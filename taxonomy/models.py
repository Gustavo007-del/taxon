from django.db import models


class TaxonomyCategory(models.Model):
    """A node in Shopify's product taxonomy tree (e.g. "Home & Garden > Furniture > Sofas")."""

    shopify_gid = models.CharField(
        max_length=255,
        unique=True,
        # Original taxonomy ID from Shopify's source data,
        # e.g. "gid://shopify/TaxonomyCategory/gg8-7l8".
    )
    name = models.CharField(max_length=255)
    full_path = models.CharField(
        max_length=500,
        unique=True,
        # Full hierarchical path joined with " > ", e.g.
        # "Home & Garden > Furniture > Sofas". Capped at 500 chars so the
        # unique index stays within MariaDB/MySQL utf8mb4 key limits.
    )
    level = models.PositiveIntegerField(default=0)  # depth in the tree; 0 = top-level vertical
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="children",
    )

    class Meta:
        ordering = ["full_path"]
        verbose_name_plural = "taxonomy categories"

    def __str__(self):
        return self.full_path


class TaxonomyAttribute(models.Model):
    """An attribute (e.g. "Color") that applies to one or more categories."""

    shopify_gid = models.CharField(max_length=255, unique=True)
    name = models.CharField(max_length=255)
    handle = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True, default="")
    categories = models.ManyToManyField(
        TaxonomyCategory,
        related_name="attributes",
        blank=True,
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class TaxonomyAttributeValue(models.Model):
    """A permitted value for an attribute (e.g. "Red" for Color)."""

    shopify_gid = models.CharField(max_length=255, unique=True)
    attribute = models.ForeignKey(
        TaxonomyAttribute,
        on_delete=models.CASCADE,
        related_name="values",
    )
    name = models.CharField(max_length=255)
    handle = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["name"]
        unique_together = ("attribute", "name")
        verbose_name_plural = "taxonomy attribute values"

    def __str__(self):
        return f"{self.attribute.name}: {self.name}"