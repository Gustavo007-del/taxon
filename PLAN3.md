# Fix Plan — Color Fields & Attribute Matching

## Problems found
1. `Product Color` and `Color Collection` both map to the same DB field
   (`product_color`) — first alias wins, so `Color Collection` (e.g. "White")
   is silently dropped whenever `Product Color` (e.g. "Heathered Weave
   Ivory") is also present.
2. Attribute-value matching uses plain substring search (`value in blob`),
   with no word boundaries — causes false positives (e.g. "Red" matched
   from inside "requi-RED").
3. Combined effect: the real, taxonomy-valid color ("White") never gets
   detected; a fabricated "Red" shows up instead.

## Tasks

- [ ] **`products/models.py`**
  - [ ] Add `color_collection` field to `Product` (`CharField`, blank/default="")
  - [ ] New migration

- [ ] **`products/management/commands/import_products.py`**
  - [ ] Split the alias entry: `product_color` keeps only
        `["product_color", "color", "colour", "product_colour"]`
  - [ ] Add new field `color_collection` with alias `["color_collection"]`
  - [ ] Map both into the `Product` object on import

- [ ] **`products/classifiers/attributes.py`**
  - [ ] Add `color_collection` to `_TEXT_FIELDS` used for `build_text_sources`
  - [ ] Replace substring check with word-boundary regex match:
        `re.search(rf"\b{re.escape(value.lower())}\b", blob)` instead of
        `value.lower() in blob`
  - [ ] (Optional improvement) Check `color_collection` / `product_color`
        directly against the attribute's value list first, before falling
        back to the general text-blob scan — gives a more direct, reliable
        match for color specifically

- [ ] **`products/classifiers/text_classifier.py`**
  - [ ] Add `color_collection` to `TEXT_FIELDS` so it also contributes to
        category-prediction embeddings (minor signal, same as product_color)

- [ ] **Verify**
  - [ ] Re-run `classify_products` (or just attribute detection) on the
        Zoya sofa product — confirm "Color" now shows `White`, not `Red`
  - [ ] Spot-check a few more products with distinct
        `Product Color` vs `Color Collection` values to confirm both survive

## Not in scope
Cosmetic `%%` → `%` typo in the import report — separate, trivial fix,
can be done alongside or later.