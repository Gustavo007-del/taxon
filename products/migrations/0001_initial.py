import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Product",
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
                ("product_number", models.CharField(max_length=255, unique=True)),
                ("title", models.CharField(blank=True, default="", max_length=1024)),
                ("description", models.TextField(blank=True, default="")),
                (
                    "category_raw",
                    models.CharField(blank=True, default="", max_length=512),
                ),
                (
                    "sub_category_raw",
                    models.CharField(blank=True, default="", max_length=512),
                ),
                ("brand", models.CharField(blank=True, default="", max_length=255)),
                ("materials", models.CharField(blank=True, default="", max_length=1024)),
                ("image_urls", models.JSONField(blank=True, default=list)),
                (
                    "price",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=12, null=True
                    ),
                ),
                ("raw_row", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["product_number"]},
        ),
    ]