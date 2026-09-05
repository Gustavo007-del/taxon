from django.contrib import admin

from .models import BatchJob, ClassificationResult, Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("product_number", "title", "brand", "category_raw", "price")
    search_fields = ("product_number", "title", "brand")
    list_filter = ("created_at",)


@admin.register(ClassificationResult)
class ClassificationResultAdmin(admin.ModelAdmin):
    list_display = (
        "product",
        "predicted_category",
        "status",
        "text_confidence",
        "final_confidence",
        "method_used",
    )
    search_fields = ("product__product_number", "product__title")
    list_filter = ("status", "method_used")
    autocomplete_fields = ("product", "predicted_category")


@admin.register(BatchJob)
class BatchJobAdmin(admin.ModelAdmin):
    list_display = (
        "job_type",
        "status",
        "processed",
        "total",
        "failed",
        "started_at",
        "finished_at",
    )
    list_filter = ("job_type", "status")
    readonly_fields = ("started_at", "finished_at")