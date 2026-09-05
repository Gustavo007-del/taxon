"""Pass-2 image classification against the Shopify taxonomy.

Loads an open_clip model once, embeds each product's downloaded images
(averaged across images per product), and ranks against cached CLIP text
embeddings of every taxonomy category name. Run only on products whose
text classification fell below the confidence threshold (see the
`classify_images` management command).
"""
import numpy as np
from PIL import Image

from products.classifiers.image_utils import fetch_product_images
from products.classifiers.text_classifier import _top_k_indices
from taxonomy.embeddings import (
    CLIP_MODEL_NAME,
    get_clip_model,
    get_clip_taxonomy_embeddings,
)


def _empty_result(product, flag):
    return {
        "product_id": product.pk,
        "predicted_gid": None,
        "predicted_pk": None,
        "confidence": 0.0,
        "method": "image",
        "alternatives": [],
        "flags": {flag: True},
    }


class ImageClassifier:
    """Pass-2 classifier. Create once per run, reuse across products."""

    def __init__(
        self,
        model_name=CLIP_MODEL_NAME,
        workers=10,
        timeout=5,
        max_per_product=3,
    ):
        from taxonomy.models import TaxonomyCategory

        self.model_name = model_name
        self.workers = workers
        self.timeout = timeout
        self.max_per_product = max_per_product

        # CLIP text embeddings of every category name, cached on disk.
        self.clip_vectors, self.category_gids = get_clip_taxonomy_embeddings(
            model_name=model_name
        )
        categories = TaxonomyCategory.objects.filter(shopify_gid__in=self.category_gids)
        self.gid_to_pk = dict(categories.values_list("shopify_gid", "pk"))
        self.gid_to_name = dict(categories.values_list("shopify_gid", "name"))
        self.names = [self.gid_to_name.get(gid, gid) for gid in self.category_gids]

        self.model, self.preprocess, _ = get_clip_model(model_name)

    def classify_product(self, product):
        """Download images for `product`, embed them, return a result dict.

        Result shape mirrors the text classifier: predicted_gid / predicted_pk /
        confidence / alternatives / flags. Returns an empty result (confidence
        0.0, no prediction) when no valid image could be fetched.
        """
        paths = fetch_product_images(
            product,
            workers=self.workers,
            timeout=self.timeout,
            max_per_product=self.max_per_product,
        )
        if not paths:
            return _empty_result(product, "no_valid_images")

        import torch

        device = next(self.model.parameters()).device
        tensors = []
        for path in paths:
            try:
                with Image.open(path) as im:
                    tensors.append(self.preprocess(im.convert("RGB")))
            except (OSError, ValueError):
                continue
        if not tensors:
            return _empty_result(product, "no_valid_images")

        with torch.no_grad():
            embeds = self.model.encode_image(
                torch.stack(tensors).to(device), normalize=True
            )
        # Average image embeddings per product, then cosine-sim against all
        # category text embeddings: (1, dim) @ (dim, n_categories).
        vector = embeds.mean(dim=0, keepdim=True).cpu().numpy().astype(np.float32)
        scores = (vector @ self.clip_vectors.T)[0]

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
        return {
            "product_id": product.pk,
            "predicted_gid": top_gid,
            "predicted_pk": self.gid_to_pk[top_gid],
            "confidence": round(float(scores[top[0]]), 4),
            "method": "image",
            "alternatives": alternatives,
            "flags": {"image_count": len(tensors)},
        }