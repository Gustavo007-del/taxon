"""Precompute and cache embeddings of every taxonomy category.

Vectors are cached in data/embeddings_cache/ keyed on the model name and
the exact set of category gids, so re-runs don't re-embed unless the
taxonomy or model changed:

- taxonomy.npy / taxonomy_meta.json   -> all-MiniLM-L6-v2 text embeddings
  of category full_paths (pass-1 text classifier)
- clip_taxonomy.npy / clip_taxonomy_meta.json -> open_clip text embeddings
  of category names (pass-2 image classifier)

The sentence-transformers / open_clip imports are deferred so that
commands like `manage.py check` don't require torch to be installed.
"""
import json
import os
from datetime import datetime, timezone

import numpy as np

from django.conf import settings

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

CACHE_DIR = settings.BASE_DIR / "data" / "embeddings_cache"
VECTORS_PATH = CACHE_DIR / "taxonomy.npy"
META_PATH = CACHE_DIR / "taxonomy_meta.json"

_model = None


def get_model():
    """Load the sentence-transformer model once per process (lazy import)."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(MODEL_NAME)
    return _model


def _current_gids():
    from taxonomy.models import TaxonomyCategory

    return list(
        TaxonomyCategory.objects.order_by("pk").values_list("shopify_gid", flat=True)
    )


def _cached_vectors(gids):
    """Return cached vectors if present and still valid for `gids`, else None."""
    if not VECTORS_PATH.exists() or not META_PATH.exists():
        return None
    try:
        meta = json.loads(META_PATH.read_text(encoding="utf-8"))
        vectors = np.load(VECTORS_PATH)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if meta.get("model") != MODEL_NAME:
        return None
    if meta.get("category_gids") != gids:
        return None
    return vectors


def _save_cache(vectors, gids):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    np.save(VECTORS_PATH, vectors)
    META_PATH.write_text(
        json.dumps(
            {
                "model": MODEL_NAME,
                "category_gids": gids,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def get_taxonomy_embeddings(force=False):
    """Return (normalized_vectors, gids) for every taxonomy category.

    vectors: float32 array of shape (n_categories, dim), L2-normalized.
    gids:    list of category shopify_gids aligned with the rows of vectors.
    """
    from taxonomy.models import TaxonomyCategory

    if not TaxonomyCategory.objects.exists():
        raise RuntimeError(
            "Taxonomy is empty — run `python manage.py load_taxonomy` first."
        )

    gids = _current_gids()
    if not force:
        cached = _cached_vectors(gids)
        if cached is not None:
            return cached, gids

    texts = list(
        TaxonomyCategory.objects.order_by("pk").values_list("full_path", flat=True)
    )
    model = get_model()
    vectors = model.encode(
        texts,
        batch_size=64,
        normalize_embeddings=True,
        show_progress_bar=False,
        convert_to_numpy=True,
    ).astype(np.float32)
    _save_cache(vectors, gids)
    return vectors, gids


# ---------------------------------------------------------------------------
# CLIP text embeddings (pass-2 image classifier)
# ---------------------------------------------------------------------------

CLIP_MODEL_NAME = "ViT-B-32"
# Pretrained checkpoint for the CLIP model. Must be passed explicitly:
# without it open_clip silently returns a RANDOMLY-initialized model whose
# similarity scores are meaningless. The default is the canonical open_clip
# ViT-B-32 checkpoint ("laion2b_s34b_b79k"), which open_clip downloads
# once from Hugging Face and caches under ~/.cache/huggingface.
CLIP_PRETRAINED = "laion2b_s34b_b79k"
# When the checkpoint has been seeded locally via scripts/fetch_clip_checkpoint.sh
# (curl into media/cache/clip/, see below) that file is used instead of the HF
# tag: huggingface_hub's python downloader is slow/throttled, and a local file
# also makes the pipeline reusable offline. Set the CLIP_PRETRAINED env var to
# override either choice.
_LOCAL_CLIP_CKPT = settings.MEDIA_ROOT / "cache" / "clip" / "open_clip_pytorch_model.bin"


def _clip_pretrained():
    """Resolve the CLIP checkpoint: env var > local seeded file > HF tag."""
    env = os.environ.get("CLIP_PRETRAINED")
    if env:
        return env
    if _LOCAL_CLIP_CKPT.exists():
        return str(_LOCAL_CLIP_CKPT)
    return CLIP_PRETRAINED
CLIP_VECTORS_PATH = CACHE_DIR / "clip_taxonomy.npy"
CLIP_META_PATH = CACHE_DIR / "clip_taxonomy_meta.json"

_clip_model = None


def get_clip_model(model_name=CLIP_MODEL_NAME):
    """Load the open_clip model + eval transforms + tokenizer once per process."""
    global _clip_model
    if _clip_model is None:
        import open_clip

        model, _, preprocess = open_clip.create_model_and_transforms(
            model_name, pretrained=_clip_pretrained()
        )
        tokenizer = open_clip.get_tokenizer(model_name)
        model.eval()
        _clip_model = (model, preprocess, tokenizer)
    return _clip_model


def _cached_clip_vectors(gids, model_name):
    """Return cached CLIP vectors if present and valid for `gids`, else None."""
    if not CLIP_VECTORS_PATH.exists() or not CLIP_META_PATH.exists():
        return None
    try:
        meta = json.loads(CLIP_META_PATH.read_text(encoding="utf-8"))
        vectors = np.load(CLIP_VECTORS_PATH)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if meta.get("model") != model_name:
        return None
    if meta.get("pretrained") != CLIP_PRETRAINED:
        return None  # stale vectors built by a different checkpoint (e.g. random init)
    if meta.get("category_gids") != gids:
        return None
    return vectors


def _save_clip_cache(vectors, gids, model_name):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    np.save(CLIP_VECTORS_PATH, vectors)
    CLIP_META_PATH.write_text(
        json.dumps(
            {
                "model": model_name,
                "pretrained": CLIP_PRETRAINED,
                "category_gids": gids,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def get_clip_taxonomy_embeddings(force=False, model_name=CLIP_MODEL_NAME):
    """Return (normalized CLIP text vectors, gids) for every taxonomy category.

    Category names (leaf names, which stay well under CLIP's 77-token
    limit) are embedded with the open_clip text encoder, so image
    embeddings can be ranked against them in the same space. Cached in
    clip_taxonomy.npy keyed on model name + category gids.
    """
    from taxonomy.models import TaxonomyCategory

    if not TaxonomyCategory.objects.exists():
        raise RuntimeError(
            "Taxonomy is empty — run `python manage.py load_taxonomy` first."
        )

    gids = _current_gids()
    if not force:
        cached = _cached_clip_vectors(gids, model_name)
        if cached is not None:
            return cached, gids

    import torch

    texts = list(
        TaxonomyCategory.objects.order_by("pk").values_list("name", flat=True)
    )
    model, _, tokenizer = get_clip_model(model_name)
    device = next(model.parameters()).device

    vectors = []
    step = 256
    with torch.no_grad():
        for start in range(0, len(texts), step):
            tokens = tokenizer(texts[start : start + step]).to(device)
            vec = model.encode_text(tokens)
            vec = vec / vec.norm(dim=-1, keepdim=True)
            vectors.append(vec.cpu().numpy())
    vectors = np.concatenate(vectors).astype(np.float32)
    _save_clip_cache(vectors, gids, model_name)
    return vectors, gids