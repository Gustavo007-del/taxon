from django.urls import path

from .views import dashboard, result_detail, results_list, update_result

urlpatterns = [
    # Kept at the root for backwards compatibility with the original layout.
    path("", results_list, name="review-results"),
    path("dashboard/", dashboard, name="review-dashboard"),
    path("results/", results_list, name="review-results-list"),
    path("results/<int:result_id>/", result_detail, name="review-detail"),
    path(
        "results/<int:result_id>/update/",
        update_result,
        name="review-update",
    ),
]
