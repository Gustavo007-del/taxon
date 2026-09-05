"""Seed the taxonomy tables from Shopify's product taxonomy distribution files.

Distribution files are published as gzip-compressed JSON assets on GitHub
releases: https://github.com/Shopify/product-taxonomy/releases/latest

Vendored copies live in data/taxonomy/ (see data/taxonomy/README.md for
how they were obtained and how to refresh them).

The categories file carries the tree (id, name, full path, parent) plus the
attributes referenced by each category; the attributes file carries the
per-attribute permitted values. Both are merged here, preserving the
category hierarchy via the self-referencing ``parent`` FK.
"""
import gzip
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from taxonomy.models import TaxonomyAttribute, TaxonomyAttributeValue, TaxonomyCategory

DEFAULT_CATEGORIES = settings.BASE_DIR / "data" / "taxonomy" / "categories.en.json.gz"
DEFAULT_ATTRIBUTES = settings.BASE_DIR / "data" / "taxonomy" / "attributes.en.json.gz"


def _read_json(path):
    """Read a JSON file, transparently decompressing .gz files."""
    path = Path(path)
    if not path.is_file():
        raise CommandError(f"Taxonomy data file not found: {path}")
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


class Command(BaseCommand):
    help = (
        "Seed the taxonomy tables (categories, attributes, attribute values) "
        "from Shopify's product taxonomy distribution files."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--categories",
            default=str(DEFAULT_CATEGORIES),
            help="Path to the categories JSON file (.gz supported).",
        )
        parser.add_argument(
            "--attributes",
            default=str(DEFAULT_ATTRIBUTES),
            help="Path to the attributes JSON file (.gz supported).",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete all existing taxonomy rows before loading (re-seed from scratch).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["reset"]:
            self.stdout.write("Resetting taxonomy tables...")
            TaxonomyAttributeValue.objects.all().delete()
            TaxonomyAttribute.objects.all().delete()  # also clears category-attribute links
            TaxonomyCategory.objects.all().delete()

        categories_data = _read_json(options["categories"])
        attributes_data = _read_json(options["attributes"])

        self.stdout.write(
            f"Source: Shopify product taxonomy version {categories_data.get('version')}"
        )

        n_categories = self._load_categories(categories_data)
        n_links = self._load_category_attributes(categories_data)
        n_values = self._load_attribute_values(attributes_data)

        self.stdout.write(self.style.SUCCESS(
            f"Done: {n_categories} categories, {n_links} category-attribute "
            f"links, {n_values} attribute values."
        ))

    # ------------------------------------------------------------------ #
    # Loading helpers (all idempotent; safe to re-run without --reset).   #
    # ------------------------------------------------------------------ #

    def _load_categories(self, data):
        """Create category rows, then wire up parent pointers from parent_id."""
        existing = set(TaxonomyCategory.objects.values_list("shopify_gid", flat=True))
        to_create = []
        raw_rows = []  # (gid, parent_gid) pairs for the parent pass
        for vertical in data.get("verticals", []):
            for cat in vertical.get("categories", []):
                gid = cat["id"]
                raw_rows.append((gid, cat.get("parent_id")))
                if gid not in existing:
                    to_create.append(
                        TaxonomyCategory(
                            shopify_gid=gid,
                            name=cat["name"],
                            full_path=cat["full_name"],
                            level=cat.get("level", 0),
                        )
                    )
        TaxonomyCategory.objects.bulk_create(to_create, batch_size=1000)

        # gid -> pk map covering new + pre-existing rows
        gid_to_pk = dict(TaxonomyCategory.objects.values_list("shopify_gid", "pk"))
        parent_updates = []
        for gid, parent_gid in raw_rows:
            parent_pk = gid_to_pk.get(parent_gid)
            if parent_pk is not None:
                parent_updates.append(
                    TaxonomyCategory(pk=gid_to_pk[gid], parent_id=parent_pk)
                )
        TaxonomyCategory.objects.bulk_update(
            parent_updates, ["parent_id"], batch_size=1000
        )
        return len(raw_rows)

    def _load_category_attributes(self, data):
        """Create attribute rows referenced by categories and link them via the M2M."""
        existing = set(TaxonomyAttribute.objects.values_list("shopify_gid", flat=True))
        to_create = []
        seen = set()
        for vertical in data.get("verticals", []):
            for cat in vertical.get("categories", []):
                for attr in cat.get("attributes", []):
                    gid = attr["id"]
                    if gid not in existing and gid not in seen:
                        seen.add(gid)
                        to_create.append(
                            TaxonomyAttribute(
                                shopify_gid=gid,
                                name=attr["name"],
                                handle=attr.get("handle", ""),
                                description=attr.get("description", ""),
                            )
                        )
        TaxonomyAttribute.objects.bulk_create(to_create, batch_size=1000)

        attr_gid_to_pk = dict(
            TaxonomyAttribute.objects.values_list("shopify_gid", "pk")
        )
        cat_gid_to_pk = dict(TaxonomyCategory.objects.values_list("shopify_gid", "pk"))

        through = TaxonomyAttribute.categories.through
        links = []
        link_keys = set()
        for vertical in data.get("verticals", []):
            for cat in vertical.get("categories", []):
                cat_pk = cat_gid_to_pk[cat["id"]]
                for attr in cat.get("attributes", []):
                    attr_pk = attr_gid_to_pk[attr["id"]]
                    key = (attr_pk, cat_pk)
                    if key in link_keys:
                        continue
                    link_keys.add(key)
                    links.append(
                        through(
                            taxonomyattribute_id=attr_pk,
                            taxonomycategory_id=cat_pk,
                        )
                    )
        through.objects.bulk_create(links, ignore_conflicts=True, batch_size=1000)
        return len(link_keys)

    def _load_attribute_values(self, data):
        """Create attribute-value rows from the attributes distribution file."""
        existing = set(
            TaxonomyAttributeValue.objects.values_list("shopify_gid", flat=True)
        )
        attr_gid_to_pk = dict(
            TaxonomyAttribute.objects.values_list("shopify_gid", "pk")
        )
        created = 0
        for attr_def in data.get("attributes", []):
            attr_pk = attr_gid_to_pk.get(attr_def["id"])
            if attr_pk is None:
                self.stdout.write(self.style.WARNING(
                    f"Skipping values for unknown attribute "
                    f"{attr_def['id']} ({attr_def['name']})"
                ))
                continue
            values = []
            for value in attr_def.get("values", []):
                gid = value["id"]
                if gid not in existing:
                    existing.add(gid)  # guard against duplicates within the file
                    values.append(
                        TaxonomyAttributeValue(
                            shopify_gid=gid,
                            attribute_id=attr_pk,
                            name=value["name"],
                            handle=value.get("handle", ""),
                        )
                    )
            created += len(values)
            TaxonomyAttributeValue.objects.bulk_create(
                values, ignore_conflicts=True, batch_size=1000
            )
        return created