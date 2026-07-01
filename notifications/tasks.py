"""Celery tasks for the notifications app.

``send_push_notification`` is the async push-delivery fan-out (stub). A real
implementation would look up device tokens and hand the payload to FCM/APNs; for
now it resolves the notification, computes the audience, and also pushes the new
item to any connected WebSocket clients via the Channels group layer so the
mobile app updates in realtime. It is enqueued by
:meth:`NotificationService.broadcast` (and can be called for per-user rows too).
"""
from __future__ import annotations

from celery import shared_task


@shared_task(name="notifications.send_push_notification")
def send_push_notification(notification_id: str) -> dict:
    """Deliver a notification to its audience (push + realtime WS). Stub.

    Returns a small summary dict for the Celery result backend. Safe to call
    even if the row was since deleted (returns ``delivered: 0``).
    """
    from notifications.models import Notification
    from notifications.serializers import NotificationAppSerializer

    notification = Notification.objects.filter(pk=notification_id).first()
    if notification is None:
        return {"notification_id": str(notification_id), "delivered": 0}

    payload = NotificationAppSerializer(notification).data

    # Realtime fan-out over Channels (best-effort; no-op if layer unavailable).
    recipients = _resolve_recipient_ids(notification)
    _push_realtime(recipients, payload)

    # TODO: integrate a real push provider (FCM/APNs) using device tokens.
    return {
        "notification_id": str(notification.pk),
        "category": notification.category,
        "delivered": len(recipients),
    }


def _resolve_recipient_ids(notification) -> list:
    """User ids that should receive this notification.

    Per-user row -> just its recipient. Broadcast row -> all active users in the
    target role (or all active users when no role is set).
    """
    if notification.recipient_id is not None:
        return [str(notification.recipient_id)]

    from django.contrib.auth import get_user_model

    User = get_user_model()
    qs = User.objects.filter(is_active=True)
    if notification.broadcast_role:
        qs = qs.filter(role=notification.broadcast_role)
    return [str(uid) for uid in qs.values_list("id", flat=True)]


def _push_realtime(recipient_ids: list, payload: dict) -> None:
    """Send ``payload`` to each recipient's per-user Channels group (best-effort)."""
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        from notifications.consumers import user_group_name
    except Exception:  # pragma: no cover - channels not installed/available
        return

    layer = get_channel_layer()
    if layer is None:
        return
    for uid in recipient_ids:
        async_to_sync(layer.group_send)(
            user_group_name(uid),
            {"type": "notify", "payload": payload},
        )
