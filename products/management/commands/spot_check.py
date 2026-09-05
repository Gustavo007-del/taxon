"""Print a sample of classified results for manual sanity checks (Phase 7).

Usage:
    python manage.py spot_check [--limit 20] [--status auto_approved]
"""
from django.core.management.base import BaseCommand

from products.models import ClassificationResult


class Command(BaseCommand):
    help = "Print a sample of classified results for manual sanity checks."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=20)
        parser.add_argument(
            "--status",
            default=None,
            help="Only show results with this status value (e.g. auto_approved).",
        )

    def handle(self, *args, **options):
        qs = ClassificationResult.objects.select_related(
            "product", "predicted_category"
        ).order_by("-updated_at")
        if options["status"]:
            qs = qs.filter(status=options["status"])

        counts = {
            label: ClassificationResult.objects.filter(status=value).count()
            for value, label in ClassificationResult.Status.choices
        }
        self.stdout.write(
            "Status counts: "
            + ", ".join(f"{label}: {n}" for label, n in counts.items())
        )

        sample = list(qs[: options["limit"]])
        if not sample:
            self.stdout.write("No results to show.")
            return

        self.stdout.write(f"\nSample of {len(sample)} result(s):\n")
        for result in sample:
            category = (
                result.predicted_category.full_path
                if result.predicted_category
                else "(no prediction)"
            )
            confidence = (
                result.final_confidence if result.final_confidence is not None else 0.0
            )
            self.stdout.write(
                f"{result.product.product_number:12s} | {result.status:14s} | "
                f"conf={confidence:.3f} | {result.method_used}"
            )
            self.stdout.write(f"    -> {category}")
            self.stdout.write(f"    {result.product.title[:90]}")