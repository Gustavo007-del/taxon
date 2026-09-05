from django.db import models


class Product(models.Model):
    """A product row mirrored from the supplier spreadsheet (Product_List.xlsx)."""

    product_number = models.CharField(max_length=255, unique=True)
    title = models.CharField(max_length=1024, blank=True, default="")
    description = models.TextField(blank=True, default="")
    category_raw = models.CharField(max_length=512, blank=True, default="")
    sub_category_raw = models.CharField(max_length=512, blank=True, default="")
    brand = models.CharField(max_length=255, blank=True, default="")
    materials = models.CharField(max_length=1024, blank=True, default="")
    image_urls = models.JSONField(blank=True, default=list)
    price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    raw_row = models.JSONField(blank=True, default=dict)  # cheap insurance: full source row
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["product_number"]

    def __str__(self):
        return self.product_number


class ClassificationResult(models.Model):
    """Classification outcome for one product (one row per product)."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        AUTO_APPROVED = "auto_approved", "Auto-approved"
        NEEDS_REVIEW = "needs_review", "Needs review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        FAILED = "failed", "Failed"  # per-product failure; retried on next run

    class Method(models.TextChoices):
        TEXT_ONLY = "text_only", "Text only"
        TEXT_PLUS_IMAGE = "text_plus_image", "Text + image"

    product = models.OneToOneField(
        Product,
        on_delete=models.CASCADE,
        related_name="classification_result",
    )
    predicted_category = models.ForeignKey(
        "taxonomy.TaxonomyCategory",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="classification_results",
    )
    text_confidence = models.FloatField(null=True, blank=True)
    image_confidence = models.FloatField(null=True, blank=True)
    final_confidence = models.FloatField(null=True, blank=True)
    # Top-3 candidate categories: [{"shopify_gid": ..., "name": ..., "score": ...}]
    alternatives = models.JSONField(blank=True, default=list)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    method_used = models.CharField(
        max_length=20, choices=Method.choices, default=Method.TEXT_ONLY
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.product} -> {self.predicted_category} ({self.status})"


class BatchJob(models.Model):
    """One classification run (text or image pass) with progress tracking."""

    class JobType(models.TextChoices):
        TEXT = "text", "Text classification"
        IMAGE = "image", "Image classification"

    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    job_type = models.CharField(max_length=20, choices=JobType.choices)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.RUNNING
    )
    total = models.PositiveIntegerField(default=0)
    processed = models.PositiveIntegerField(default=0)
    failed = models.PositiveIntegerField(default=0)
    options = models.JSONField(blank=True, default=dict)  # run parameters
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.job_type} {self.status} ({self.processed}/{self.total})"