"""Background jobs for the complaints app.

Complaints have no long-running request-path work today.
``notify_complaint_status`` is provided as a Celery hook so the complainant can
be notified off-request when staff change a complaint's status (wired to the
notifications module at integrate time).
"""
from __future__ import annotations

from celery import shared_task

from complaints.models import Complaint


@shared_task(name="complaints.notify_complaint_status")
def notify_complaint_status(complaint_id: str) -> str:
    """Placeholder: notify the complainant of a status change.

    Returns the complaint id it processed (a no-op until the notifications
    module is wired in). Kept off the request path per the Celery contract.
    """
    complaint = Complaint.objects.filter(pk=complaint_id).first()
    if complaint is None:
        return ""
    # Integrate step will enqueue push/notification fan-out here.
    return str(complaint.pk)
