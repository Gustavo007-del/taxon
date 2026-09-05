"""Pass-1 text classification against the Shopify taxonomy.

Strategy:
1. Fuzzy shortcut: if category_raw / sub_category_raw nearly matches a
   taxonomy category name (rapidfuzz, token_set_ratio >= threshold), take
   it directly — high confidence, no embedding cost.
2. Otherwise embed the product text blob (title + description +
   category_raw + sub_category_raw + brand + materials) and take the top-3
   categories by cosine similarity against the precomputed taxonomy
   vectors. Confidence = top-1 similarity, penalized (x0.85) when the
   description or category_raw is missing.
"""
import numpy as np

from taxonomy.embeddings import get_model, get_taxonomy_embeddings

# Confidence multiplier applied when a product lacks description or category_raw.
MISSING_INFO_PENALTY = 0.85

TEXT_FIELDS = (
    "title",
    "description",
    "category_raw",
    "sub_category_raw",
    "brand",
    "materials",
)


def build_text_blob(product):
    """Concatenate the product's text fields into a single blob for embedding."""
    parts = []
    for field in TEXT_FIELDS:
        value = getattr(product, field)
        if value:
            parts.append(str(value))
    return " ".join(parts).strip()


def _top_k_indices(scores, k=3):
    """Return the indices of the k highest scores, descending."""
    if scores.size <= k:
        order = np.argsort(scores)[::-1]
    else:
        order = np.argpartition(scores, -k)[-k:]
        order = order[np.argsort(scores[order])[::-1]]
    return order[:k]


class TextClassifier:
    """Fast pass-1 classifier. Create once per run, reuse across chunks."""

    def __init__(self, fuzzy=True, fuzzy_threshold=90.0, batch_size=64):
        from taxonomy.models import TaxonomyCategory

        self.fuzzy = fuzzy
        self.fuzzy_threshold = fuzzy_threshold
        self.batch_size = batch_size

        self.category_vectors, self.category_gids = get_taxonomy_embeddings()
        categories = TaxonomyCategory.objects.filter(
            shopify_gid__in=self.category_gids
        )
        self.gid_to_pk = dict(categories.values_list("shopify_gid", "pk"))
        self.gid_to_name = dict(categories.values_list("shopify_gid", "name"))
        self.names = [self.gid_to_name.get(gid, gid) for gid in self.category_gids]
        self._model = None  # loaded lazily, only if the embedding pass is needed

    # -- public API ------------------------------------------------------

    def classify_products(self, products):
        """Classify a list of Product instances; returns one dict per product."""
        results = []
        to_embed = []  # (product, blob) pairs needing the embedding pass
        for product in products:
            result = self._fuzzy_shortcut(product)
            if result is not None:
                results.append(result)
                continue
            blob = build_text_blob(product)
            if not blob:
                results.append(self._empty_result(product))
            else:
                to_embed.append((product, blob))

        if to_embed:
            results.extend(self._embed_pass(to_embed))
        return results

    # -- internals -------------------------------------------------------

    def _fuzzy_shortcut(self, product):
        """Match category_raw / sub_category_raw against taxonomy names."""
        if not self.fuzzy:
            return None
        try:
            from rapidfuzz import fuzz, process
        except ImportError:
            return None  # rapidfuzz not installed — fall back to embeddings

        for text in (product.category_raw, product.sub_category_raw):
            if not text:
                continue
            match = process.extractOne(
                text,
                self.names,
                scorer=fuzz.token_set_ratio,
                score_cutoff=self.fuzzy_threshold,
            )
            if match is not None:
                best_name, score, index = match
                gid = self.category_gids[index]
                confidence = score / 100.0
                return {
                    "product_id": product.pk,
                    "predicted_gid": gid,
                    "predicted_pk": self.gid_to_pk[gid],
                    "confidence": confidence,
                    "method": "fuzzy",
                    "alternatives": [
                        {
                            "shopify_gid": gid,
                            "name": best_name,
                            "score": round(confidence, 4),
                        }
                    ],
                    "flags": {},
                }
        return None

    def _empty_result(self, product):
        return {
            "product_id": product.pk,
            "predicted_gid": None,
            "predicted_pk": None,
            "confidence": 0.0,
            "method": "text",
            "alternatives": [],
            "flags": {"empty_text": True},
        }

    def _embed_pass(self, pairs):
        """Embed blobs in batches and rank them against the taxonomy vectors."""
        if self._model is None:
            self._model = get_model()

        blobs = [blob for _, blob in pairs]
        embeds = self._model.encode(
            blobs,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        ).astype(np.float32)

        # (n_products, dim) x (dim, n_categories) -> similarity matrix
        similarity = embeds @ self.category_vectors.T

        out = []
        for (product, _), scores in zip(pairs, similarity):
            top = _top_k_indices(scores)
            alternatives = [
                {
                    "shopify_gid": self.category_gids[i],
                    "name": self.names[i],
                    "score": round(float(scores[i]), 4),
                }
                for i in top
            ]
            top_gid = self.category_gids[top[0]]
            missing = not (product.description and product.category_raw)
            confidence = float(scores[top[0]])
            if missing:
                confidence *= MISSING_INFO_PENALTY
            out.append(
                {
                    "product_id": product.pk,
                    "predicted_gid": top_gid,
                    "predicted_pk": self.gid_to_pk[top_gid],
                    "confidence": round(confidence, 4),
                    "method": "text",
                    "alternatives": alternatives,
                    "flags": {
                        "no_description": not product.description,
                        "no_category_raw": not product.category_raw,
                    },
                }
            )
        return out