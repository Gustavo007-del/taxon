"""Shared orchestration helpers for the classify_* commands (Phase 5).

A BatchJob row is created when a run starts, updated with processed/failed
counts after every chunk, and finished (completed/failed) at the end so a
progress endpoint (Phase 6) can report on it.
"""
from django.utils import timezone

from products.models import BatchJob


def start_job(job_type, total, **options):
    """Create a running BatchJob for a classification run."""
    return BatchJob.objects.create(
        job_type=job_type,
        status=BatchJob.Status.RUNNING,
        total=total,
        options=options,
    )


def update_progress(job, processed, failed):
    """Persist progress after a chunk (cheap UPDATE on the job row)."""
    BatchJob.objects.filter(pk=job.pk).update(processed=processed, failed=failed)
    job.processed = processed
    job.failed = failed


def finish_job(job, failed=None, success=True):
    """Mark the job completed (or failed) with its final counts."""
    if failed is not None:
        job.failed = failed
    job.status = BatchJob.Status.COMPLETED if success else BatchJob.Status.FAILED
    job.finished_at = timezone.now()
    job.save(update_fields=["status", "failed", "finished_at"])