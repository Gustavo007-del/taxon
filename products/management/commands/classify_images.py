"""Run pass-2 image classification over low-confidence products (Phase 4).

Usage:
    python manage.py classify_images [--limit 100] [--workers 10] [--threshold 0.65]

Thin CLI wrapper around products.tasks.run_image_job, which owns the
chunked loop, BatchJob progress tracking, resume logic and per-product
failure marking. By default only needs_review/failed results are processed;
pass --all to also re-run on auto_approved rows.
"""
from django.core.management.base import BaseCommand

from products.tasks import run_image_job


class Command(BaseCommand):
    help = "Classify low-confidence products with images (pass-2 fallback)."

    def add_arguments(self, parser):
        parser.add_argument("--chunk-size", type=int, default=50)
        parser.add_argument("--workers", type=int, default=10)
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--threshold", type=float, default=0.65)
        parser.add_argument(
            "--all",
            action="store_true",
            help="Also re-run the image pass on auto_approved results.",
        )

    def handle(self, *args, **options):
        run_options = {
            "workers": options["workers"],
            "threshold": options["threshold"],
            "chunk_size": options["chunk_size"],
            "limit": options["limit"],
            "all_results": options["all"],
        }
        job, summary = run_image_job(
            options=run_options,
            log=self.stdout.write,
            err=self.stderr.write,
        )
        if job is None:
            self.stdout.write("No results to classify.")
            return
        breakdown = ", ".join(f"{k}: {v}" for k, v in summary["counts"].items())
        self.stdout.write(self.style.SUCCESS(f"Done. {breakdown}"))