"""Background jobs for the exams app.

Enqueued from services/views; never block a request on long work. Kept minimal
for now — results-published notifications and marks-sheet exports are the natural
extension points once the notifications module is wired in.
"""
from __future__ import annotations

from celery import shared_task


@shared_task
def notify_results_published(subject_id: str, exam_label: str) -> None:
    """Placeholder: notify students that results for an exam were published.

    Wiring to the notifications module happens in a later integrate step; the
    task exists now so services can enqueue it without a code change later.
    """
    return None


@shared_task
def export_marks_sheet(sheet_id: str) -> None:
    """Placeholder: export a marks sheet (CSV/PDF) for download."""
    return None
