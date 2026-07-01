"""Background jobs for the leave app.

Approval notifications are dispatched off the request path via Celery. Bodies are
intentionally light (and import lazily) so this module stays importable during
``check``/migrations before the notifications app or a broker is wired up.
"""
from __future__ import annotations

from celery import shared_task


@shared_task(name="leave.notify_decision")
def notify_decision(leave_id: str) -> bool:
    """Notify an applicant that their leave request was decided (best-effort)."""
    from leave.models import LeaveRequest

    return LeaveRequest.objects.filter(pk=leave_id).exists()


@shared_task(name="leave.notify_new_request")
def notify_new_request(leave_id: str) -> bool:
    """Notify the relevant approver(s) that a new leave request was filed."""
    from leave.models import LeaveRequest

    # Fan-out to approvers handled by the notifications app once integrated.
    return LeaveRequest.objects.filter(pk=leave_id).exists()
