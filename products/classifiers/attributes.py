"""Detect taxonomy attributes and values for a predicted category.

The task requires not just a category but "relevant category attributes and
attribute values". For each product's predicted category we list that
category's taxonomy attributes and match value names against the product's
text (title, description, bullets, categories, brand, materials, collection,
color). Matching is a case-insensitive whole-word check (word boundaries,
so "Red" no longer matches inside "requi-RED"); for color attributes the
dedicated Product Color / Color Collection fields are checked first for a
direct, reliable match. Results are stored on
ClassificationResult.detected_attributes.
"""
import re

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
    "color_collection",
)

# Dedicated color fields, checked directly against an attribute's value list
# before falling back to the general text-blob scan.
_DIRECT_COLOR_FIELDS = ("product_color", "color_collection")


def _is_color_attribute(structure):
    name = (structure.get("name") or "").lower()
    handle = (structure.get("handle") or "").lower()
    return "color" in name or "colour" in name or "color" in handle or "colour" in handle


def _direct_color_matches(product, values):
    """Values that exactly equal a dedicated color field (case-insensitive)."""
    if product is None:
        return []
    matched = []
    for field in _DIRECT_COLOR_FIELDS:
        raw = getattr(product, field, None)
        if not raw:
            continue
        field_text = str(raw).strip().lower()
        for value in values:
            if value and value.lower() == field_text and value not in matched:
                matched.append(value)
    return matched


def _word_match(value, blob):
    """Whole-word, case-insensitive match of a value within a text blob."""
    return bool(re.search(rf"\b{re.escape(value.lower())}\b", blob))


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
        matched = []
        # Color attributes: exact match against the dedicated color fields
        # first (reliable, e.g. Color Collection "White"), then fall back to
        # the general whole-word text scan.
        if _is_color_attribute(structure):
            matched = _direct_color_matches(product, structure["values"])
        if blob:
            for value in structure["values"]:
                if value and value not in matched and _word_match(value, blob):
                    matched.append(value)
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