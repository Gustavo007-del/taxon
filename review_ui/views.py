"""Simple server-rendered review UI (Phase 6).

Plain HTML forms + server-side POST handler (no JS build step); the
DRF API under /api/ serves the same data for programmatic access.
"""
import math

from django.shortcuts import get_object_or_404, redirect, render

from products.filters import apply_result_filters
from products.models import BatchJob, ClassificationResult
from taxonomy.models import TaxonomyCategory

PAGE_SIZE = 200


def results_list(request):
    qs = ClassificationResult.objects.select_related(
        "product", "predicted_category"
    ).order_by("-updated_at")
    qs = apply_result_filters(qs, request)
    total = qs.count()

    try:
        page = max(int(request.GET.get("page", 1)), 1)
    except ValueError:
        page = 1
    pages = max(math.ceil(total / PAGE_SIZE), 1)
    page = min(page, pages)

    results = list(qs[(page - 1) * PAGE_SIZE : page * PAGE_SIZE])

    # Resolve alternatives' shopify_gids to category pks/names so the
    # per-row "set category" dropdown can offer them as options.
    gids = {
        alt.get("shopify_gid")
        for r in results
        for alt in (r.alternatives or [])
        if alt.get("shopify_gid")
    }
    gid_to_pk = dict(
        TaxonomyCategory.objects.filter(shopify_gid__in=gids).values_list(
            "shopify_gid", "pk"
        )
    )
    gid_to_name = dict(
        TaxonomyCategory.objects.filter(shopify_gid__in=gids).values_list(
            "shopify_gid", "name"
        )
    )

    base_query = {k: v for k, v in request.GET.items() if k != "page"}
    context = {
        "results": results,
        "total": total,
        "page": page,
        "pages": pages,
        "base_query": base_query,
        "gid_to_pk": gid_to_pk,
        "gid_to_name": gid_to_name,
        "jobs": BatchJob.objects.all()[:5],
        "status_choices": ClassificationResult.Status.choices,
    }
    return render(request, "review_ui/results_list.html", context)


def update_result(request, result_id):
    """Handle the approve / reject / set-category forms (plain POSTs)."""
    result = get_object_or_404(ClassificationResult, pk=result_id)
    action = request.POST.get("action")

    if action == "approve":
        result.status = ClassificationResult.Status.APPROVED
        result.save(update_fields=["status", "updated_at"])
    elif action == "reject":
        result.status = ClassificationResult.Status.REJECTED
        result.save(update_fields=["status", "updated_at"])
    elif action == "set_category":
        category = None
        category_id = request.POST.get("category_id")
        if category_id:
            category = TaxonomyCategory.objects.filter(pk=category_id).first()
        if category is not None:
            result.predicted_category = category
            # A human-chosen category IS the review decision.
            result.status = ClassificationResult.Status.APPROVED
            result.save(
                update_fields=["predicted_category", "status", "updated_at"]
            )

    query = request.GET.urlencode()
    return redirect(f"/?{query}" if query else "/")