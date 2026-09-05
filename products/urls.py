"""URLs for the products review API (Phase 6)."""
from django.urls import path

from products.views import (
    BatchJobDetail,
    BatchRunView,
    ClassificationResultDetail,
    ClassificationResultList,
)

urlpatterns = [
    path("results/", ClassificationResultList.as_view(), name="api-result-list"),
    path(
        "results/<int:pk>/",
        ClassificationResultDetail.as_view(),
        name="api-result-detail",
    ),
    path("batch/run/", BatchRunView.as_view(), name="api-batch-run"),
    path("batch/<int:pk>/", BatchJobDetail.as_view(), name="api-batch-detail"),
]