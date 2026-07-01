"""Background jobs for the placement app.

Notifications to applicants on opening/status changes are enqueued here so the
request never blocks on delivery. The task body is intentionally lightweight
(and import-safe when Celery is not running); wire real push/email inside once
the notifications transport is available.
"""
from __future__ import annotations

from celery import shared_task


@shared_task(name="placement.notify_new_opening")
def notify_new_opening(opening_id: str) -> str:
    """Notify eligible students that a new placement opening is live."""
    # Placeholder: fan-out to the notifications app when integrated.
    return f"notified:opening:{opening_id}"


@shared_task(name="placement.notify_status_change")
def notify_status_change(application_id: str, status: str) -> str:
    """Notify a student that their application status changed."""
    return f"notified:application:{application_id}:{status}"
