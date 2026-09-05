# Shopify Product Classifier — Freebuff Desktop prototype

A Django prototype that classifies products from a supplier spreadsheet
(`Product_List.xlsx`) into **Shopify's Product Taxonomy** (14,606 categories),
using only free/local models — no paid LLM/API calls. Two-pass design:

1. **Pass 1 — text** (`all-MiniLM-L6-v2`): fast, cheap, covers every product.
2. **Pass 2 — image** (`open_clip` ViT-B-32): only the low-confidence rows
   from pass 1 get their images downloaded and classified.

Why two passes: text embedding of 5,000 products takes seconds on a laptop;
image classification requires downloading images and running CLIP, which is
far slower. The image pass is reserved for the ~15–30% of products text can't
decide, and the two scores are combined with a documented rule (agreement →
boost, disagreement → manual review).

## Repo structure

```
├── config/            # Django project: settings, urls, wsgi/asgi
├── taxonomy/          # Shopify taxonomy models + load_taxonomy command
│   ├── models.py      # TaxonomyCategory (tree), TaxonomyAttribute, TaxonomyAttributeValue
│   ├── embeddings.py  # cached text (MiniLM) + CLIP embeddings of all categories
│   └── management/commands/load_taxonomy.py
├── products/
│   ├── models.py      # Product, ClassificationResult, BatchJob
│   ├── batch.py       # BatchJob helpers (start / progress / finish)
│   ├── tasks.py       # shared chunked runners (CLI + API both call these)
│   ├── classifiers/
│   │   ├── text_classifier.py    # pass 1: fuzzy shortcut + embedding top-3
│   │   ├── image_classifier.py   # pass 2: CLIP image -> category
│   │   ├── image_utils.py        # concurrent download, validation, caching
│   │   └── pipeline.py           # combine text + image scores
│   ├── serializers.py / views.py / urls.py   # /api/ endpoints
│   └── management/commands/
│       ├── import_products.py    # xlsx -> Product (Phase 2)
│       ├── classify_products.py  # pass 1 (Phase 3)
│       ├── classify_images.py    # pass 2 (Phase 4)
│       └── spot_check.py         # print a sample for manual review
├── review_ui/         # plain-HTML review table at / (no build step)
├── scripts/
│   ├── make_sample_data.py       # generates data/Product_List_sample.xlsx
│   └── verify_e2e.sh             # fresh-clone end-to-end check
└── data/
    ├── taxonomy/      # vendored Shopify taxonomy 2026-08 (gzip, ~4 MB)
    └── embeddings_cache/  # .npy caches, regenerable (gitignored)
```

## Requirements

- Python 3.10+ (3.11/3.12 recommended)
- ~2 GB free disk for model weights (MiniLM ~90 MB, CLIP ViT-B-32 ~350 MB,
  PyTorch itself is the big one)
- MariaDB/MySQL optional — SQLite is the default for local dev

## Setup

```bash
python -m venv .venv
# Windows (Git Bash):   source .venv/Scripts/activate
# Linux / macOS:        source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # edit DB settings if using MariaDB
python manage.py migrate    # creates db.sqlite3 (SQLite) by default
```

To use MariaDB/MySQL instead, set `DB_ENGINE=mysql` plus `DB_NAME`,
`DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` in `.env` (PyMySQL is the
pure-Python driver; no native client library needed).

## Load the taxonomy (one-time)

The Shopify taxonomy source is vendored in `data/taxonomy/` so this works
offline. To refresh it later, follow `data/taxonomy/README.md`.

```bash
python manage.py load_taxonomy          # seeds 14,606 categories, 8k+ attributes, 75k values
python manage.py load_taxonomy --reset  # wipe and re-seed
```

## Import products

The importer tolerates messy spreadsheets: normalized header aliases, NaN
cells, currency-formatted prices, comma-separated image URLs, duplicate
product numbers (skipped + logged), and non-ASCII text.

```bash
# Try it on the generated sample (150 rows with deliberate edge cases):
python scripts/make_sample_data.py
python manage.py import_products --file data/Product_List_sample.xlsx

# Real file: drop Product_List.xlsx in the project root (or data/) and run:
python manage.py import_products              # finds it automatically
python manage.py import_products --dry-run    # report only, nothing written
```

## Classify

**CLI** (recommended for big runs):

```bash
python manage.py classify_products --limit 100   # pass 1 on a sample first
python manage.py classify_products               # pass 1 on everything remaining
python manage.py classify_images --limit 10      # pass 2 fallback (downloads CLIP weights first run)
python manage.py classify_images                 # pass 2 on all needs_review/failed rows
```

Both commands create a `BatchJob`, update progress after every chunk, and
support **resume**: a re-run only picks up rows that are still unprocessed,
`pending`, `needs_review`, or `failed`. Manually approved/rejected results
are never overwritten. Per-product failures are recorded as
`status=failed` and retried on the next run instead of killing the batch.

**API** (background thread, returns immediately — poll for progress):

```bash
curl -X POST localhost:8000/api/batch/run/ -H 'Content-Type: application/json' \
     -d '{"job_type": "text", "limit": 100}'
curl localhost:8000/api/batch/1/            # {"status": "running", "processed": 50, "total": 100, ...}
```

`job_type` is `text` or `image`; optional options mirror the CLI flags
(`fuzzy`, `fuzzy_threshold`, `confidence_threshold`, `batch_size`,
`chunk_size`, `reclassify`, `limit`, `workers`, `threshold`, `all_results`).

## Review

```bash
python manage.py runserver
```

- **`http://localhost:8000/`** — review table: filters (status / min
  confidence / search), status badges, top-3 alternatives, per-row
  Approve / Reject / Set-category buttons (plain HTML forms).
- **`http://localhost:8000/admin/`** — full Django admin (taxonomy,
  products, results, batch jobs).
- **API**:
  - `GET /api/results/?status=needs_review&min_confidence=0.4&q=&limit=&offset=`
  - `GET /api/results/{id}/` · `PATCH /api/results/{id}/` — edit category
    (`{"predicted_category_id": 123}`), approve/reject (`{"status": "approved"}`)
  - `GET /api/batch/{id}/` — progress
- **Spot-check** from the terminal:

```bash
python manage.py spot_check --limit 20
```

## End-to-end verification (fresh clone)

```bash
scripts/verify_e2e.sh            # check -> migrate -> load_taxonomy -> import -> classify -> spot_check
scripts/verify_e2e.sh --with-images   # also runs a 5-product image pass (downloads CLIP weights)
```

## Status model

| Status | Meaning |
|---|---|
| `pending` | imported, not classified yet |
| `auto_approved` | text (or text+image) confidence ≥ threshold |
| `needs_review` | low confidence — the image pass / a human should look |
| `approved` / `rejected` | human decision; never overwritten by batch runs |
| `failed` | per-product error; retried on the next run |

Confidence combining (`products/classifiers/pipeline.py`): same category
from both passes → `min(1.0, avg + 0.1)`; different categories → the lower
score and forced `needs_review` with both top-3 lists stored as
`alternatives`; no text prediction → the image result is adopted.

## Known caveats

- First runs download model weights (MiniLM, then CLIP) and build the
  category-embedding caches in `data/embeddings_cache/` — subsequent runs
  reuse them.
- `POST /api/batch/run/` runs in a background thread — fine for the dev
  server. For production-scale batches, wire Celery (celery/redis are
  already in `requirements.txt`; the runners in `products/tasks.py` are
  designed to be wrapped in `@shared_task`).
- The review API and forms have **no authentication** — dev prototype only.
- SQLite is single-writer; use MariaDB (`DB_ENGINE=mysql`) for concurrent
  use or large runs.