# Fix Plan — Product Import Column Mapping

## Problem
Dry-run against the real `Product_List.xlsx` confirms:
- `Product Category` → not aliased → **100% dropped**
- `Product Sub Category` → not aliased → **100% dropped**
- `Image 1`...`Image 20` → no per-column handling → **100% dropped, 0 images imported**
- `Bullets` → not in `TEXT_FIELDS` → never used in classification

Impact: fuzzy-shortcut and missing-info penalty logic get no category signal,
and the entire Phase 4 image-classification fallback has nothing to run on.

## Tasks

- [ ] **`products/management/commands/import_products.py`**
  - [ ] Add `"product_category"` to `category_raw` aliases
  - [ ] Add `"product_sub_category"` to `sub_category_raw` aliases
  - [ ] Add image-column collector: gather all `image_1`...`image_20`
        (or any `image_N`) columns per row into one ordered list, replacing
        the current single-column `image_urls` alias lookup
  - [ ] Add `"bullets"` as a new mapped field (alias: `"bullets"`)

- [ ] **`products/models.py`**
  - [ ] Add `bullets` field to `Product` (`TextField`, blank/default="")
  - [ ] New migration for the added field

- [ ] **`products/classifiers/text_classifier.py`**
  - [ ] Add `"bullets"` to `TEXT_FIELDS` so it's included in the embedding blob

- [ ] **Verify**
  - [ ] Re-run `import_products --dry-run` against the real file — confirm
        `missing_category` and `missing_images` drop from 100% to near 0%
  - [ ] Re-import for real, re-run `classify_products`, spot-check that
        image-based Phase 4 fallback now actually executes on low-confidence rows

## Not in scope for this fix
`Model Number`, `Collection Name`, `Color Collection`, `Product Color`,
`Set Includes`, `Product Weight`, `Product Dimensions` — remain unused in
classification (still captured in `raw_row` as a fallback), can be revisited
later if classification quality needs further improvement.