"""Classification run orchestration (Phases 5/6).

run_text_job / run_image_job encapsulate the full chunked processing loop,
including BatchJob progress tracking, resume logic, and per-product failure
isolation. They are shared by the management commands (CLI) and the batch
API (background thread), and are Celery-task-ready: once config/celery.py
exists, wrap them with @shared_task and dispatch per job.
"""
import logging

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from products.batch import finish_job, start_job, update_progress
from products.classifiers.attributes import attributes_map, detect_attributes
from products.classifiers.image_classifier import ImageClassifier
from products.classifiers.pipeline import combine_results
from products.classifiers.text_classifier import TextClassifier
from products.models import BatchJob, ClassificationResult, Product

logger = logging.getLogger(__name__)

_TEXT_UPDATE_FIELDS = (
    "predicted_category",
    "text_confidence",
    "final_confidence",
    "alternatives",
    "detected_attributes",
    "status",
    "method_used",
    "updated_at",
)

_IMAGE_UPDATE_FIELDS = (
    "predicted_category",
    "image_confidence",
    "final_confidence",
    "method_used",
    "status",
    "alternatives",
    "detected_attributes",
    "updated_at",
)


def _log_default(msg):
    logger.info(msg)


def _err_default(msg):
    logger.error(msg)


def _as_bool(value, default=False):
    """Coerce API/CLI input to bool ("false"/"0"/"no" must not be truthy)."""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Pass 1: text
# ---------------------------------------------------------------------------


def run_text_job(job_id=None, options=None, log=None, err=None):
    """Run the pass-1 text classification loop.

    job_id: pk of an existing BatchJob (API path) or None to create one
            (CLI path; returns (None, summary) when there is nothing to do).
    options: fuzzy, fuzzy_threshold, confidence_threshold, batch_size,
             chunk_size, reclassify, limit.
    Returns (job, summary) where summary has total/processed/failed/status_counts.
    """
    options = options or {}
    log = log or _log_default
    err = err or _err_default

    reclassify = _as_bool(options.get("reclassify", False))
    limit = int(options.get("limit") or 0)
    threshold = float(options.get("confidence_threshold", 0.65))
    chunk_size = int(options.get("chunk_size", 200))
    batch_size = int(options.get("batch_size", 64))
    fuzzy = _as_bool(options.get("fuzzy", True))
    fuzzy_threshold = float(options.get("fuzzy_threshold", 90.0))

    qs = Product.objects.select_related("classification_result").order_by("pk")
    if reclassify:
        # Never overwrite manual review decisions.
        qs = qs.exclude(
            classification_result__status__in=[
                ClassificationResult.Status.APPROVED,
                ClassificationResult.Status.REJECTED,
            ]
        )
    else:
        # Resume logic: products without a result, or whose result is still
        # pending or failed from a previous run.
        qs = qs.filter(
            Q(classification_result__isnull=True)
            | Q(
                classification_result__status__in=[
                    ClassificationResult.Status.PENDING,
                    ClassificationResult.Status.FAILED,
                ]
            )
        )

    total = qs.count()
    if limit:
        qs = qs[:limit]
        total = limit

    if job_id is not None:
        job = BatchJob.objects.get(pk=job_id)
        BatchJob.objects.filter(pk=job.pk).update(total=total)
        job.total = total
    elif total == 0:
        return None, {"total": 0, "processed": 0, "failed": 0, "status_counts": {}}
    else:
        job = start_job(BatchJob.JobType.TEXT, total, **options)

    log(f"Classifying {total} products (text pass)...")
    try:
        classifier = TextClassifier(
            fuzzy=fuzzy, fuzzy_threshold=fuzzy_threshold, batch_size=batch_size
        )
    except RuntimeError as exc:
        finish_job(job, success=False)
        raise

    processed = 0
    failed = 0
    status_counts = {}
    try:
        for start in range(0, total, chunk_size):
            chunk = list(qs[start : start + chunk_size])
            results, chunk_failures = _classify_text_chunk(classifier, chunk, err)
            failed += len(chunk_failures)
            _persist_text_results(
                results,
                chunk_failures,
                reclassify=reclassify,
                threshold=threshold,
                status_counts=status_counts,
            )
            processed += len(chunk)
            update_progress(job, processed, failed)
            log(f"  processed {processed}/{total} (failed {failed})")
    except Exception:
        finish_job(job, failed=failed, success=False)
        raise

    finish_job(job, failed=failed)
    summary = {
        "total": total,
        "processed": processed,
        "failed": failed,
        "status_counts": status_counts,
    }
    return job, summary


def _classify_text_chunk(classifier, products, err):
    """Classify a chunk; on failure fall back to per-product so one bad row
    can't kill the batch. Returns (results, failures) where failures is a
    list of (product, reason)."""
    try:
        return classifier.classify_products(products), []
    except Exception:
        results = []
        failures = []
        for product in products:
            try:
                results.append(classifier.classify_products([product])[0])
            except Exception as exc:  # noqa: BLE001 - keep the batch alive
                failures.append((product, str(exc)))
                err(f"  classification failed for {product.product_number}: {exc}")
        return results, failures


@transaction.atomic
def _persist_text_results(results, failures, reclassify, threshold, status_counts):
    """Bulk-create/update ClassificationResult rows for one chunk.

    Rows for products that already have a result (pending/failed from a
    previous run) are updated in place; the rest are created. Failed
    classifications are stored as status=failed for the next run.
    """
    combined = list(results)
    for product, reason in failures:
        combined.append(
            {
                "product_id": product.pk,
                "predicted_pk": None,
                "confidence": 0.0,
                "alternatives": [],
                "attributes": [],
                "failed": True,
                "reason": reason,
            }
        )
    if not combined:
        return

    pids = [r["product_id"] for r in combined]
    if reclassify:
        ClassificationResult.objects.filter(product_id__in=pids).delete()
        existing = {}
    else:
        existing = dict(
            ClassificationResult.objects.filter(product_id__in=pids).values_list(
                "product_id", "pk"
            )
        )

    to_create = []
    to_update = []
    now = timezone.now()
    for result in combined:
        if result.get("failed"):
            status = ClassificationResult.Status.FAILED
        elif result["predicted_pk"] is None or result["confidence"] < threshold:
            status = ClassificationResult.Status.NEEDS_REVIEW
        else:
            status = ClassificationResult.Status.AUTO_APPROVED
        status_counts[str(status)] = status_counts.get(str(status), 0) + 1

        obj = ClassificationResult(
            product_id=result["product_id"],
            predicted_category_id=result["predicted_pk"],
            text_confidence=result["confidence"],
            final_confidence=result["confidence"],
            alternatives=result["alternatives"],
            detected_attributes=result.get("attributes", []),
            status=status,
            method_used=ClassificationResult.Method.TEXT_ONLY,
        )
        if result["product_id"] in existing:
            obj.pk = existing[result["product_id"]]
            obj.updated_at = now
            to_update.append(obj)
        else:
            to_create.append(obj)

    ClassificationResult.objects.bulk_create(to_create)
    if to_update:
        ClassificationResult.objects.bulk_update(to_update, _TEXT_UPDATE_FIELDS)


# ---------------------------------------------------------------------------
# Pass 2: image
# ---------------------------------------------------------------------------


def run_image_job(job_id=None, options=None, log=None, err=None):
    """Run the pass-2 image classification loop.

    job_id: pk of an existing BatchJob (API path) or None to create one
            (CLI path; returns (None, summary) when there is nothing to do).
    options: workers, threshold, chunk_size, limit, all_results.
    Returns (job, summary) where summary has total/processed/failed/counts.
    """
    options = options or {}
    log = log or _log_default
    err = err or _err_default

    all_results = _as_bool(options.get("all_results", False))
    limit = int(options.get("limit") or 0)
    threshold = float(options.get("threshold", 0.65))
    chunk_size = int(options.get("chunk_size", 50))
    workers = int(options.get("workers", 10))

    qs = ClassificationResult.objects.select_related(
        "product", "predicted_category"
    ).order_by("pk")
    # Never overwrite manual review decisions.
    qs = qs.exclude(
        status__in=[
            ClassificationResult.Status.APPROVED,
            ClassificationResult.Status.REJECTED,
        ]
    )
    if not all_results:
        # Resume logic: needs_review rows plus rows that failed last run.
        qs = qs.filter(
            status__in=[
                ClassificationResult.Status.NEEDS_REVIEW,
                ClassificationResult.Status.FAILED,
            ]
        )

    total = qs.count()
    if limit:
        qs = qs[:limit]
        total = limit

    if job_id is not None:
        job = BatchJob.objects.get(pk=job_id)
        BatchJob.objects.filter(pk=job.pk).update(total=total)
        job.total = total
    elif total == 0:
        return None, {"total": 0, "processed": 0, "failed": 0, "counts": {}}
    else:
        job = start_job(BatchJob.JobType.IMAGE, total, **options)

    log(f"Running image pass on {total} product(s)...")
    try:
        classifier = ImageClassifier(workers=workers)
    except RuntimeError as exc:
        finish_job(job, success=False)
        raise

    counts = {"auto_approved": 0, "needs_review": 0, "no_images": 0, "failed": 0}
    processed = 0
    failed = 0
    try:
        for start in range(0, total, chunk_size):
            chunk = list(qs[start : start + chunk_size])
            chunk_failed = _process_image_chunk(
                chunk, classifier, threshold, counts, err
            )
            failed += chunk_failed
            processed += len(chunk)
            update_progress(job, processed, failed)
            log(f"  processed {processed}/{total} (failed {failed})")
    except Exception:
        finish_job(job, failed=failed, success=False)
        raise

    finish_job(job, failed=failed)
    summary = {
        "total": total,
        "processed": processed,
        "failed": failed,
        "counts": counts,
    }
    return job, summary


@transaction.atomic
def _process_image_chunk(chunk, classifier, threshold, counts, err):
    """Classify + combine one chunk, bulk-update rows; returns # failures."""
    updates = []
    failed = 0
    for result in chunk:
        product = result.product
        try:
            image_result = classifier.classify_product(product)
        except Exception as exc:  # noqa: BLE001 - keep the batch alive
            result.status = ClassificationResult.Status.FAILED
            result.updated_at = timezone.now()
            updates.append(result)
            counts["failed"] += 1
            failed += 1
            err(f"  error classifying {product.product_number}: {exc}")
            continue

        if image_result["predicted_gid"] is None:
            counts["no_images"] += 1
            continue  # no usable image — leave status as needs_review

        text_result = {
            "predicted_gid": (
                result.predicted_category.shopify_gid
                if result.predicted_category
                else None
            ),
            "confidence": result.text_confidence or 0.0,
            "alternatives": result.alternatives,
        }
        if text_result["predicted_gid"] is None:
            # No text prediction — adopt the image category too (not just its
            # score), so the stored prediction matches the boosted confidence.
            result.predicted_category_id = image_result["predicted_pk"]

        combined = combine_results(text_result, image_result, threshold)

        result.image_confidence = image_result["confidence"]
        result.final_confidence = combined["final_confidence"]
        result.method_used = combined["method_used"]
        result.status = combined["status"]
        result.alternatives = combined["alternatives"]
        result.updated_at = timezone.now()
        counts[str(result.status)] = counts.get(str(result.status), 0) + 1
        updates.append(result)

    if updates:
        # Re-detect attributes against each row's final category (which the
        # image pass may have adopted), so the stored attribute list always
        # matches the stored prediction.
        final_pks = {
            r.predicted_category_id for r in updates if r.predicted_category_id
        }
        structures = attributes_map(final_pks)
        for result in updates:
            if result.status == ClassificationResult.Status.FAILED:
                continue  # keep whatever attributes the text pass stored
            product = result.product
            result.detected_attributes = detect_attributes(
                product, structures.get(result.predicted_category_id)
            )
        ClassificationResult.objects.bulk_update(updates, _IMAGE_UPDATE_FIELDS)
    return failed