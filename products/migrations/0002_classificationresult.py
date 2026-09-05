import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0001_initial"),
        ("taxonomy", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ClassificationResult",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("text_confidence", models.FloatField(blank=True, null=True)),
                ("image_confidence", models.FloatField(blank=True, null=True)),
                ("final_confidence", models.FloatField(blank=True, null=True)),
                ("alternatives", models.JSONField(blank=True, default=list)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("auto_approved", "Auto-approved"),
                            ("needs_review", "Needs review"),
                            ("approved", "Approved"),
                            ("rejected", "Rejected"),
                            ("failed", "Failed"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                (
                    "method_used",
                    models.CharField(
                        choices=[
                            ("text_only", "Text only"),
                            ("text_plus_image", "Text + image"),
                        ],
                        default="text_only",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "predicted_category",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="classification_results",
                        to="taxonomy.taxonomycategory",
                    ),
                ),
                (
                    "product",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="classification_result",
                        to="products.product",
                    ),
                ),
            ],
            options={"ordering": ["-updated_at"]},
        ),
    ]