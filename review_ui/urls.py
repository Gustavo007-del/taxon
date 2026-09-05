from django.urls import path

from .views import results_list, update_result

urlpatterns = [
    path("", results_list, name="review-results"),
    path("<int:result_id>/update/", update_result, name="review-update"),
]