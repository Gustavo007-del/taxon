from django.urls import path, re_path

from .views import (
    dashboard,
    result_detail,
    results_list,
    spa_index,
    spa_or_dashboard,
    spa_redirect,
    update_result,
)

urlpatterns = [
    # React SPA: the site root (and every path not matched below) serves the
    # built app, so /, /dashboard, /results and /results/<id> all work
    # directly in the browser.
    path("", spa_or_dashboard, name="review-home"),
    path("app/", spa_redirect, {"rest": ""}, name="spa-old-root"),
    path("app/<path:rest>", spa_redirect, name="spa-old-routes"),
    # Classic server-rendered pages — kept under /legacy/ for rollback and
    # for no-build setups (when frontend/dist is missing).
    path("legacy/dashboard/", dashboard, name="review-dashboard"),
    path("legacy/results/", results_list, name="review-results-list"),
    path("legacy/results/<int:result_id>/", result_detail, name="review-detail"),
    path(
        "legacy/results/<int:result_id>/update/",
        update_result,
        name="review-update",
    ),
    # Catch-all: everything else (except admin/, api/, media/, static/ —
    # resolved earlier in config/urls.py or by the static handler) loads the
    # SPA, which renders the dashboard for unknown paths.
    re_path(r"^.*", spa_index, name="spa-catchall"),
]