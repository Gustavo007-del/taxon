#!/usr/bin/env bash
# Fresh-clone end-to-end verification (Phase 7).
# Assumes a venv is active with requirements.txt installed (see README "Setup").
#
# Usage:
#   scripts/verify_e2e.sh                 # full run without the image pass
#   scripts/verify_e2e.sh --with-images   # also runs a 5-product image pass
#
# Exit codes: 0 = all steps passed; non-zero = first failing step.
set -euo pipefail

PY=python
if command -v py >/dev/null 2>&1; then
  PY=py
fi

step() { echo; echo "==> $1"; }

step "1/9 Django system check"
$PY manage.py check

step "2/9 migrations up to date (hand-written migrations must match models)"
$PY manage.py makemigrations --check --dry-run

step "3/9 apply migrations"
$PY manage.py migrate

step "4/9 load Shopify taxonomy (idempotent)"
$PY manage.py load_taxonomy

step "5/9 generate sample spreadsheet"
$PY scripts/make_sample_data.py

step "6/9 import sample products"
$PY manage.py import_products --file data/Product_List_sample.xlsx

step "7/9 text classification on a small sample"
$PY manage.py classify_products --limit 100

step "8/9 spot-check 10 results"
$PY manage.py spot_check --limit 10

if [[ "${1:-}" == "--with-images" ]]; then
  step "9/9 optional: image pass on up to 5 products (downloads CLIP weights on first run)"
  $PY manage.py classify_images --limit 5
else
  step "9/9 skipped image pass (pass --with-images to include it)"
fi

echo
echo "E2E verification passed."