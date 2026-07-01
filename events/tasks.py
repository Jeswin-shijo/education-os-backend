"""Celery tasks for the events app.

Event reminders/notifications are enqueued rather than run inline so requests
never block on delivery. The concrete notification transport is owned by the
``notifications`` app; this task is a thin, safe stub that can be wired to it.
"""
from __future__ import annotations

from celery import shared_task


@shared_task(name="events.send_event_reminder")
def send_event_reminder(event_id: str) -> str:
    """Send reminders to everyone registered for ``event_id``.

    Placeholder implementation: resolves the registrant list so the wiring is in
    place; delegating to the notifications app is left to the integrate step.
    """
    from events.models import EventRegistration

    user_ids = list(
        EventRegistration.objects.filter(event_id=event_id).values_list(
            "user_id", flat=True
        )
    )
    return f"queued reminder for event {event_id} to {len(user_ids)} registrant(s)"
