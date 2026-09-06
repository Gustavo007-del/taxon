# Fix Plan — Batch Loop Silently Skips/Stops Early

## Context
`shopify-classifier` (Django) has two batch-processing jobs:
`run_text_job` and `run_image_job`, both in `products/tasks.py`. Both loop
over a filtered queryset of "still needs processing" rows, in chunks,
using a **fixed offset** computed from the *original* total count.

Both jobs are affected because they follow the identical pattern.

## The bug
Each queryset filters for status = pending/null (text) or
needs_review/failed (image). As soon as a chunk is processed,
`_persist_text_results` / `_process_image_chunk` changes those rows'
status — which makes them **fall out of the filter immediately**.

The loop, however, still does:
```python
for start in range(0, total, chunk_size):
    chunk = list(qs[start : start + chunk_size])
```
`start` is computed against the *original* `total`, but `qs` is shrinking
underneath it every iteration (already-processed rows disappear from the
filter). The real offset needed drifts further from `start` every chunk,
until `start` overshoots the actual remaining row count. From that point
on, `qs[start:start+chunk_size]` returns an empty list every iteration —
but the `for` loop still runs through all its remaining planned
iterations, logging the same frozen `processed` count each time, then
exits normally with `finish_job()` as if everything completed.

**Net effect: silently processes roughly half the intended rows (or less,
depending on chunk_size/total), then reports success.** No exception, no
error — the run just looks "done" after covering only part of the data.

## Confirmed reproduction (already done — don't need to redo)
Live-simulated against the real imported DB (1,000 products, chunk_size
200, same filter+persist pattern):
```
start=0:   got 200 rows, cumulative processed=200
start=200: got 200 rows, cumulative processed=400
start=400: got 200 rows, cumulative processed=600
start=600: EMPTY chunk (offset overshoot)
start=800: EMPTY chunk (offset overshoot)
TOTAL UNIQUE PRODUCTS ACTUALLY PROCESSED: 600 out of 1000
```
Matches the real-world symptom exactly: a real run on 4,899 products
stalled at 2,499 (`processed 2499/4899` repeated ~13 times, then
`Done. Status breakdown: auto_approved: 2498, needs_review: 1` — only
half the catalog actually got classified).

## The fix
Replace fixed-offset pagination with "always take from the front" —
since finished rows naturally exit the filter, `qs[:chunk_size]` on every
iteration already returns the correct next batch with no offset math
needed. Loop until a chunk comes back empty (or the optional `limit` is
reached).

### `products/tasks.py` — `run_text_job`
Replace:
```python
processed = 0
failed = 0
status_counts = {}
try:
    for start in range(0, total, chunk_size):
        chunk = list(qs[start : start + chunk_size])
        results, chunk_failures = _classify_text_chunk(classifier, chunk, err)
        failed += len(chunk_failures)
        _persist_text_results(
            results, chunk_failures, reclassify=reclassify,
            threshold=threshold, status_counts=status_counts,
        )
        processed += len(chunk)
        update_progress(job, processed, failed)
        log(f"  processed {processed}/{total} (failed {failed})")
except Exception:
    finish_job(job, failed=failed, success=False)
    raise
```
With:
```python
processed = 0
failed = 0
status_counts = {}
try:
    while True:
        take = chunk_size if not limit else min(chunk_size, limit - processed)
        if take <= 0:
            break
        chunk = list(qs[:take])
        if not chunk:
            break
        results, chunk_failures = _classify_text_chunk(classifier, chunk, err)
        failed += len(chunk_failures)
        _persist_text_results(
            results, chunk_failures, reclassify=reclassify,
            threshold=threshold, status_counts=status_counts,
        )
        processed += len(chunk)
        update_progress(job, processed, failed)
        log(f"  processed {processed}/{total} (failed {failed})")
except Exception:
    finish_job(job, failed=failed, success=False)
    raise
```
Also remove the earlier pre-slicing block (no longer needed / would
conflict with re-slicing `qs` inside the loop):
```python
total = qs.count()
if limit:
    qs = qs[:limit]      # <-- remove this line
    total = limit
```
Keep `total = qs.count()` (or `min(qs.count(), limit)` if limit is set)
for reporting/progress purposes only — don't slice `qs` itself.

### `products/tasks.py` — `run_image_job`
Same exact change, same reasoning — replace:
```python
for start in range(0, total, chunk_size):
    chunk = list(qs[start : start + chunk_size])
    chunk_failed = _process_image_chunk(chunk, classifier, threshold, counts, err)
    failed += chunk_failed
    processed += len(chunk)
    update_progress(job, processed, failed)
    log(f"  processed {processed}/{total} (failed {failed})")
```
With the same `while True: take = ...; chunk = list(qs[:take]); if not chunk: break; ...`
pattern, and remove the same `qs = qs[:limit]` pre-slicing above it.

## Verification steps (do these after applying the fix)
1. Re-run the same 1,000-row live simulation shown above (or equivalent)
   — confirm it now reaches `TOTAL UNIQUE PRODUCTS ACTUALLY PROCESSED: 1000 out of 1000`
   with no empty-chunk lines.
2. On the full dataset: `python manage.py classify_products` — confirm
   the log reaches `processed 4899/4899` (not stalling around 2400-2500),
   and `Done. Status breakdown:` counts sum to 4899.
3. Run `python manage.py classify_products` a second time immediately
   after — since everything is now classified, it should report
   "No products to classify." (confirms resume logic still works
   correctly with the new loop).
4. Repeat steps 2-3 for the image pass (`run_image_job` / whatever the
   corresponding management command is) once there are `needs_review`
   rows to process.