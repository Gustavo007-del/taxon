"""Combine pass-1 (text) and pass-2 (image) results for one product.

Per the plan:
- same category from both passes -> boost confidence (avg + 0.1, capped at 1.0)
- different categories -> take the lower confidence, force needs_review,
  store both as alternatives
- no text prediction (empty blob) -> nothing to disagree with, adopt the
  image result so the fallback actually rescues those rows
- no usable image -> keep the text result, stay needs_review
"""
from products.models import ClassificationResult

SAME_CATEGORY_BOOST = 0.1


def _merge_alternatives(text_alts, image_alts, limit=3):
    """Merge both top-k lists, keeping the higher score per gid, top `limit`."""
    merged = {}
    for alt in list(text_alts) + list(image_alts):
        gid = alt.get("shopify_gid")
        if gid is None:
            continue
        existing = merged.get(gid)
        if existing is None or alt.get("score", 0.0) > existing.get("score", 0.0):
            merged[gid] = alt
    ranked = sorted(
        merged.values(), key=lambda a: a.get("score", 0.0), reverse=True
    )
    return ranked[:limit]


def combine_results(text_result, image_result, confidence_threshold=0.65):
    """Return the fields to write back onto a ClassificationResult.

    text_result / image_result are dicts with predicted_gid, confidence,
    alternatives (the shape produced by both classifier classes).
    """
    text_gid = text_result.get("predicted_gid")
    image_gid = image_result.get("predicted_gid")
    image_confidence = image_result.get("confidence", 0.0)
    alternatives = _merge_alternatives(
        text_result.get("alternatives", []),
        image_result.get("alternatives", []),
    )

    if image_gid is None:
        # No usable image: keep the text result, still needs review.
        return {
            "final_confidence": round(text_result.get("confidence", 0.0), 4),
            "method_used": ClassificationResult.Method.TEXT_ONLY,
            "status": ClassificationResult.Status.NEEDS_REVIEW,
            "alternatives": alternatives,
            "flags": {"image_pass": "no_valid_images"},
        }

    if text_gid is None:
        # No text prediction (e.g. empty blob) — adopt the image prediction.
        final = image_confidence
        status = (
            ClassificationResult.Status.AUTO_APPROVED
            if final >= confidence_threshold
            else ClassificationResult.Status.NEEDS_REVIEW
        )
        return {
            "final_confidence": round(float(final), 4),
            "method_used": ClassificationResult.Method.TEXT_PLUS_IMAGE,
            "status": status,
            "alternatives": alternatives,
            "flags": {"no_text_prediction": True},
        }

    if text_gid == image_gid:
        final = min(
            1.0,
            (text_result.get("confidence", 0.0) + image_confidence) / 2
            + SAME_CATEGORY_BOOST,
        )
        status = (
            ClassificationResult.Status.AUTO_APPROVED
            if final >= confidence_threshold
            else ClassificationResult.Status.NEEDS_REVIEW
        )
        flags = {"text_image_agreement": True}
    else:
        final = min(text_result.get("confidence", 0.0), image_confidence)
        status = ClassificationResult.Status.NEEDS_REVIEW
        flags = {"text_image_disagreement": True}

    return {
        "final_confidence": round(float(final), 4),
        "method_used": ClassificationResult.Method.TEXT_PLUS_IMAGE,
        "status": status,
        "alternatives": alternatives,
        "flags": flags,
    }