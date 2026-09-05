# Shopify product taxonomy data (vendored)

These are Shopify's official product-taxonomy distribution files, pulled
from the GitHub release assets of
[Shopify/product-taxonomy](https://github.com/Shopify/product-taxonomy).
They are vendored (gzip-compressed) so the prototype seeds its database
fully offline and reproducibly.

| File | Contents | Source |
|---|---|---|
| `categories.en.json.gz` | Category tree: id, name, full path, parent, level, attributes per category | `https://github.com/Shopify/product-taxonomy/releases/latest/download/categories.en.json.gz` |
| `attributes.en.json.gz` | Attribute definitions with their permitted values | `https://github.com/Shopify/product-taxonomy/releases/latest/download/attributes.en.json.gz` |

Current version: **2026-08** (check the `version` field inside either file).

## How they were fetched

```bash
curl -L https://github.com/Shopify/product-taxonomy/releases/latest/download/categories.en.json.gz -o categories.en.json.gz
curl -L https://github.com/Shopify/product-taxonomy/releases/latest/download/attributes.en.json.gz -o attributes.en.json.gz
```

## How they are used

```bash
python manage.py load_taxonomy                 # idempotent load
python manage.py load_taxonomy --reset         # wipe and re-seed
```