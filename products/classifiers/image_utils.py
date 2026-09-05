"""Download, validate, and cache product images for the pass-2 classifier.

Images are fetched concurrently (ThreadPoolExecutor), retried once on
failure, validated with Pillow (opens cleanly, not a tiny/1x1 placeholder),
and cached under media/cache/<product_number>/ so re-runs reuse files that
already exist. Failures are logged and skipped — the pipeline must degrade
gracefully because spreadsheet image URLs are often broken or expired.
"""
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from PIL import Image, UnidentifiedImageError

from django.conf import settings

logger = logging.getLogger(__name__)

CACHE_ROOT = settings.MEDIA_ROOT / "cache"
MIN_IMAGE_DIMENSION = 32  # px on each side; smaller is a placeholder/broken render

_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]")


def image_cache_dir(product_number):
    """Directory for one product's downloaded images (sanitized name)."""
    safe = _SAFE_FILENAME.sub("_", str(product_number))
    return CACHE_ROOT / safe


def download_image(url, dest_path, timeout=5, retries=1):
    """Download `url` to `dest_path`; returns the Path on success, None on failure.

    Existing files are reused without re-downloading. The file is written to a
    `.part` temp path first so a failed/partial download never leaves a file
    that later passes the existence check.
    """
    dest_path = Path(dest_path)
    if dest_path.exists():
        return dest_path
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, timeout=timeout)
            resp.raise_for_status()
            content = resp.content
            if not content:
                raise ValueError("empty response body")
            tmp = dest_path.with_name(dest_path.name + ".part")
            tmp.write_bytes(content)
            tmp.rename(dest_path)
            return dest_path
        except (requests.RequestException, ValueError, OSError) as exc:
            logger.debug(
                "image download failed (attempt %d/%d): %s (%s)",
                attempt + 1,
                retries + 1,
                url,
                exc,
            )
    logger.warning("image download failed after %d attempts: %s", retries + 1, url)
    return None


def validate_image(path, min_dimension=MIN_IMAGE_DIMENSION):
    """Return True if the file opens as an image and looks like a real photo."""
    try:
        with Image.open(path) as im:
            im.load()  # triggers full decode — catches corrupt/truncated files
            width, height = im.size
            if width < min_dimension or height < min_dimension:
                return False
            if width == 1 and height == 1:
                return False
            return True
    except (UnidentifiedImageError, OSError, ValueError):
        return False


def fetch_product_images(product, workers=10, timeout=5, retries=1, max_per_product=3):
    """Concurrently download + validate up to `max_per_product` images.

    Returns a list of local paths to valid images (cached under
    media/cache/<product_number>/), which may be empty.
    """
    urls = [u for u in (product.image_urls or []) if u][:max_per_product]
    if not urls:
        return []

    dest_dir = image_cache_dir(product.product_number)
    dest_dir.mkdir(parents=True, exist_ok=True)

    downloaded = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                download_image, url, dest_dir / f"{index}.jpg", timeout, retries
            ): index
            for index, url in enumerate(urls)
        }
        for future in as_completed(futures):
            path = future.result()
            if path:
                downloaded.append(path)

    valid = [path for path in downloaded if validate_image(path)]
    if len(valid) < len(downloaded):
        logger.warning(
            "%s: %d/%d downloaded images failed validation",
            product.product_number,
            len(downloaded) - len(valid),
            len(downloaded),
        )
    return valid