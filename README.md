# Shopify Product Classifier — Freebuff Desktop prototype

A Django prototype that classifies products from a supplier spreadsheet
(`Product List.xlsx`) into **Shopify's Product Taxonomy** (14,606 categories),
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
│   │   ├── attributes.py         # detect category attributes + values in product text
│   │   └── pipeline.py           # combine text + image scores
│   ├── serializers.py / views.py / urls.py   # /api/ endpoints
│   └── management/commands/
│       ├── import_products.py    # xlsx -> Product (Phase 2)
│       ├── classify_products.py  # pass 1 (Phase 3)
│       ├── classify_images.py    # pass 2 (Phase 4)
│       └── spot_check.py         # print a sample for manual review
├── frontend/          # React SPA (Vite + react-router): the main UI
│   ├── src/pages/     # Dashboard, Results List, Result Detail
│   ├── src/components/  # badges, tooltips, icons, skeletons, onboarding modal
│   └── src/api.js     # fetch() wrapper for the /api/ endpoints
├── review_ui/         # classic server-rendered fallback (dashboard, results, detail)
│   ├── views.py / urls.py          # + serves the built SPA at / and /app/
│   ├── templates/review_ui/        # base, dashboard, results_list, result_detail
│   └── static/review_ui/app.js     # fetch(): run batch + progress polling
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

cp .env.example .env        # edit DB settings with MariaDB credentials
python manage.py makemigrations
python manage.py migrate    
```

## Load the taxonomy (one-time)

The Shopify taxonomy source is vendored in `data/taxonomy/` so this works
offline. To refresh it later, follow `data/taxonomy/README.md`.

```bash
python manage.py load_taxonomy          # seeds 14,606 categories, 8k+ attributes, 75k values
python manage.py load_taxonomy --reset  # wipe and re-seed
```

## Import products

```bash
# if using different product list sheet:
python manage.py import_products --file data/Product_List_sample.xlsx

# Real file: drop 'Product List.xlsx' (or Product_List.xlsx) in the project, sheet name is sensitive so give it as mentioned or else use the above method using --file:
# root or data/, then:
python manage.py import_products              # finds it automatically
python manage.py import_products --dry-run    # report only, nothing written
```

## Classify

**CLI** (recommended for big runs):

```bash
python manage.py classify_products               # pass 1 on everything remaining
python manage.py classify_images --limit 10      # pass 2 fallback (downloads CLIP weights first run)
python manage.py classify_images                 # pass 2 on all needs_review/failed rows
```
#After this run the server
python manage.py runserver

The image pass needs real pretrained CLIP weights (open_clip without an
explicit checkpoint silently builds a **randomly-initialized** model whose
scores are meaningless — always resolved via `taxonomy/embeddings.py`).
First run downloads them from Hugging Face. If that python download is
slow/throttled, seed the checkpoint once with curl instead:

```bash
bash scripts/fetch_clip_checkpoint.sh   # resumable; ~580 MB into media/cache/clip/
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

## Review UI

```bash
python manage.py runserver
```

The main frontend is a **React SPA** (Vite + react-router) built in
`frontend/` and served by Django from the same origin. The site root **`/`**
is the SPA — no prefix needed:

- **`http://localhost:8000/`** — SPA dashboard: stat cards with icons,
  **Run text pass / Run image pass** buttons with an inline spinner + live
  progress bar (polling `GET /api/batch/{id}/`), recent batch jobs.
- **`http://localhost:8000/results`** — filterable results table: status
  dropdown, **min-confidence slider**, search, per-row Approve / Reject /
  Override actions, tooltips + "ⓘ" hints on every column, pagination.
- **`http://localhost:8000/results/{id}/`** — product info + image gallery
  beside the prediction panel (category, text/image/final confidence shown
  as **0–100%**, alternatives with scores, detected attributes) with
  approve / reject / override controls.
- Confidences render as percentages (≥75% green, 50–74% amber, <50% red).
  A first-visit welcome modal explains the pages (dismissible, "don't show
  again" option). Loading states use skeletons; empty states are friendly.


Local dev can run two ways.

python manage.py runserver serves the app at http://localhost:8000, including the API and the built frontend.
npm run dev in frontend/ runs the React dev server at http://localhost:5173, which is faster for frontend edits.
Both show the same app. When editing React code, use the Vite dev server on 5173. For everything else, or when you want the Django-integrated version, use 8000.

Build / dev for the SPA (Node 20+; a portable Node can live in a gitignored
`.nodejs/` folder):

```bash
cd frontend
npm install
npm run build            # outputs frontend/dist, served by Django at /static/
npm run dev              # Vite on :5173, proxies /api and /media to Django :8000
```

The **classic server-rendered pages are still available** (no build step,
rollback path) under `/legacy/dashboard/`, `/legacy/results/`,
`/legacy/results/{id}/`, plus `/admin/`. Old `/app/...` bookmarks redirect
to the root equivalents. If `frontend/dist` is missing, `/` falls back to
the classic dashboard instead of erroring.

**API** (same origin as the pages, so no CORS setup):
- `GET /api/stats/` — dashboard summary counts (products, by-status,
  avg confidence, recent jobs)
- `GET /api/results/?status=needs_review&min_confidence=0.4&q=&limit=&offset=`
- `GET /api/results/{id}/` · `PATCH /api/results/{id}/` — edit category
  (`{"predicted_category_id": 123}`), approve/reject (`{"status": "approved"}`)
- `GET /api/categories/?gids=...` · `?q=...` — resolve taxonomy categories
  for override dropdowns / pickers
- `POST /api/batch/run/` (`{"job_type": "text"|"image", ...}`) ·
  `GET /api/batch/{id}/` — progress

**Spot-check** from the terminal:

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

**Category attributes & values**: for every classified product the app
also detects the predicted category's taxonomy attributes and which of
their values actually appear in the product's text (title, description,
bullets, category columns, materials, collection, color). Stored as
`ClassificationResult.detected_attributes`, surfaced in the review table
and in `GET /api/results/` — matches the task's "detect relevant category
attributes and attribute values" requirement.

## Known caveats

- First runs download model weights (MiniLM, then CLIP) and build the
  category-embedding caches in `data/embeddings_cache/` — subsequent runs
  reuse them. A CLIP checkpoint seeded via `scripts/fetch_clip_checkpoint.sh`
  (or a `CLIP_PRETRAINED` env var pointing at a local file) is picked up
  automatically and makes the image pass work offline too.
- `POST /api/batch/run/` runs in a background thread — fine for the dev
  server. For production-scale batches, wire Celery (celery/redis are
  already in `requirements.txt`; the runners in `products/tasks.py` are
  designed to be wrapped in `@shared_task`).
- The review API and forms have **no authentication** — dev prototype only.
-  use MariaDB (`DB_ENGINE=mysql`) for concurrent
  use or large runs.