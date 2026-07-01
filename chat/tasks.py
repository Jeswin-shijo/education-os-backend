"""Background jobs for the chat app.

Chat's realtime path is synchronous (the service broadcasts to the Channels group
inline). This Celery task exists for the *out-of-band* side channels — e.g.
push/email notifying an offline recipient of a new message — so the request never
blocks on external delivery. The view/service can enqueue it after persisting a
message; delivery integrations are pluggable.
"""
from __future__ import annotations

from celery import shared_task


@shared_task(name="chat.notify_new_message")
def notify_new_message(thread_id: str, message_id: str, recipient_id: str) -> dict:
    """Notify an (offline) recipient of a new chat message.

    Best-effort and idempotent-safe: looks up the row and would hand off to the
    push/email provider. Returns a small status dict for result tracking.
    """
    from chat.models import ChatMessage

    message = ChatMessage.all_objects.filter(pk=message_id).first()
    if message is None:
        return {"status": "skipped", "reason": "message-not-found"}

    # Delivery integration (push/email) is pluggable — wire the provider here.
    # Kept side-effect-free so it is safe to run in any environment.
    return {
        "status": "queued",
        "thread": str(thread_id),
        "message": str(message_id),
        "recipient": str(recipient_id),
    }
