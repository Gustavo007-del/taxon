"""Import products from the supplier spreadsheet (Product List.xlsx).

Usage:
    python manage.py import_products [--file path] [--chunk-size 500]
    python manage.py import_products --dry-run   # report only, no writes

The importer normalizes column headers (lowercase, spaces/dashes become
underscores) and tolerates common aliases. It matches the real supplier
file's layout: Product Number / Product Category / Product Sub Category /
Product Name / Product Description / Bullets / Collection Name /
Product Color / Materials / MSRP / Image 1..Image 20 / ... Columns it
does not recognize are preserved verbatim in each product's `raw_row`.

NaN cells become empty values, image URL cells are split into lists, and
spreadsheets that spread images across many columns ("Image 1".."Image N")
are merged into one ordered image_urls list. Products are bulk-created in
chunks of ~500; duplicate product_numbers (already in the DB or repeated
in the file) are skipped and logged.
"""
import math
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from products.models import Product

# Normalized column name -> accepted aliases from the source spreadsheet.
# The first alias present in the file wins for each field.
COLUMN_ALIASES = {
    "product_number": ["product_number", "product_no", "item_number", "item_no", "sku"],
    "title": ["title", "name", "product_name", "item_title"],
    "description": ["description", "product_description", "long_description", "details"],
    "category_raw": [
        "category_raw",
        "product_category",
        "category",
        "primary_category",
        "department",
    ],
    "sub_category_raw": [
        "sub_category_raw",
        "subcategory_raw",
        "product_sub_category",
        "sub_category",
        "subcategory",
        "secondary_category",
    ],
    "brand": ["brand", "brand_name", "manufacturer", "vendor"],
    "materials": ["materials", "material", "fabric", "fabric_content"],
    "product_type": ["product_type", "type", "item_type"],
    "bullets": ["bullets", "bullet", "bullet_points", "highlights"],
    "collection_name": ["collection_name", "collection", "product_collection"],
    "product_color": [
        "product_color",
        "color",
        "colour",
        "product_colour",
        "color_collection",
    ],
    "image_urls": ["image_urls", "image_url", "images", "image", "photo_urls"],
    "price": ["price", "unit_price", "sale_price", "retail_price", "msrp"],
}

_IMAGE_COLUMN_RE = re.compile(r"^image\s*\d+$", re.IGNORECASE)
_PRICE_CLEAN_RE = re.compile(r"[^0-9.\-]")


def _is_na(value):
    if value is None:
        return True
    if isinstance(value, float):
        return math.isnan(value)
    return False


def _text(value):
    """Coerce a cell to a stripped string; NaN/None become ''."""
    if _is_na(value):
        return ""
    return str(value).strip()


def _price(value):
    """Coerce a cell to Decimal, tolerating currency symbols/commas; NaN -> None."""
    if _is_na(value):
        return None
    cleaned = _PRICE_CLEAN_RE.sub("", str(value)).strip()
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _image_urls(value):
    """Coerce a cell to a list of image URLs (splits on comma/semicolon/newline)."""
    if _is_na(value):
        return []
    if isinstance(value, list):
        return [str(u).strip() for u in value if str(u).strip()]
    parts = re.split(r"[,;\n]", str(value))
    return [p.strip() for p in parts if p.strip()]


def _jsonable(value):
    """Make a cell JSON-serializable (NaN -> None, exotic types -> str)."""
    if _is_na(value):
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def image_columns(df):
    """Original headers like 'Image 1'..'Image 20', ordered numerically."""
    cols = [
        col
        for col in df.columns
        if isinstance(col, str) and _IMAGE_COLUMN_RE.match(col.strip())
    ]
    return sorted(cols, key=lambda c: int(re.sub(r"\D", "", c)))


def normalize_columns(df):
    """Map source headers onto Product field names using COLUMN_ALIASES."""
    rename = {}
    normalized = {
        str(col).strip().lower().replace(" ", "_").replace("-", "_"): col
        for col in df.columns
    }
    for field, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                rename[normalized[alias]] = field
                break
    return df.rename(columns=rename)


class Command(BaseCommand):
    help = "Import products from the supplier spreadsheet (Product List.xlsx)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            default=None,
            help="Path to the spreadsheet (default: 'Product List.xlsx' or "
            "'Product_List.xlsx' in the project root or data/).",
        )
        parser.add_argument("--chunk-size", type=int, default=500)
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and report only; do not write anything to the database.",
        )

    def handle(self, *args, **options):
        path = self._resolve_file(options["file"])
        self.stdout.write(f"Reading {path} ...")

        df = self._read_spreadsheet(path)
        image_cols = image_columns(df)
        if image_cols:
            self.stdout.write(f"Found {len(image_cols)} image columns to merge: {image_cols[0]}..{image_cols[-1]}")
        df = normalize_columns(df)

        if "product_number" not in df.columns:
            raise CommandError(
                "No product-number column found. Normalized columns present: "
                + ", ".join(sorted(str(c) for c in df.columns))
            )

        products, stats = self._build_products(df, image_cols)
        self._print_report(len(df), stats)

        if options["dry_run"]:
            self.stdout.write("Dry run — nothing written.")
            return

        existing = set(Product.objects.values_list("product_number", flat=True))
        seen = set()
        to_create = []
        skipped = 0
        for product in products:
            if product.product_number in existing or product.product_number in seen:
                skipped += 1
                self.stdout.write(f"  skipping duplicate product_number: {product.product_number}")
                continue
            seen.add(product.product_number)
            to_create.append(product)

        chunk_size = options["chunk_size"]
        for start in range(0, len(to_create), chunk_size):
            Product.objects.bulk_create(to_create[start : start + chunk_size])
        self.stdout.write(self.style.SUCCESS(
            f"Imported {len(to_create)} products ({skipped} duplicates skipped, "
            f"chunk size {chunk_size})."
        ))

    # ------------------------------------------------------------------ #

    def _resolve_file(self, given):
        if given:
            path = Path(given)
        else:
            candidates = []
            for root in (settings.BASE_DIR, settings.BASE_DIR / "data"):
                candidates.append(root / "Product List.xlsx")
                candidates.append(root / "Product_List.xlsx")
            for candidate in candidates:
                if candidate.exists():
                    path = candidate
                    break
            else:
                raise CommandError(
                    "'Product List.xlsx' not found in the project root or data/; "
                    "pass --file explicitly."
                )
        if not path.is_file():
            raise CommandError(f"File not found: {path}")
        return path

    def _read_spreadsheet(self, path):
        if path.suffix.lower() == ".csv":
            return pd.read_csv(path)
        return pd.read_excel(path)

    def _build_products(self, df, image_cols):
        products = []
        stats = {"total": len(df), "missing_description": 0, "missing_images": 0, "missing_category": 0}
        for _, row in df.iterrows():
            urls = _image_urls(row.get("image_urls")) if "image_urls" in row else []
            for col in image_cols:
                urls.extend(_image_urls(row.get(col)))
            product = Product(
                product_number=_text(row.get("product_number")),
                title=_text(row.get("title")),
                description=_text(row.get("description")),
                category_raw=_text(row.get("category_raw")),
                sub_category_raw=_text(row.get("sub_category_raw")),
                brand=_text(row.get("brand")),
                materials=_text(row.get("materials")),
                product_type=_text(row.get("product_type")),
                bullets=_text(row.get("bullets")),
                collection_name=_text(row.get("collection_name")),
                product_color=_text(row.get("product_color")),
                image_urls=urls,
                price=_price(row.get("price")),
                raw_row={str(k): _jsonable(v) for k, v in row.items()},
            )
            if not product.description:
                stats["missing_description"] += 1
            if not product.image_urls:
                stats["missing_images"] += 1
            if not product.category_raw:
                stats["missing_category"] += 1
            products.append(product)
        return products, stats

    def _print_report(self, total, stats):
        pct = lambda n: f"{(100.0 * n / total):.1f}%" if total else "0.0%"
        self.stdout.write("--- import report ---")
        self.stdout.write(f"total rows:              {total}")
        self.stdout.write(f"missing description:     {stats['missing_description']} ({pct(stats['missing_description'])}%)")
        self.stdout.write(f"missing images:          {stats['missing_images']} ({pct(stats['missing_images'])}%)")
        self.stdout.write(f"missing category_raw:    {stats['missing_category']} ({pct(stats['missing_category'])}%)")
        self.stdout.write("---------------------")
