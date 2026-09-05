"""DRF API views for results review + batch progress (Phase 6)."""
import threading

from django.shortcuts import get_object_or_404
from rest_framework import status as http_status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from products.batch import start_job
from products.filters import apply_result_filters
from products.models import BatchJob, ClassificationResult
from products.serializers import ClassificationResultSerializer

MAX_PAGE_SIZE = 500


class ClassificationResultList(APIView):
    """GET /api/results/?status=needs_review&min_confidence=0.4&q=&limit=&offset="""

    def get(self, request):
        qs = ClassificationResult.objects.select_related(
            "product", "predicted_category"
        ).order_by("-updated_at")
        qs = apply_result_filters(qs, request)
        total = qs.count()

        try:
            limit = min(int(request.GET.get("limit", 100)), MAX_PAGE_SIZE)
        except ValueError:
            limit = 100
        try:
            offset = max(int(request.GET.get("offset", 0)), 0)
        except ValueError:
            offset = 0

        page = list(qs[offset : offset + limit])
        data = ClassificationResultSerializer(page, many=True).data
        return Response(
            {"count": total, "limit": limit, "offset": offset, "results": data}
        )


class ClassificationResultDetail(APIView):
    """GET /api/results/{id}/ and PATCH /api/results/{id}/ (edit category/status)."""

    def get(self, request, pk):
        result = get_object_or_404(
            ClassificationResult.objects.select_related(
                "product", "predicted_category"
            ),
            pk=pk,
        )
        return Response(ClassificationResultSerializer(result).data)

    def patch(self, request, pk):
        result = get_object_or_404(ClassificationResult, pk=pk)
        serializer = ClassificationResultSerializer(
            result, data=request.data, partial=True
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=http_status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(ClassificationResultSerializer(result).data)


class BatchRunView(APIView):
    """POST /api/batch/run/ — kick off classification in a background thread.

    Body: {"job_type": "text"|"image", ...run options...}. Returns 202 with
    the job id; poll GET /api/batch/{id}/ for progress. (Note: the thread
    runs alongside the dev server; wire Celery per Phase 5 for production.)
    """

    _KNOWN_OPTIONS = (
        "fuzzy",
        "fuzzy_threshold",
        "confidence_threshold",
        "batch_size",
        "chunk_size",
        "reclassify",
        "limit",
        "workers",
        "threshold",
        "all_results",
    )

    def post(self, request):
        from products.tasks import run_image_job, run_text_job

        raw_type = str(request.data.get("job_type", "text")).lower()
        try:
            job_type = BatchJob.JobType(raw_type)
        except ValueError:
            raise ValidationError(
                {"job_type": f"must be one of: text, image (got {raw_type!r})"}
            )

        params = {k: request.data[k] for k in self._KNOWN_OPTIONS if k in request.data}
        for key, converter in (
            ("fuzzy_threshold", float),
            ("confidence_threshold", float),
            ("threshold", float),
            ("batch_size", int),
            ("chunk_size", int),
            ("limit", int),
            ("workers", int),
        ):
            if key in params:
                try:
                    converter(params[key])
                except (TypeError, ValueError):
                    raise ValidationError({key: "must be numeric"})

        job = start_job(job_type, 0, **params)

        runner = run_text_job if job_type == BatchJob.JobType.TEXT else run_image_job
        threading.Thread(target=runner, args=(job.pk, params), daemon=True).start()
        return Response(
            {"id": job.pk, "job_type": job_type, "status": BatchJob.Status.RUNNING},
            status=http_status.HTTP_202_ACCEPTED,
        )


class BatchJobDetail(APIView):
    """GET /api/batch/{id}/ — progress (processed/total)."""

    def get(self, request, pk):
        job = get_object_or_404(BatchJob, pk=pk)
        return Response(
            {
                "id": job.pk,
                "job_type": job.job_type,
                "status": job.status,
                "total": job.total,
                "processed": job.processed,
                "failed": job.failed,
                "options": job.options,
                "started_at": job.started_at,
                "finished_at": job.finished_at,
            }
        )