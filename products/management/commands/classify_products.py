"""Run pass-1 text classification over unclassified products (Phase 3).

Usage:
    python manage.py classify_products [--limit 200] [--no-fuzzy] [--reclassify]

Thin CLI wrapper around products.tasks.run_text_job, which owns the
chunked loop, BatchJob progress tracking, resume logic and per-product
failure isolation. See that function for details.
"""
from django.core.management.base import BaseCommand

from products.tasks import run_text_job

DEFAULT_CONFIDENCE_THRESHOLD = 0.65


class Command(BaseCommand):
    help = "Classify unclassified products with the pass-1 text classifier."

    def add_arguments(self, parser):
        parser.add_argument("--chunk-size", type=int, default=200)
        parser.add_argument("--batch-size", type=int, default=64)
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Only classify the first N products (for testing on a sample).",
        )
        parser.add_argument(
            "--no-fuzzy",
            action="store_true",
            help="Disable the fuzzy category-name shortcut.",
        )
        parser.add_argument("--fuzzy-threshold", type=float, default=90.0)
        parser.add_argument(
            "--confidence-threshold",
            type=float,
            default=DEFAULT_CONFIDENCE_THRESHOLD,
        )
        parser.add_argument(
            "--reclassify",
            action="store_true",
            help="Re-classify products that already have a result.",
        )

    def handle(self, *args, **options):
        run_options = {
            "fuzzy": not options["no_fuzzy"],
            "fuzzy_threshold": options["fuzzy_threshold"],
            "confidence_threshold": options["confidence_threshold"],
            "batch_size": options["batch_size"],
            "chunk_size": options["chunk_size"],
            "reclassify": options["reclassify"],
            "limit": options["limit"],
        }
        job, summary = run_text_job(
            options=run_options,
            log=self.stdout.write,
            err=self.stderr.write,
        )
        if job is None:
            self.stdout.write("No products to classify.")
            return
        breakdown = ", ".join(
            f"{k}: {v}" for k, v in sorted(summary["status_counts"].items())
        )
        self.stdout.write(self.style.SUCCESS(f"Done. Status breakdown: {breakdown}"))