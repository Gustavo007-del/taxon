#!/usr/bin/env bash
# Seed the open_clip ViT-B-32 pretrained checkpoint locally.
#
# open_clip needs explicit pretrained weights — without `pretrained=` it
# silently builds a RANDOMLY-initialized model whose similarity scores are
# meaningless. Normally open_clip fetches the checkpoint from Hugging Face
# on first use (cached under ~/.cache/huggingface), but its python downloader
# can be slow/throttled. This script fetches the same file with curl
# (resumable: re-run it after an interruption and it continues) into
# media/cache/clip/, which taxonomy/embeddings.py auto-detects and uses
# instead — the image-classification fallback then works fully offline too.
#
# Usage:  bash scripts/fetch_clip_checkpoint.sh
set -euo pipefail

DEST="$(cd "$(dirname "$0")/.." && pwd)/media/cache/clip/open_clip_pytorch_model.bin"
URL="https://huggingface.co/laion/CLIP-ViT-B-32-laion2B-s34B-b79K/resolve/main/open_clip_pytorch_model.bin"

mkdir -p "$(dirname "$DEST")"
if [ -s "$DEST" ] && ! curl -sIL --max-time 10 "$URL" | grep -qi "HTTP/2 200\|HTTP/1.1 200"; then
  echo "Skipping $DEST — already present and the remote is unreachable right now." >&2
  exit 0
fi

echo "Downloading CLIP ViT-B-32 checkpoint -> $DEST"
curl -L --fail --retry 5 -C - -o "$DEST" "$URL"
echo "Checkpoint ready: $(du -h "$DEST" | cut -f1)"
