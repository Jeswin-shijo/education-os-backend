"""Background jobs for the assignments app.

Reminders + notifications are dispatched off the request path via Celery. The
bodies are intentionally light (and import lazily) so this module stays
importable during ``check``/migrations even before the notifications app or a
broker is wired up.
"""
from __future__ import annotations

from celery import shared_task


@shared_task(name="assignments.send_due_reminders")
def send_due_reminders(window_hours: int = 24) -> int:
    """Notify students of assignments due within ``window_hours``.

    Returns the number of assignments considered. The actual push/email fan-out
    is delegated to the notifications app once available; here we just compute
    the due set so the task is safe to schedule immediately.
    """
    from datetime import timedelta

    from django.utils import timezone

    from assignments.models import Assignment

    now = timezone.now()
    horizon = now + timedelta(hours=window_hours)
    due = Assignment.objects.filter(
        due_date__gte=now,
        due_date__lte=horizon,
        status=Assignment.STATUS_PENDING,
    )
    return due.count()


@shared_task(name="assignments.notify_new_assignment")
def notify_new_assignment(assignment_id: str) -> bool:
    """Notify a class that a new assignment was posted (best-effort)."""
    from assignments.models import Assignment

    exists = Assignment.objects.filter(pk=assignment_id).exists()
    # Notification fan-out handled by the notifications app when integrated.
    return exists
