"""Shared query filtering for the classification-results list (API + review UI)."""
from django.db.models import Q


def apply_result_filters(qs, request):
    """Apply ?status= (comma-separated), ?min_confidence=, ?q= to a queryset.

    Malformed numeric filters are ignored rather than erroring.
    """
    status_param = request.GET.get("status")
    if status_param:
        statuses = [s.strip() for s in status_param.split(",") if s.strip()]
        qs = qs.filter(status__in=statuses)

    min_confidence = request.GET.get("min_confidence")
    if min_confidence:
        try:
            qs = qs.filter(final_confidence__gte=float(min_confidence))
        except ValueError:
            pass

    q = request.GET.get("q")
    if q:
        qs = qs.filter(
            Q(product__product_number__icontains=q) | Q(product__title__icontains=q)
        )
    return qs