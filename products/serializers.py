"""DRF serializers for the review API (Phase 6)."""
from rest_framework import serializers

from products.models import ClassificationResult, Product
from taxonomy.models import TaxonomyCategory


class CategoryBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaxonomyCategory
        fields = ("id", "name", "full_path", "shopify_gid")


class ProductBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ("id", "product_number", "title", "brand", "image_urls", "price")


class ClassificationResultSerializer(serializers.ModelSerializer):
    product = ProductBriefSerializer(read_only=True)
    predicted_category = CategoryBriefSerializer(read_only=True)
    # Writable alias so PATCH can set the category by id (the nested
    # serializer above is read-only).
    predicted_category_id = serializers.PrimaryKeyRelatedField(
        source="predicted_category",
        queryset=TaxonomyCategory.objects.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = ClassificationResult
        fields = (
            "id",
            "product",
            "predicted_category",
            "predicted_category_id",
            "text_confidence",
            "image_confidence",
            "final_confidence",
            "alternatives",
            "detected_attributes",
            "status",
            "method_used",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "product",
            "text_confidence",
            "image_confidence",
            "final_confidence",
            "alternatives",
            "detected_attributes",
            "method_used",
            "created_at",
            "updated_at",
        )