# Shopify Product Classifier — Full Build Plan

A Django prototype that classifies products from `Product_List.xlsx` into
Shopify's Product Taxonomy (category + attributes), using only free/local
models (no paid LLM/API calls). Two-pass design: fast text classification
for all products, image classification only as a fallback for low-confidence
cases.

---

## 1. Tech Stack & Why

| Purpose | Tool | Why |
|---|---|---|
| Web framework | Django | Required/standard for backend prototype |
| API layer | Django REST Framework | Clean endpoints for review UI |
| Database | MariaDB (SQLite for local dev) | Structured relational data, hierarchy support |
| Data import | pandas | Clean handling of 5,000-row xlsx, NaN detection, filtering |
| Numeric ops | numpy | Underlies embeddings + cosine similarity |
| Text embeddings | sentence-transformers (`all-MiniLM-L6-v2`) | Free, local, fast, good for product text |
| Image embeddings | open_clip | Free, local CLIP implementation, fallback pass only |
| Image validation (optional) | OpenCV / Pillow | Detect corrupt/blank images before wasting a CLIP call |
| Background jobs | Celery + Redis (or chunked mgmt commands) | Batch processing without blocking, resumable |
| Frontend | Django templates | Simple review/approve table, no build step needed |

---

## 2. Repo Structure
```
shopify-classifier/
├── README.md
├── requirements.txt
├── .gitignore
├── manage.py
├── config/                          # Django settings, urls, celery.py
├── taxonomy/
│   ├── models.py                    # TaxonomyCategory, TaxonomyAttribute, TaxonomyAttributeValue
│   ├── management/commands/load_taxonomy.py
│   └── embeddings.py                # pre-embed + cache category vectors
├── products/
│   ├── models.py                    # Product, ClassificationResult, BatchJob
│   ├── management/commands/import_products.py
│   ├── classifiers/
│   │   ├── text_classifier.py
│   │   ├── image_classifier.py
│   │   ├── image_utils.py           # download, validate, cache images
│   │   └── pipeline.py              # two-pass orchestration + confidence combine
│   ├── serializers.py
│   ├── views.py
│   ├── urls.py
│   └── tasks.py                     # Celery tasks
├── review_ui/
│   └── templates/review_ui/results_list.html
├── media/cache/                     # downloaded product images
└── data/embeddings_cache/           # cached taxonomy embeddings (npy files)
```

---

## 3. Data Models (design detail)

**taxonomy.TaxonomyCategory**
- `id`, `name`, `full_path` (e.g. "Home & Garden > Furniture > Sofas")
- `parent` (self FK, nullable)
- `shopify_gid` (original taxonomy ID from source data)

**taxonomy.TaxonomyAttribute** / **TaxonomyAttributeValue**
- Attribute: `name` (e.g. "Color"), linked to categories
- Value: `attribute` FK, `value` (e.g. "Red")

**products.Product**
- Mirrors spreadsheet columns: `product_number`, `title`, `description`,
  `category_raw`, `sub_category_raw`, `brand`, `materials`, `image_urls`
  (JSON list), `price`, etc.
- Keep a `raw_row` JSON field too — cheap insurance against missed columns

**products.ClassificationResult**
- `product` FK (OneToOne or FK if re-runs are kept as history)
- `predicted_category` FK → TaxonomyCategory
- `text_confidence`, `image_confidence`, `final_confidence` (floats)
- `alternatives` (JSON — top-3 candidate categories + scores)
- `status`: `pending / auto_approved / needs_review / approved / rejected`
- `method_used`: `text_only / text_plus_image`

**products.BatchJob**
- `id`, `started_at`, `finished_at`, `total`, `processed`, `failed`,
  `status: running/completed/failed`

---

## 4. Phase-by-Phase Tasks

### Phase 1 — Foundation (est. 4–6 hrs)
- [ ] `django-admin startproject config .`
- [ ] Create `taxonomy` and `products` apps
- [ ] Configure DB in `.env` (MariaDB creds; SQLite fallback flag for local dev)
- [ ] Write `.gitignore` (venv, `__pycache__`, `.env`, `media/`, `*.npy`)
- [ ] Draft `requirements.txt` (django, djangorestframework, pandas, numpy,
      sentence-transformers, open_clip_torch, torch, pillow, celery, redis,
      python-dotenv, openpyxl)
- [ ] Build `TaxonomyCategory`/`TaxonomyAttribute` models + migrations
- [ ] Get Shopify's taxonomy source (likely a GitHub JSON/TSV — check the
      test doc's reference link) and write `load_taxonomy` command to parse
      and seed it, preserving hierarchy

### Phase 2 — Product Import (est. 2–3 hrs)
- [ ] Build `Product` model + migration
- [ ] `import_products` command:
  - Read xlsx with `pandas.read_excel()`
  - Normalize column names, strip whitespace
  - Replace `NaN` with `None`/empty consistently
  - Bulk-create in chunks of ~500 (`bulk_create`) for speed
  - Skip/log duplicate `product_number`
- [ ] Print a post-import report: total rows, % missing description,
      % missing images, % missing category

### Phase 3 — Text Classification, Pass 1 (est. 5–7 hrs)
- [ ] `taxonomy/embeddings.py`: load `all-MiniLM-L6-v2` once, embed every
      taxonomy category's `full_path` (+ description if available), save to
      `data/embeddings_cache/taxonomy.npy` so it's not recomputed each run
- [ ] `text_classifier.py`:
  - Build product text blob: `title + description + category_raw +
    sub_category_raw + brand + materials`
  - Batch-encode products (batch size 32–64) with `model.encode()`
  - Cosine similarity (numpy dot product on normalized vectors) against all
    taxonomy vectors — get top-3 matches per product
  - Confidence = top-1 similarity score; apply penalty (e.g. ×0.85) if
    description or category_raw was empty
- [ ] Optional shortcut: fuzzy-match `category_raw`/`sub_category_raw`
      directly against taxonomy names first (e.g. `rapidfuzz`) — if a
      near-exact match exists, use it as a high-confidence shortcut and skip
      embedding comparison for that product
- [ ] Write results into `ClassificationResult` (bulk insert)

### Phase 4 — Image Classification, Pass 2 fallback (est. 5–7 hrs)
- [ ] Query `ClassificationResult` where `text_confidence < THRESHOLD`
      (e.g. 0.65) — expect ~15–30% of products
- [ ] `image_utils.py`:
  - Concurrent download (e.g. `concurrent.futures.ThreadPoolExecutor`,
    10–20 workers), timeout ~5s, retry once, skip on failure
  - Optional: Pillow/OpenCV check — image opens, isn't 1x1 placeholder,
    isn't corrupt — before spending a CLIP call on it
- [ ] `image_classifier.py`:
  - Load `open_clip` model once
  - Embed each valid image, average embeddings if multiple images per
    product, cosine-similarity against taxonomy embeddings (image-text or
    image-image depending on what taxonomy reference data you use)
- [ ] Combine scores in `pipeline.py`:
  - Same category from both → boost confidence (e.g. avg + 0.1, capped at 1.0)
  - Different categories → take the lower confidence, force `needs_review`,
    store both as alternatives
- [ ] Update `ClassificationResult.final_confidence`, `method_used`, `status`

### Phase 5 — Batch Orchestration & Resumability (est. 3–4 hrs)
- [ ] `BatchJob` model + creation at start of a run
- [ ] Chunk processing: process products in batches of e.g. 200, updating
      `BatchJob.processed` after each chunk (visible progress)
- [ ] Resume logic: a new run for the same job only queries
      `ClassificationResult.status = pending` or `failed`
- [ ] Wrap each product/chunk in try/except; log failures with product id
      and reason, mark `status=failed`, continue rest of batch
- [ ] (Optional) Wire into Celery: `classify_batch` task dispatches
      per-chunk subtasks so it doesn't block a web request

### Phase 6 — API + Review UI (est. 5–8 hrs)
- [ ] DRF serializers for `Product` + `ClassificationResult`
- [ ] Endpoints:
  - `GET /api/results/?status=needs_review&min_confidence=0.4`
  - `GET /api/results/{id}/`
  - `PATCH /api/results/{id}/` — edit category / approve / reject
  - `POST /api/batch/run/` — kick off classification on unclassified products
  - `GET /api/batch/{id}/` — progress (`processed/total`)
- [ ] Simple template (`results_list.html`): table with product title,
      predicted category, confidence, status badge, filter dropdown, and an
      inline "approve"/"edit category" action (can be plain HTML forms —
      no need for React for a prototype)

### Phase 7 — Testing & Submission Polish (est. 3–4 hrs)
- [ ] Run on a small sample (~100–200 rows) first, verify end-to-end before
      running all 5,000
- [ ] Manually spot-check 15–20 classified products for sanity
- [ ] Handle edge cases explicitly: broken image URLs, blank descriptions,
      duplicate product numbers, non-UTF8/special characters in text
- [ ] Write `README.md`:
  - Setup steps (`venv`, `pip install -r requirements.txt`, `.env`,
    `migrate`, `load_taxonomy`, `import_products`, `runserver`)
  - How to trigger classification (`POST /api/batch/run/` or a management
    command `classify_products`)
  - Architecture summary + a note on the two-pass design and why
- [ ] Fresh-clone test: clone repo into a new folder, follow your own README
      exactly, confirm it works with no hidden local state
- [ ] `git init`, commit, push to your existing GitHub repo URL

---

## 5. Suggested Build Order (fastest path to a visible demo)
1. Phase 1 + 2 — get the DB and data in
2. Phase 3 — first end-to-end classification working (text-only)
3. Phase 6 (minimal) — a results list you can actually look at
4. Phase 4 — add image fallback for low-confidence cases
5. Phase 5 — batching/resumability for full 5,000-row scale
6. Phase 7 — cleanup, README, push

---

## 6. Effort Estimate
| Phase | Hours |
|---|---|
| 1. Foundation + taxonomy loader | 4–6 |
| 2. Product import | 2–3 |
| 3. Text classification | 5–7 |
| 4. Image classification fallback | 5–7 |
| 5. Batch/resumability | 3–4 |
| 6. API + review UI | 5–8 |
| 7. Testing, README, polish | 3–4 |
| **Total** | **~27–39 hrs** |

---

## 7. Key Risks / Assumptions
- Shopify's taxonomy source data may need cleanup/parsing before loading —
  check its exact format (JSON/TSV) before writing the loader
- Local models trade some accuracy for zero cost — expect a meaningful
  "needs manual review" bucket, and that's fine to state explicitly
- Some image URLs in the spreadsheet will likely be broken/expired —
  pipeline must degrade gracefully (skip, don't crash)
- MariaDB assumed as the target DB; SQLite is fine for local development
- OpenCV is optional (image validity checks only) — not a hard dependency
  unless you want that extra robustness layer
