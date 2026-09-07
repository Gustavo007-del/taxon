"""Review UI pages: React SPA host + server-rendered fallback (classic).

The React SPA (frontend/dist) is served at the site root (/) and talks to
the DRF API under /api/. Old /app/... URLs redirect to root equivalents.
The classic pages live under /legacy/ for backwards compatibility and
rollback when frontend/dist is missing.
"""
import math

from django.conf import settings
from django.db.models import Avg, Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import ensure_csrf_cookie

from products.filters import apply_result_filters
from products.models import BatchJob, ClassificationResult, Product
from taxonomy.models import TaxonomyCategory

PAGE_SIZE = 200

SPA_INDEX = settings.BASE_DIR / "frontend" / "dist" / "index.html"


def spa_built():
    return SPA_INDEX.exists()


@ensure_csrf_cookie
def spa_index(request, *args, **kwargs):
    """Serve the built React SPA (frontend/dist/index.html).

    ensure_csrf_cookie makes the CSRF cookie available to the SPA's fetch()
    calls (same mechanism the classic base.html used with {% csrf_token %}).
    Falls back to a short notice page when the frontend isn't built, so this
    route never 404s in a fresh checkout.
    """
    if spa_built():
        return HttpResponse(
            SPA_INDEX.read_text(encoding="utf-8"),
            content_type="text/html; charset=utf-8",
        )
    return HttpResponse(
        "<!DOCTYPE html><html lang='en'><body style='font-family:sans-serif;padding:2rem'>"
        "<h2>React frontend not built yet</h2>"
        "<p>Build it from the <code>frontend/</code> directory with "
        "<code>npm install && npm run build</code>, then reload this page. "
        "Meanwhile the classic pages still work at "
        "<a href='/legacy/dashboard/'>/legacy/dashboard/</a> and "
        "<a href='/legacy/results/'>/legacy/results/</a>.</p>"
        "</body></html>",
        content_type="text/html; charset=utf-8",
    )


def spa_or_dashboard(request):
    """Root route: the React SPA when built, otherwise the classic dashboard."""
    if spa_built():
        return spa_index(request)
    return redirect("review-dashboard")


def spa_redirect(request, rest=""):
    """Redirect old /app/... URLs to their root equivalents.

    /app            -> /dashboard
    /app/results    -> /results
    /app/results/5  -> /results/5
    """
    target = f"/{rest}" if rest else "/dashboard"
    return redirect(target)


def _gid_maps(gids):
    """Resolve a set of shopify gids to (pk, name) lookup dicts."""
    gids = {g for g in gids if g}
    if not gids:
        return {}, {}
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
    return gid_to_pk, gid_to_name


def _result_gids(results):
    return {
        alt.get("shopify_gid")
        for r in results
        for alt in (r.alternatives or [])
        if alt.get("shopify_gid")
    }


def dashboard(request):
    """Summary stats + recent batch jobs + classification run trigger."""
    products_total = Product.objects.count()
    by_status = {
        row["status"]: row["count"]
        for row in ClassificationResult.objects.values("status").annotate(
            count=Count("pk")
        )
    }
    results_total = sum(by_status.values())

    avg = ClassificationResult.objects.filter(
        final_confidence__isnull=False
    ).aggregate(a=Avg("final_confidence"))["a"]

    jobs = BatchJob.objects.all()[:8]
    jobs_data = [
        {
            "job": j,
            "pct": round(100 * j.processed / j.total) if j.total else 0,
        }
        for j in jobs
    ]

    context = {
        "stats": {
            "products_total": products_total,
            "pending": products_total - results_total,
            "auto_approved": by_status.get(ClassificationResult.Status.AUTO_APPROVED, 0),
            "needs_review": by_status.get(ClassificationResult.Status.NEEDS_REVIEW, 0),
            "approved": by_status.get(ClassificationResult.Status.APPROVED, 0),
            "rejected": by_status.get(ClassificationResult.Status.REJECTED, 0),
            "failed": by_status.get(ClassificationResult.Status.FAILED, 0),
            "avg_confidence": round(avg, 3) if avg is not None else None,
        },
        "jobs": jobs_data,
    }
    return render(request, "review_ui/dashboard.html", context)


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
    gid_to_pk, gid_to_name = _gid_maps(_result_gids(results))

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


def result_detail(request, result_id):
    """Full product view with approve / reject / set-category actions."""
    result = get_object_or_404(
        ClassificationResult.objects.select_related("product", "predicted_category"),
        pk=result_id,
    )
    gid_to_pk, gid_to_name = _gid_maps(_result_gids([result]))
    context = {
        "result": result,
        "gid_to_pk": gid_to_pk,
        "gid_to_name": gid_to_name,
    }
    return render(request, "review_ui/result_detail.html", context)


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

    # Return to the page the form came from (relative path only).
    next_url = request.POST.get("next") or "/"
    if not next_url.startswith("/") or "://" in next_url:
        next_url = "/"
    return redirect(next_url)
