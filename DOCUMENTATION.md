# Shopify Product Classifier — Complete Documentation

Comprehensive companion to the shorter `README.md`. It covers **everything
implemented**, the **technologies used**, **how the system works**, and
**step-by-step run instructions**.

> Prototype state: the codebase is complete and statically reviewed, but has
> never been executed (no Python available on the machine it was built on).
> The first run on a real Python machine should follow
> [First-run verification](#first-run-verification).

---

## 1. What was built

A Django web application that:

1. **Imports** a supplier product catalogue (`Product List.xlsx`, 10,000+
   rows) — tolerant of real-world spreadsheet mess.
2. **Classifies** every product into **Shopify's Product Taxonomy**
   (14,606 categories) using local, free models only (no paid API calls).
3. **Detects** the predicted category's **attributes and attribute values**
   (e.g. category *Sofas* → attribute *Color* → value *Grey*) by matching
   the taxonomy's permitted values against product text.
4. **Uses images when available** and still works when they are missing or
   broken (two-pass design: text for everything, images only for the
   low-confidence remainder).
5. Produces a **confidence score**, up to **3 alternative categories**, and
   flags low-confidence rows as **needs review**.
6. Processes in **chunks/batches with progress tracking and resume** —
   designed for 10,000+ products.
7. **Isolates failures** per product (one bad row/image never kills a run).
8. Provides a **review UI** (dashboard / results table / per-product detail)
   and a **JSON API** to view, approve, reject, and override results.

### Two-pass classification

| Pass | Model | When | Cost |
|---|---|---|---|
| 1 · Text | `sentence-transformers/all-MiniLM-L6-v2` | every product | fast (thousands/min on a laptop) |
| 2 · Image | `open_clip` `ViT-B-32` | only rows below the text-confidence bar (or empty-text rows) | slow (downloads + CLIP) — reserved for the ~15–30% text can't decide |

Both passes rank against **precomputed embeddings of every taxonomy
category**, cached on disk (`data/embeddings_cache/`) so re-runs are cheap.

### Task-requirement coverage

| Requirement from the brief | Where it is implemented |
|---|---|
| Import the provided product list | `products/management/commands/import_products.py` |
| Identify Shopify taxonomy category | pass 1 text classifier (+ pass 2 image fallback) |
| Detect category attributes + attribute values | `products/classifiers/attributes.py` → `ClassificationResult.detected_attributes` |
| Products with / without images | pass 2 runs only where images exist; text always runs |
| Missing description / other info | blank-description penalty; empty-text rows defer to images |
| Use title, description, product type, brand, image | all fed into the text blob / image pass |
| Confidence score | `text_confidence`, `image_confidence`, `final_confidence` |
| Alternative categories when confidence low | top-3 `alternatives` JSON on every result |
| Identify manual-review rows | `status = needs_review` (low confidence / disagreement) |
| Batch processing for 10,000+ | chunked runs + `BatchJob` progress; resume-safe |
| Handle invalid images, missing data, errors | per-row try/except isolation → `status = failed`, retried next run |
| UI/API to view, update, approve results | `/dashboard/`, `/results/`, `/results/<id>/` + `/api/*` |

---

## 2. Tech stack

| Layer | Tool | Why |
|---|---|---|
| Backend | Django 5.x | required backend; ORM, admin, management commands |
| API | Django REST Framework | JSON endpoints for the UI / integration |
| Database | MariaDB/MySQL via PyMySQL (SQLite default for dev) | relational; taxonomy hierarchy + FKs |
| xlsx import | pandas + openpyxl | NaN handling, header normalization |
| Numerics | numpy | cosine similarity, matrix ops |
| Text embeddings | sentence-transformers (MiniLM-L6-v2) | free, local, fast |
| Image embeddings | open_clip (ViT-B-32) | free, local fallback pass |
| Image validation | Pillow, requests | open/decode check, download with retry |
| Fuzzy shortcut | rapidfuzz | near-match category names without embeddings |
| Background jobs | Celery + redis (optional; currently background threads) | resumable batch processing at scale |
| Frontend | Django templates + **Tailwind CSS (CDN)** + vanilla JS `fetch()` | no Node/build step |
| Config | python-dotenv (`.env`) | per-machine DB/secret settings |

### requirements.txt (with purpose)

```
Django>=5.2,<6.1               web framework
djangorestframework>=3.15,<4.0 DRF API
PyMySQL>=1.1                   MariaDB/MySQL driver (DB_ENGINE=mysql)
pandas>=2.2, numpy>=1.26,<3.0  spreadsheet + numeric work
openpyxl>=3.1                  xlsx reader for pandas
sentence-transformers>=3.0     text embeddings (pass 1)
torch>=2.3                     engine under transformers / CLIP
rapidfuzz>=3.9                 fuzzy category shortcut
open_clip_torch>=2.24          image/text CLIP model (pass 2)
Pillow>=10.3, requests>=2.32   image download + validation
celery>=5.4, redis>=5.0        optional production batch queue
python-dotenv>=1.0             .env loading
```

Python 3.10+ (3.11/3.12 recommended). ~2 GB free disk for model weights on
first run (PyTorch is the large one).

---

## 3. Repository layout

```
├── README.md / DOCUMENTATION.md
├── requirements.txt · .gitignore · .env(.example) · manage.py
├── config/
│   ├── settings.py          # env-driven; SQLite default, MariaDB via DB_ENGINE=mysql
│   └── urls.py              # admin/ · api/ · review_ui pages at the root
├── taxonomy/
│   ├── models.py            # TaxonomyCategory (tree), TaxonomyAttribute, TaxonomyAttributeValue
│   ├── admin.py
│   ├── embeddings.py        # cached MiniLM full-path + CLIP name vectors of all categories
│   └── management/commands/load_taxonomy.py
├── products/
│   ├── models.py            # Product, ClassificationResult, BatchJob
│   ├── admin.py · batch.py  # BatchJob helpers (start / progress / finish)
│   ├── serializers.py · views.py · urls.py · filters.py   # /api/ endpoints
│   ├── tasks.py             # shared chunked runners (CLI + API + future Celery)
│   ├── classifiers/
│   │   ├── text_classifier.py  # pass 1: fuzzy shortcut + MiniLM top-3
│   │   ├── image_classifier.py # pass 2: CLIP image → category
│   │   ├── image_utils.py      # concurrent download, Pillow validation, cache
│   │   ├── attributes.py       # detect category attributes/values in product text
│   │   └── pipeline.py         # combine text + image scores
│   └── management/commands/
│       ├── import_products.py  classify_products.py  classify_images.py  spot_check.py
├── review_ui/                # Tailwind pages (no build step)
│   ├── views.py · urls.py
│   ├── templates/review_ui/  # base / dashboard / results_list / result_detail
│   └── static/review_ui/app.js
├── scripts/
│   ├── make_sample_data.py   # generates data/Product_List_sample.xlsx (real column layout)
│   └── verify_e2e.sh         # fresh-clone end-to-end check
└── data/
    ├── taxonomy/             # vendored Shopify taxonomy 2026-08 (gzip, ~4 MB)
    └── embeddings_cache/     # .npy caches (gitignored, regenerable)
```

---

## 4. Database schema

Six tables across two apps (`taxonomy`, `products`).

### 4.1 Taxonomy (loaded from Shopify's distribution files)

**TaxonomyCategory** — one node of the taxonomy tree (`parent` self-FK):

| field | notes |
|---|---|
| `shopify_gid` | `unique`; e.g. `gid://shopify/TaxonomyCategory/...` |
| `name` | short name, e.g. `Sofas` |
| `full_path` | `unique`; e.g. `Home & Garden > Furniture > Sofas` |
| `level` | depth (0 = top vertical) |
| `parent` | self-FK `SET_NULL`, `related_name="children"` |

**TaxonomyAttribute** — `shopify_gid` unique, `name`, `handle`,
`description`, and `categories` **M2M → TaxonomyCategory**
(`related_name="attributes"`).

**TaxonomyAttributeValue** — `shopify_gid` unique, `name`, `handle`,
FK `attribute → TaxonomyAttribute` (`related_name="values"`),
`unique_together (attribute, name)`.

Seed totals (Shopify taxonomy **2026-08**, vendored): ~14,606 categories,
~8,200 attribute definitions, ~75,000 values, hierarchy preserved via
`parent`.

### 4.2 Products

**Product** — one spreadsheet row:

| field | notes |
|---|---|
| `product_number` | `unique`; dedupe key |
| `title`, `description`, `bullets`, `materials` | free text (used by classifier) |
| `category_raw`, `sub_category_raw` | the supplier's own category text |
| `product_type`, `collection_name`, `product_color` | extra text signals |
| `brand` | captured when a column exists |
| `image_urls` | JSON list — merged from `Image 1..Image 20` columns |
| `price` | Decimal, nullable |
| `raw_row` | JSON — full original row (insurance) |
| `created_at`, `updated_at` | |

**ClassificationResult** — one per product (`OneToOne`):

| field | notes |
|---|---|
| `product` | OneToOne → Product |
| `predicted_category` | FK → TaxonomyCategory, `SET_NULL` |
| `text_confidence` / `image_confidence` / `final_confidence` | Float, nullable |
| `alternatives` | JSON `[{shopify_gid, name, score}]` (top-3) |
| `detected_attributes` | JSON `[{name, handle, values:[matched], value_count}]` |
| `status` | `pending / auto_approved / needs_review / approved / rejected / failed` |
| `method_used` | `text_only` or `text_plus_image` |
| timestamps | |

**BatchJob** — one classification run:

| field | notes |
|---|---|
| `job_type` | `text` or `image` |
| `status` | `running / completed / failed` |
| `total`, `processed`, `failed` | progress counters (updated per chunk) |
| `options` | JSON of run parameters |
| `started_at`, `finished_at` | |

### 4.3 Migrations

```
taxonomy/migrations/0001_initial.py
products/migrations/0001_initial.py                        # Product
products/migrations/0002_classificationresult.py           # + ClassificationResult
products/migrations/0003_batchjob.py                       # + BatchJob (sync failed choice)
products/migrations/0004_extra_fields_and_detected_attributes.py  # + new Product fields, detected_attributes
```

Hand-written to mirror Django's output. `python manage.py migrate` applies
them; `python manage.py makemigrations --check` confirms no drift.

---

## 5. Taxonomy data & embedding caches

### 5.1 Taxonomy source (vendored, offline)

`data/taxonomy/categories.en.json.gz` + `attributes.en.json.gz` are
Shopify's official release assets
(`github.com/Shopify/product-taxonomy/releases/latest/download/...`),
current version **2026-08**. Vendored so `load_taxonomy` works offline and
reproducibly. `data/taxonomy/README.md` explains refresh via `curl`.

### 5.2 Embedding caches (regenerable, gitignored)

`data/embeddings_cache/` stores two numpy files, each paired with a
metadata JSON that records the **model name** and the exact **ordered
category gid set** used, so the cache invalidates automatically if the
taxonomy or model changes:

| File | Encodes | Used by |
|---|---|---|
| `taxonomy.npy` | MiniLM embeddings of category **full paths** | pass-1 text classifier |
| `clip_taxonomy.npy` | CLIP text embeddings of category **names** | pass-2 image classifier |

Category *names* (not full paths) are used for CLIP because deep full
paths can exceed CLIP's 77-token window.

### 5.3 Downloaded product images

Pass 2 downloads up to 3 images per product into `media/cache/<product_number>/`
(written to `.part` first, then renamed). `media/` is gitignored; valid
cached files are reused on re-runs.

---

## 6. The classification pipeline

### 6.1 Pass 1 — text (`classify_products`, runner `run_text_job`)

For each product:

1. **Fuzzy shortcut.** If `category_raw`/`sub_category_raw` nearly matches a
   taxonomy category name (`rapidfuzz.token_set_ratio ≥ 90`), use it
   directly with `confidence = score/100` — zero embedding cost.
2. **Embedding pass.** Otherwise embed the text blob (`title, description,
   bullets, category_raw, sub_category_raw, brand, materials, product_type,
   collection_name, product_color`) with MiniLM and cosine-rank against the
   cached category vectors. Top-1 becomes the prediction; top-3 are stored.
3. **Missing-info penalty.** If `description` *or* `category_raw` is
   missing, confidence is multiplied by `0.85`.
4. **Status decision** (threshold default `0.65`):
   - `confidence ≥ threshold` → `auto_approved`
   - below threshold, or no prediction (empty text) → `needs_review`
   - exception for a row → `failed` (retried on next run)
5. **Attribute detection.** For every predicted category, load its
   taxonomy attributes + permitted values (2 queries with prefetch) and
   match values (case-insensitive substring) against the product text.
   Stored in `detected_attributes`; up to 10 matched values per attribute.

Batch behavior: chunked (`chunk_size`, default 200); progress pushed to a
`BatchJob` after each chunk; one bad row falls back to per-product
classification so a single row cannot kill the run.

### 6.2 Pass 2 — images (`classify_images`, runner `run_image_job`)

Targets rows whose pass-1 result is `needs_review` or `failed` (or, with
`--all`, every non-manually-reviewed row). Per product:

1. **Fetch** up to 3 image URLs concurrently (10 workers), retry once,
   validate with Pillow (must open/decodes, ≥ 32 px, not 1×1). Broken
   images are skipped, never fatal.
2. **Embed** valid images with CLIP, average the image vectors, cosine-rank
   against cached CLIP text vectors of every category name.
3. **Combine with the text result** (`pipeline.py`):

   | Case | final confidence | status |
   |---|---|---|
   | text and image agree | `min(1.0, avg + 0.1)` | ≥ threshold → `auto_approved`, else `needs_review` |
   | they disagree | `min(text, image)` | always `needs_review` |
   | no text prediction | image score | ≥ threshold → `auto_approved`, else `needs_review`; **image category is adopted** into `predicted_category` |
   | no usable image | keep text score | stays `needs_review` |

   Alternatives are merged (higher score per gid, top-3). `method_used`
   becomes `text_plus_image`. Detected attributes are **recomputed** against
   the final (possibly image-adopted) category.

### 6.3 Statuses at a glance

| Status | Meaning |
|---|---|
| `pending` | imported, never classified |
| `auto_approved` | text (or text+image) confidence ≥ threshold |
| `needs_review` | low confidence / text-image disagreement — human should look |
| `approved` / `rejected` | human decision — **never overwritten** by batch runs |
| `failed` | per-product error — retried on the next run |

### 6.4 Resume & progress

- Without `--reclassify`, pass 1 picks up only products with **no result**
  or a result `pending`/`failed`; pass 2 picks up `needs_review`/`failed`.
- `--reclassify` / `--all` re-run everything **except** rows a human marked
  `approved`/`rejected`.
- A `BatchJob` row is created at start (recording options), updated per
  chunk (`processed`, `failed`), and finished `completed`/`failed`.
- API-triggered runs execute in a **background daemon thread** per job
  (dev-server friendly). The same runners live in `products/tasks.py` and
  are Celery-task-ready: wrap with `@shared_task` for production scale.

---

## 7. Web UI & API reference

### 7.1 Pages (server-rendered, Tailwind via CDN, no build step)

| URL | Page | Purpose |
|---|---|---|
| `/` (and `/results/`) | Results list | filter (status / min confidence / search), badges, per-row approve/reject/set, pagination |
| `/dashboard/` | Dashboard | stat cards, run text/image passes, live progress, recent jobs |
| `/results/<id>/` | Result detail | product info + images + full prediction panel + review actions |
| `/admin/` | Django admin | taxonomy, products, results, batch jobs |

The results forms are plain CSRF-protected POSTs handled by
`review_ui.views.update_result` (approve / reject / set category; setting a
category counts as the review decision → `approved`). The dashboard's
run buttons and progress polling live in
`review_ui/static/review_ui/app.js` (CSRF-aware `fetch`, poll every 2 s).

### 7.2 API endpoints (DRF, same origin — no CORS needed)

**`GET /api/results/`** — paginated list.
Query params: `status` (comma-separated), `min_confidence`, `q`
(product # / title), `limit` (default 100, max 500), `offset`.
Response: `{count, limit, offset, results:[...]}` — each result nests
`product` and `predicted_category` summaries and includes
`detected_attributes` and `alternatives`.

**`GET /api/results/<id>/`** — one result.

**`PATCH /api/results/<id>/`** — partial update, e.g.
```json
{"status": "approved"}
{"predicted_category_id": 123}
{"status": "needs_review"}
```
`status` is validated against its choices; confidence fields are
read-only via the API.

**`POST /api/batch/run/`** — start a classification run (202 + job):
```json
{"job_type": "text", "limit": 100, "fuzzy_threshold": 90.0, "confidence_threshold": 0.65}
{"job_type": "image", "workers": 10, "threshold": 0.65}
```
Options: `fuzzy, fuzzy_threshold, confidence_threshold, batch_size,
chunk_size, reclassify, limit, workers, threshold, all_results`.
Booleans are coerced properly (`"false"` is not truthy); numeric params
validated before the thread starts.

**`GET /api/batch/<id>/`** — progress:
```json
{"id": 3, "job_type": "text", "status": "running", "total": 100,
 "processed": 40, "failed": 0, "options": {...}, "started_at": "...", "finished_at": null}
```

> Prototype caveat: no authentication on the API or update forms — fine
> locally; add DRF session/permission classes before anything public.

---

## 8. Spreadsheet import mapping

The importer finds the spreadsheet automatically (`Product List.xlsx` or
`Product_List.xlsx` in the project root or `data/`; override with
`--file`). Headers are normalized (lowercase, spaces→underscores) and
aliased to model fields; the **real supplier file's 48 columns** map as:

| Spreadsheet column(s) | Model field |
|---|---|
| `Product Number` | `product_number` |
| `Product Name` | `title` |
| `Product Description` | `description` |
| `Product Category` | `category_raw` |
| `Product Sub Category` | `sub_category_raw` |
| `Bullets` | `bullets` |
| `Collection Name` | `collection_name` |
| `Product Color`, `Color Collection` | `product_color` |
| `Materials` | `materials` |
| `MSRP` (or `Item Cost`/`MAP`/`Price`) | `price` |
| `Image 1` … `Image 20` | merged into `image_urls` (ordered) |
| everything else (`Model Number`, dimensions, weights, `Product URL`, …) | preserved in `raw_row` |

Normalization: NaN/empty → `""`/`None`, whitespace stripped, prices cleaned
of currency/commas, URL cells split on commas/semicolons/newlines.
Duplicate `product_number` rows (in DB or repeated in file) are skipped and
logged. `--dry-run` parses and reports without writing.

---

## 9. Step-by-step run instructions

### 9.1 Prerequisites

- Python 3.10+ on the PATH
- ~2 GB free disk (first run downloads MiniLM + CLIP weights + PyTorch)
- MariaDB/MySQL only if you want it — SQLite works out of the box

### 9.2 Setup

```bash
# 1) virtualenv + dependencies
python -m venv .venv
# Windows (Git Bash):   source .venv/Scripts/activate
# Linux / macOS:        source .venv/bin/activate
pip install -r requirements.txt

# 2) environment file
cp .env.example .env        # defaults = SQLite + DEBUG on
# Optional MariaDB/MySQL: set DB_ENGINE=mysql, DB_NAME, DB_USER,
# DB_PASSWORD, DB_HOST, DB_PORT in .env

# 3) schema
python manage.py migrate
python manage.py makemigrations --check   # should report "No changes"

# 4) (optional) Django admin account
python manage.py createsuperuser
```

### 9.3 Load the taxonomy (one-time, offline)

```bash
python manage.py load_taxonomy          # ~14.6k categories, 8.2k attributes, 75k values
python manage.py load_taxonomy --reset  # wipe and re-seed (never needed normally)
```

### 9.4 Import products

```bash
# Try the generated sample first (150 rows, real column layout, edge cases):
python scripts/make_sample_data.py
python manage.py import_products --file data/Product_List_sample.xlsx

# Real catalogue — drop 'Product List.xlsx' in the project root (or data/):
python manage.py import_products              # auto-detected
python manage.py import_products --dry-run    # report only
python manage.py import_products --file /path/to/file.xlsx --chunk-size 1000
```

### 9.5 Classify

```bash
# Pass 1 (text) — try a slice first; the first run downloads MiniLM and
# builds data/embeddings_cache/taxonomy.npy (~minutes for 14.6k categories).
python manage.py classify_products --limit 100
python manage.py classify_products            # everything remaining (resumable)
python manage.py classify_products --reclassify   # re-run all except manual decisions

# Inspect results from the terminal
python manage.py spot_check --limit 20
python manage.py spot_check --status needs_review

# Pass 2 (images) — fallback for needs_review/failed rows only.
# First run downloads CLIP ViT-B-32 + builds clip_taxonomy.npy.
python manage.py classify_images --limit 10
python manage.py classify_images              # all needs_review/failed rows
python manage.py classify_images --all --limit 50 --workers 10
```

### 9.6 Review in the browser

```bash
python manage.py runserver
# Dashboard  http://localhost:8000/dashboard/   (run passes + live progress)
# Results    http://localhost:8000/results/      (filter, approve/reject/set)
# Detail     http://localhost:8000/results/<id>/ (full view + override)
# Admin      http://localhost:8000/admin/
# API        http://localhost:8000/api/results/?status=needs_review
```

API examples:

```bash
curl "localhost:8000/api/results/?status=needs_review&limit=5"
curl "localhost:8000/api/results/?q=EEI-1010"
curl -X PATCH localhost:8000/api/results/1/ -H 'Content-Type: application/json' \
     -d '{"status": "approved"}'
curl -X POST localhost:8000/api/batch/run/ -H 'Content-Type: application/json' \
     -d '{"job_type": "text", "limit": 100}'
curl localhost:8000/api/batch/1/
```

### 9.7 Full end-to-end verification (fresh clone)

```bash
scripts/verify_e2e.sh                 # check → migrations → taxonomy → import → classify → spot_check
scripts/verify_e2e.sh --with-images   # additionally runs a 5-product image pass
```

---

## 10. How it was built / design decisions

| Decision | Why |
|---|---|
| Local embedding models instead of LLM/API | zero per-call cost, private data, fast enough for 10k+ |
| Text pass for all + image fallback | images are the expensive part (download + CLIP); only low-confidence rows need them |
| Precomputed, cache-keyed category vectors | classification becomes one matmul; re-runs are cheap |
| Fuzzy shortcut before embeddings | near-matching supplier categories skip the model entirely |
| Threshold + `needs_review` + alternatives | honest about low-confidence rows; reviewer sees the top-3 |
| Substring attribute-value matching | predictable and explainable for a prototype (vs another model) |
| Chunked transactions + per-row failure isolation | one bad URL/row can't abort 10,000 products |
| `BatchJob` row per run | progress UI + resume boundary without extra infra |
| Same runners for CLI and API (`products/tasks.py`) | one implementation, no drift; Celery-ready later |
| Server-rendered templates + small JS | consistent with the prototype; no Node build step |
| Tailwind via CDN | fast iteration; production would use the Tailwind CLI to purge CSS |
| SQLite default, MariaDB switch via `.env` | zero-friction dev; target DB production-ready |

---

## 11. Troubleshooting & production notes

- **First run downloads models** (MiniLM ~90 MB, CLIP ViT-B-32 ~350 MB,
  plus PyTorch). Subsequent runs reuse `data/embeddings_cache/*.npy`.
- **Broken image URLs** are normal in real catalogues — they are skipped
  and counted; rows keep `needs_review`.
- **MariaDB**: set `DB_ENGINE=mysql` + credentials in `.env` (PyMySQL
  driver included). SQLite is single-writer; use MariaDB for concurrent
  use or large runs.
- **Background runs** currently use daemon threads — fine for the dev
  server and one-off runs. For production scale, wrap
  `products.tasks.run_text_job` / `run_image_job` in Celery `@shared_task`
  (celery/redis are already in requirements).
- **No authentication** anywhere — dev prototype only.
- **Admin autocomplete** on `predicted_category` needs the search field on
  `TaxonomyCategory` (already configured).
- **Windows note**: files carry LF; Git may warn about CRLF conversion.
  Commands above assume Git Bash / bash (POSIX syntax).
- **If `makemigrations --check` reports changes**: a migration drifted from
  the models (migrations are hand-written). Rebuild with
  `python manage.py makemigrations taxonomy products` after reviewing.
