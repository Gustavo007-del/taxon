"""Detect taxonomy attributes and values for a predicted category.

The task requires not just a category but "relevant category attributes and
attribute values". For each product's predicted category we list that
category's taxonomy attributes and match value names against the product's
text (title, description, bullets, categories, brand, materials, collection,
color). Matching is a case-insensitive substring check — simple and
predictable for a prototype — and results are stored on
ClassificationResult.detected_attributes.
"""
from django.db.models import Prefetch

MAX_MATCHED_VALUES = 10

_TEXT_FIELDS = (
    "title",
    "description",
    "bullets",
    "category_raw",
    "sub_category_raw",
    "brand",
    "materials",
    "collection_name",
    "product_color",
)


def build_text_sources(product):
    """Concatenated lowercase text of a product, used for value matching."""
    parts = []
    for field in _TEXT_FIELDS:
        value = getattr(product, field, None)
        if value:
            parts.append(str(value))
    return " ".join(parts).lower()


def attributes_map(category_pks):
    """Return {category_pk: [{"name", "handle", "values": [...]}]}.

    Loads each category's attributes and all their values with two queries
    (nested prefetch), then builds plain structures for matching.
    """
    from taxonomy.models import TaxonomyAttribute, TaxonomyCategory

    if not category_pks:
        return {}
    categories = TaxonomyCategory.objects.filter(pk__in=category_pks).prefetch_related(
        Prefetch(
            "attributes",
            queryset=TaxonomyAttribute.objects.order_by("name").prefetch_related(
                "values"
            ),
        )
    )
    out = {}
    for category in categories:
        attrs = []
        for attr in category.attributes.all():
            attrs.append(
                {
                    "name": attr.name,
                    "handle": attr.handle,
                    "values": [v.name for v in attr.values.all()],
                }
            )
        out[category.pk] = attrs
    return out


def detect_attributes(product, structures):
    """Match a product's text against attribute value lists.

    structures: the [{"name", "handle", "values"}] list from attributes_map.
    Returns [{name, handle, values: [matched], value_count}], including
    attributes with no match so the UI shows what is relevant.
    """
    if product is None or not structures:
        return []
    blob = build_text_sources(product)
    out = []
    for structure in structures:
        if blob:
            matched = [
                value
                for value in structure["values"]
                if value and value.lower() in blob
            ]
        else:
            matched = []
        out.append(
            {
                "name": structure["name"],
                "handle": structure["handle"],
                "values": matched[:MAX_MATCHED_VALUES],
                "value_count": len(structure["values"]),
            }
        )
    return out


def attach_attributes(results, products_by_id, attr_map):
    """Set result["attributes"] on each result dict (mutates in place)."""
    for result in results:
        product = products_by_id.get(result.get("product_id"))
        structures = attr_map.get(result.get("predicted_pk"))
        result["attributes"] = detect_attributes(product, structures)