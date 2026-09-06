# Python Developer Online Test — Written Answers

Answers to all 15 questions, grounded in the working prototype in this
repository (`README.md` for the quick start, `DOCUMENTATION.md` for the
full architecture, schema, and run steps). Where an answer references
"the implementation", it points at real files/behaviour in the codebase.

---

## 1. Approach for automatically identifying the Shopify category, attributes, and values

**Approach.** Two local-embedding passes plus a rule-based attribute/value
detector:

1. **Fuzzy shortcut first.** Many supplier rows carry their own
   category text (`Product Category`, `Product Sub Category`). We compare
   it against all 14,606 taxonomy category names with `rapidfuzz`
   (`token_set_ratio`, cutoff 90) and take the match directly when it
   clears the bar — zero model cost and very accurate for well-formed
   supplier categories.
2. **Embedding pass otherwise.** The product text (title, description,
   bullets, raw category/sub-category, brand, materials, product type,
   collection, color) is embedded with `all-MiniLM-L6-v2` and cosine-ranked
   against **precomputed embeddings of every taxonomy category's full
   path**, stored as a cached matrix in `data/embeddings_cache/taxonomy.npy`.
   Classification of N products is then one matrix multiplication.
3. **Category attributes and values.** Shopify's taxonomy files attach
   attributes to categories and attribute values to attributes. For the
   predicted category we load its attributes and their permitted values and
   match each value against the product text with whole-word,
   case-insensitive matching (word boundaries prevent false positives such
   as "Red" inside "requi-RED"); color attributes are additionally checked
   directly against the product's dedicated `product_color` /
   `color_collection` fields for an exact value match. Matches are stored
   per result in `detected_attributes`
   (`products/classifiers/attributes.py`). A *category alone* is rarely
   enough for e-commerce enrichment — the attributes (color, material,
   pattern, …) are what a listing actually needs, so we surface both.

**Why this design.** The task rules out paid per-call LLM/API services for
10,000+ products. Local embeddings give:
- deterministic, explainable ranking (cosine similarity to taxonomy paths);
- batch throughput (hundreds–thousands of products/minute on a laptop) with
  no per-request latency or cost;
- a natural "top-3 alternatives" output for review;
- offline operation once weights are cached.

CLIP text vectors are precomputed for the same reason on the image side
(`clip_taxonomy.npy`), keeping the image pass to one embedding per image
plus a dot product.

---

## 2. A product with a title but no description and no image

The product still gets a real classification attempt, and the system says
so honestly:

1. The text blob is *not* empty (title + any raw category/brand/etc. are
   present), so the embedding pass runs and returns a top category with a
   cosine confidence.
2. Missing `description` (and/or missing `category_raw`) applies a
   **0.85 confidence penalty** (`MISSING_INFO_PENALTY` in
   `text_classifier.py`) — the system models that it has less evidence.
3. The final status depends on the penalised score against the 0.65
   threshold: at/above → `auto_approved`; below → `needs_review`.
4. Because it lacks description, the row stays in the queue for the
   **image pass**, which downloads whatever images exist and, if they agree
   with the text category, boosts confidence (`avg + 0.1`); if it still
   can't decide, the row remains `needs_review` for a human, with the
   top-3 alternatives shown.

So: title-only products are handled by the same pipeline with a lower
confidence and are routed to exactly the right reviewer state instead of
crashing or being silently guessed. Attribute detection still runs on the
fields that do exist (title, category, brand, materials).

---

## 3. Using product images to improve classification

Images run in a **second, targeted pass** rather than for every product:

- Rows that qualify are `needs_review`/`failed` from pass 1 (an explicit
  "no description" product is the archetypal candidate).
- Up to 3 image URLs per product are downloaded concurrently
  (`ThreadPoolExecutor`, 10 workers, one retry), validated with Pillow
  (must decode, ≥ 32 px, not a 1×1 placeholder), and cached under
  `media/cache/<product_number>/`.
- Valid images are embedded with **open_clip ViT-B-32**, averaged per
  product, and cosine-ranked against **CLIP text embeddings of every
  taxonomy category name** (`taxonomy/embeddings.py` → `clip_taxonomy.npy`).
- The image prediction is combined with the text prediction
  (`products/classifiers/pipeline.py`):
  - **Agree** → `final = min(1.0, avg + 0.1)` → typically auto-approved.
  - **Disagree** → `final = min(text, image)`, forced `needs_review`, both
    top-3 lists merged into `alternatives`.
  - **No text prediction** → the image category is *adopted* (also written
    to `predicted_category`, not just the score).
  - **No usable image** → text result is kept, still `needs_review`.

Why CLIP: it is trained on image–text pairs, so image embeddings and the
category-name text embeddings live in the same space and are directly
comparable — no per-category image dataset or fine-tuning is needed. Why a
second pass only: downloading and embedding images is the expensive part;
reserving it for the ~15–30% of rows text can't decide keeps the whole
10k pipeline fast.

---

## 4. Processing 10,000+ products efficiently (batching/background)

The design principle is: **never one-row-at-a-time through a model or an
HTTP API, and never block the web server.**

- **Vectorised text pass.** Category vectors are precomputed once; per
  batch of products we encode ~64 at a time and score the whole batch with
  one matrix multiply. 10,000 products ≈ minutes on a laptop.
- **Chunked DB writes.** Runs iterate a queryset in chunks
  (text: 200 rows, image: 50 rows), classify in memory, then use
  `bulk_create`/`bulk_update` per chunk inside one transaction —
  thousands of rows are written with a handful of statements.
- **Progress + resume state.** Every run creates a `BatchJob` row
  (`job_type`, `total`, `processed`, `failed`, run `options`) updated after
  each chunk — the job is resumable and observable.
- **Per-row isolation.** If a whole chunk throws, it is retried
  product-by-product; individual failures are recorded (`status = failed`)
  and retried next run — one bad row never aborts 10,000.
- **Triggering.** The CLI commands and the API
  (`POST /api/batch/run/`) share the same runners in `products/tasks.py`.
  API-triggered runs execute in a background thread per job and the
  dashboard polls `GET /api/batch/{id}/` for a live progress bar.
- **Celery-ready.** The runners are pure functions of `(job_id, options)`:
  swapping the daemon thread for a Celery worker (already in
  `requirements.txt`) is a wrapper change, which is the production path for
  horizontal scaling and guaranteed retries.

---

## 5. Storing the Shopify taxonomy and its hierarchy

Three relational tables mirror the taxonomy's own structure:

- **`TaxonomyCategory`** — `shopify_gid` (unique), `name`, `full_path`
  (unique, denormalised `"Home & Garden > Furniture > Sofas"`), `level`,
  and a **self-referencing `parent` FK** (`related_name="children"`) that
  preserves the tree exactly as Shopify defines it (each node carries its
  `parent_id` in the source files).
- **`TaxonomyAttribute`** — gid, name, handle, description, and a
  **ManyToMany → `TaxonomyCategory`** (an attribute like *Color* applies to
  thousands of categories).
- **`TaxonomyAttributeValue`** — gid, name, handle, FK to attribute
  (`unique_together (attribute, name)`).

Why this shape:
- The self-FK is the simplest faithful representation of Shopify's
  `parent_id` data and supports parent/child traversal and UI breadcrumbs.
- `full_path` is denormalised because the classifier matches against it
  and the review UI displays it — no recursive join on every read.
- Attribute–category is a genuine many-to-many in the source data, so it is
  modelled as one.

Loading (`load_taxonomy`) is idempotent bulk work: gids dedupe, creates
happen via `bulk_create`, parent pointers and M2M links are resolved from
gid→pk maps, and the whole load is one transaction; `--reset` wipes first
when a full re-seed is wanted. Source files are vendored gzip JSON
(Shopify taxonomy 2026-08) so seeding is offline and reproducible
(~14,606 categories, ~8,200 attributes, ~75,000 values). We deliberately
did **not** add an MPTT/treebeard materialised path: this workload is
read-mostly top-down lookup, not subtree aggregation, so the extra
maintenance cost isn't justified.

---

## 6. Calculating / determining the confidence score

Confidence is **cosine similarity in embedding space**, with explicit
penalties for missing evidence, and is computed per pass:

- **Text pass:** `confidence = cosine(embed(product_text), embed(category_full_path))`
  on the top-ranked category (0–1). Missing description or raw category →
  × 0.85. The fuzzy shortcut's confidence is the normalised fuzzy score.
- **Image pass:** `confidence = cosine(mean(CLIP image vectors), CLIP text vector of category name)`.
- **Combined (`pipeline.py`):**
  - text + image agree → `min(1.0, (text + image)/2 + 0.1)`;
  - disagree → `min(text, image)`;
  - text absent → image score;
  - no image → text score.
- **Status mapping** against a configurable threshold (default 0.65):
  `≥ threshold → auto_approved`, `< threshold → needs_review`.

Why this is defensible: cosine similarity has a principled interpretation
(top-1 relative to all 14,606 categories), the 0.85 penalty quantifies
missing information, agreement/disagreement between two independent
modalities is a strong, explainable signal, and the threshold is a single
tunable knob. The score is surfaced per component
(`text_confidence`, `image_confidence`, `final_confidence`) so a reviewer
sees *why* a number is what it is. We avoid calibrating to absolute
"probability" claims — we report rank-based similarity and let the review
workflow absorb borderline rows.

---

## 7. When the system cannot confidently identify a single category

Three layered responses (all implemented):

1. **Show alternatives, don't fake a single answer.** The classifier always
   returns a **top-3** (`alternatives` JSON: gid, name, score). Forcing a
   single low-confidence category is worse than showing the plausible set.
2. **Mark for manual review.** Score below threshold → `needs_review`; the
   review UI is sorted for exactly this queue and shows the alternatives
   side-by-side with one-click "set this category" actions. Text/image
   **disagreement** also forces `needs_review` even if each pass alone was
   confident — disagreement is treated as a red flag, not averaged away.
3. **Give reviewers everything to decide.** The detail page shows the
   product text, images, full path of the prediction, all three
   alternatives with scores, and the detected attribute matches; the API
   exposes the same via `PATCH /api/results/{id}/`.

If a category is *entirely* missing (empty text + no images), the result is
stored with no prediction and flagged `needs_review`, and an optional
image pass can rescue it later when images exist.

---

## 8. Broken or inaccessible images without stopping the batch

The image pass treats images as **skippable by design** and isolates
failures at several levels:

- **Per-URL:** download has a 5 s timeout and one retry; a partial download
  is written to a `.part` file and renamed only on success, so a corrupt
  download can never masquerade as a valid cached image.
- **Per-file:** every downloaded file is validated with Pillow — it must
  open *and* decode, be ≥ 32 px, and not be a 1×1 placeholder.
  UnidentifiedImageError/OSError → rejected, not raised.
- **Per-product:** if none of a product's URLs produce a valid image, that
  product simply stays at its pass-1 result (`needs_review`); counters
  track `no_images` so the operator can see the volume.
- **Per-row:** any unexpected exception while classifying one product marks
  *that row* `status = failed` (logged with the product number and error)
  and the chunk continues — failures are recorded, not propagated.

Because each chunk is committed independently and the run is resumable
(§11), even a wholesale crash mid-run only re-does the unfinished part.
`image_utils.py` implements all of this (`fetch_product_images`,
`download_image`, `validate_image`).

---

## 9. API and database structure design

**Database** (see also §5, `DOCUMENTATION.md` §4):

- `taxonomy`: `TaxonomyCategory` (hierarchical), `TaxonomyAttribute`,
  `TaxonomyAttributeValue`.
- `products`: `Product` (unique `product_number`, all text fields used for
  classification, `image_urls` JSON list, `price`, `raw_row` JSON
  insurance); `ClassificationResult` — **OneToOne → Product** (a product
  has exactly one outcome), FK → predicted category, per-pass and final
  confidences, `alternatives` JSON, `detected_attributes` JSON, `status`,
  `method_used`; `BatchJob` with counters + run options JSON.

OneToOne for the result (rather than fields on `Product`) keeps import and
classification decoupled and makes "classify me next" a clean outer join.
JSON for `alternatives`/`detected_attributes` is right for prototype
flexibility (document-shaped, read-mostly, never joined on).

**API (DRF, `/api/…`):**

| Endpoint | Purpose |
|---|---|
| `GET /api/results/` | list + filter: `status` (comma-sep), `min_confidence`, `q`, `limit` (≤500), `offset`; nests product + category summaries |
| `GET/PATCH /api/results/{id}/` | view; edit `predicted_category_id` or `status` (approved/rejected/needs_review) |
| `POST /api/batch/run/` | `{job_type: text\|image, ...options}` → 202 + job id; background thread runs it |
| `GET /api/batch/{id}/` | progress `{status, total, processed, failed}` |

Statuses: `pending → auto_approved | needs_review | failed`, then human
`approved | rejected` (never overwritten by batches). Honest prototype
caveat: no authentication — for production add DRF session/token auth and
permissions before exposing publicly.

---

## 10. Optimising when an external AI/API request takes ~2 s each

The implemented system avoids this class of problem entirely — local
embeddings have no per-request 2 s penalty. But the same architecture
answers the question directly, and two options are worth separating:

1. **If the model is local (what we built):** the bottleneck is encoding,
   not request latency. We batch encodings (MiniLM `batch_size=64`, CLIP
   in chunks of 256) and score thousands of products against all categories
   with matrix multiplication — total for 10,000 products is minutes.
2. **If an external API at ~2 s/request is unavoidable:** the fixes are
   concurrency and batching, not a faster loop:
   - **Parallelism.** A worker pool (threads/async or Celery with N
     workers) — 20 concurrent workers turns 10,000 × 2 s = 5.6 h sequential
     into ~17 min ideal; the plan's throughput math should be
     `(count × latency) / concurrency`.
   - **Batch endpoints.** Many providers accept arrays of items per request
     (e.g. one call for 20 products), which multiplies throughput further.
   - **Cache aggressively.** Never re-ask for a product that already has a
     result (resume filter does exactly this) and memoise identical inputs
     (same category text, same image URL).
   - **Pipeline overlap.** Fetch/embed in one stage while the previous
     stage's results are being written, so DB I/O never idles the model.
   - **Queue + progress + resume.** Push work to a durable queue
     (Celery + Redis) so a crash costs only in-flight items; `BatchJob`
     already records per-chunk progress and the codebase's runners are the
     Celery tasks.

With either option the DB writes are chunked and vectorised so storage is
never the serial bottleneck.

---

## 11. Resume after a failure at, say, product 6,000 of 10,000

Resume is built into the state model, not a checkpoint file:

- Every row's processing state is persisted: products with **no**
  `ClassificationResult`, or a result still `pending` or `failed`, are
  "not done".
- On every run **without** `--reclassify`, pass 1 selects exactly the not
  done rows (`Product` left-joined to results, filtered to
  null/pending/failed); pass 2 selects `needs_review`/`failed` rows. So a
  run that died at 6,000 simply re-runs and picks up from row 6,001+ in
  O(remaining), not O(10,000) — already-classified rows are untouched.
- Processing is chunked with a **per-chunk transaction**; `BatchJob`
  progress (`processed`, `failed`) is updated after every chunk, giving an
  operator a precise restart point and observability.
- Manual decisions are protected: human `approved`/`rejected` rows are
  excluded even under `--reclassify`/`--all`, so a resume/re-run can never
  clobber review work.
- Per-product failures are stored as `status = failed` (with the error
  logged) and are *precisely* what the next run picks up — failed rows are
  retried automatically, nothing else is re-done.

(If the "failure" is a whole worker/process crash rather than a row error,
the same semantics hold because nothing is committed until a chunk
completes and uncommitted chunks remain "not done".)

---

## 12. Technologies/frameworks and why

- **Django 5.x** — required and the right call: ORM, admin, migrations,
  management commands, and an easy path to MariaDB.
- **Django REST Framework** — clean JSON API for the review UI/integration
  with serializers, validation, and permissions-ready.
- **MariaDB** (SQLite for local dev) — relational needs (hierarchy, FKs,
  status queries at 10k scale); PyMySQL keeps the driver pure-Python.
- **pandas + openpyxl** — the provided xlsx has 48 messy columns (image
  URLs split over 20 columns, currency prices, NaNs); pandas normalisation
  is the pragmatic choice.
- **sentence-transformers (all-MiniLM-L6-v2)** — text embeddings: free,
  local, fast, and semantically strong enough for category matching.
- **open_clip (ViT-B-32)** — image↔text similarity in one space without any
  image training data or fine-tuning.
- **numpy + rapidfuzz** — matrix scoring; cheap fuzzy shortcut that skips
  the model for clean supplier categories.
- **Pillow + requests** — image download/validation with graceful failure.
- **Celery + Redis** — declared for the production batch path (runners are
  already Celery-task-shaped); the prototype itself uses chunked commands +
  background threads so it runs with zero extra infrastructure.
- **Django templates + Tailwind (CDN) + vanilla `fetch()`** — the brief
  allows any frontend; this keeps one codebase, no Node build step, and
  matches the prototype's scope. Swapping to a React/Vite SPA later is
  easy because the UI is a thin client of the DRF API.

Everything is chosen to be free, local, and horizontally simple — no
paid API, no heavy infra, no build pipeline — which fits a 10,000-row
prototype while leaving production upgrade paths (Celery, auth, purged
Tailwind build).

---

## 13. High-level architecture

```
                        ┌────────────────────────────────────────────┐
  xlsx (48 cols, 20 img │  Django app                                 │
  columns, 10k rows)    │                                            │
        │               │  import_products ──► Product ────────────┐ │
        ▼               │                    ▲                      │ │
  Supplier catalogue    │                    │ raw row / text       │ │
                        │  Shopify taxonomy (vendored gz 2026-08)   │ │
                        │        │ load_taxonomy                    │ │
                        │        ▼                                  │ │
                        │  TaxonomyCategory ◄── ClassificationResult │ │
                        │  TaxonomyAttribute ◄───────┘ (OneToOne→P) │ │
                        │  TaxonomyAttributeValue                    │ │
                        │        ▲                                   │ │
                        │  embeddings_cache/*.npy                   │ │
                        │  (MiniLM full paths, CLIP names)          │ │
                        └──────────┬────────────────────────────────┘ │
                                   │                                  │
   Pass 1 text (all products) ─────┤─ TextClassifier (fuzzy → MiniLM) │
   Pass 2 image (needs_review) ────┤─ ImageClassifier (CLIP)          │
        media/cache images         │  combine_results (pipeline)      │
                                   │                                  │
                        ┌──────────▼───────────────────┐              │
                        │ run_text_job / run_image_job │  BatchJob    │
                        │ (chunks, bulk_create/update, │  progress    │
                        │  resume, per-row isolation)  │              │
                        └──────────┬───────────────────┘              │
                                   │                                  │
                 CLI commands ─────┴──── POST /api/batch/run/ (thread)
                                        GET  /api/batch/{id}/ (poll)
                                        GET/PATCH /api/results/…​
                                             │
                        ┌────────────────────▼────────────────────┐
                        │ review UI: /dashboard/ /results/        │
                        │ /results/<id>/ (Tailwind + fetch) + /admin/
                        └─────────────────────────────────────────┘
```

**Data flow in one paragraph:** `import_products` maps the supplier
spreadsheet onto `Product` rows (images merged from `Image 1..20`, currency
and NaNs normalised, duplicates skipped). `load_taxonomy` seeds the
hierarchy from Shopify's own distribution files. `classify_products`
(pass 1) embeds every product against the cached taxonomy matrix and
stores category, top-3, confidence, status, and detected attributes;
`classify_images` (pass 2) does the same for images on the
`needs_review`/`failed` remainder and merges both scores. All runs are
chunked, tracked by `BatchJob`, resumable, and isolated per row. Results
are reviewed through server-rendered Tailwind pages or the DRF API.

---

## 14. Development-effort estimate for a production-ready application

**Assumptions.** One experienced full-stack Python developer; Django +
DRF backend; the taxonomy ingestion and embedding-cache infrastructure as
built; no custom model training (pre-trained MiniLM/CLIP); review UI
server-rendered (no SPA); MariaDB; Celery+Redis for batches; includes
testing/QA but not long-running operational tuning of the review workflow.

Task-wise breakdown (hours):

| # | Task | Hours |
|---|---|---|
| 1 | Requirements analysis, DB design, environment/CICD skeleton | 6–10 |
| 2 | Taxonomy ingestion (loader, idempotency, hierarchy, refresh tooling) | 8–12 |
| 3 | Product import (xlsx normalisation, dedupe, schema validation, audit report) | 6–10 |
| 4 | Text classification pipeline (embeddings, cache, scoring, fuzzy shortcut) | 10–16 |
| 5 | Image classification pipeline (download/validate/cache, CLIP, score fusion) | 10–16 |
| 6 | Batch orchestration: Celery tasks, queueing, progress, resume, retries, monitoring hooks | 10–16 |
| 7 | DRF API (results/batch endpoints, filters, pagination, auth/permissions, rate limits) | 8–14 |
| 8 | Review UI (dashboard, results list, detail, batch controls, styling) | 12–18 |
| 9 | Attribute/value detection tuning + tests | 6–10 |
| 10 | Testing: unit (scorers, pipeline rules, importer), integration (end-to-end on real file), load test 10k | 12–18 |
| 11 | Deployment, docs, monitoring/alerting, secrets, backup | 8–12 |
| 12 | Buffer for unknowns, review iterations, demo polish | 10–15 |
| | **Total** | **~106–167 h (~3–4.5 weeks full-time)** |

(The working prototype in this repo represents roughly the first half —
tasks 1–5 plus a minimal 6–8 — on the order of 50–60 h.)

**Dependencies.** PyTorch/transformers downloads and CPU vs GPU (GPU
optional; CPU is fine at this scale); MariaDB instance; Redis + Celery
broker for the production batch path; a stable vendor for image URLs
(many provided URLs will 404 — that's expected and handled).

**Major risks.** (1) Classification accuracy — mitigated by the needs-review
workflow, alternatives, and threshold tuning on real labelled data.
(2) Taxonomy refresh cadence — Shopify ships new versions; the loader and
embedding cache are version-keyed so refreshes are safe. (3) Image-URL
rot/availability — mitigated by caching, validation, and graceful
skips. (4) Scale surprises at 10k+ (DB write contention, model memory) —
mitigated by chunking, bulk writes, Celery, and MariaDB. (5) Scope creep in
the review UI — keep it a thin client of the API.

---

## 15. Practical task — what the prototype demonstrates

A working prototype is implemented in this repository
(`README.md` quick start, `DOCUMENTATION.md` full reference). It
demonstrates, on the sample catalogue (`scripts/make_sample_data.py`
generates 150 rows in the real 48-column layout, deliberately laced with
edge cases — duplicates, blank descriptions, missing categories, empty-text
rows, broken image URLs, non-ASCII/emoji, NaN cells, currency prices):

- full import of the real supplier layout (incl. `Image 1..Image 20`
  merging and `MSRP`);
- taxonomy load → text classification → optional image fallback →
  `spot_check`/review;
- category + **detected attributes/values** per product;
- confidence scores, top-3 alternatives, `needs_review` routing,
  resume-safe resumable batches, per-row failure isolation;
- review UI (dashboard with live batch progress, results table, detail
  page) and a JSON API for the same.

Run it end-to-end with:

```bash
python -m venv .venv && source .venv/Scripts/activate   # (Windows Git Bash)
pip install -r requirements.txt
python manage.py migrate
python manage.py load_taxonomy
python scripts/make_sample_data.py
python manage.py import_products --file data/Product_List_sample.xlsx
python manage.py classify_products --limit 100
python manage.py spot_check --limit 10
python manage.py runserver        # → /dashboard/ · /results/ · /api/results/
```

For a fully automated check on a fresh machine:
`scripts/verify_e2e.sh` (optionally `--with-images`).

> Status note: the codebase is complete and statically reviewed but has not
> yet been executed in an environment with Python; the first-run steps
> above (notably `makemigrations --check` before `migrate`) are the
> remaining verification.
