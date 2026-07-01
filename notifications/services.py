"""Business-logic layer for the notifications app.

:class:`NotificationService` extends :class:`core.services.BaseService` so writes
auto-stamp ``created_by``/``updated_by``, emit an :class:`~core.models.AuditLog`
row, and invalidate the cached per-user notification reads. It also owns the
domain operations the app needs: mark-read, mark-all-read, unread-count, and the
admin broadcast (which fans out to a role/all and enqueues push delivery).
"""
from __future__ import annotations

from django.contrib.auth import get_user_model

from core.cache import cache_key, invalidate, invalidate_prefix
from core.models import AuditLog
from core.services import BaseService

from notifications.models import Notification
from notifications.repositories import NotificationRepository

User = get_user_model()

# Cache key prefix owned by this app.
NOTIFICATIONS_PREFIX = "notifications"


def user_scope_key(user_id, scope: str) -> str:
    """Cache key for a per-user notifications view (``notifications:<scope>:<uid>``)."""
    return cache_key(NOTIFICATIONS_PREFIX, scope, user_id)


class NotificationService(BaseService):
    model = Notification
    repository_class = NotificationRepository
    entity_name = "Notification"

    # -- cache ------------------------------------------------------------
    def invalidate_cache(self, instance=None) -> None:
        """Bust per-user caches touched by a write.

        A per-recipient write only affects that user's cache; a broadcast (no
        recipient) can affect everyone, so bust the whole prefix.
        """
        recipient_id = getattr(instance, "recipient_id", None) if instance else None
        if recipient_id:
            invalidate(
                user_scope_key(recipient_id, "list"),
                user_scope_key(recipient_id, "unread"),
            )
        else:
            invalidate_prefix(NOTIFICATIONS_PREFIX)

    # -- reads ------------------------------------------------------------
    def list_for_user(self, user):
        return self.repository.for_user(user)

    def unread_count(self, user) -> int:
        return self.repository.for_user(user).filter(read=False).count()

    # -- writes -----------------------------------------------------------
    def mark_read(self, instance: Notification) -> Notification:
        """Mark a single notification as read (idempotent)."""
        if not instance.read:
            instance = self.update(instance, read=True)
        return instance

    def mark_all_read(self, user) -> int:
        """Mark all of the user's own unread notifications as read.

        Only directly-targeted rows are mutated (a shared broadcast row is not
        flipped for one reader). Returns the number of rows updated.
        """
        qs = self.repository.owned_by(user).filter(read=False)
        updated = qs.update(read=True)
        if updated:
            self.audit(
                AuditLog.ACTION_UPDATE,
                entity_id=getattr(user, "pk", None),
                changes={"mark_all_read": updated},
            )
            invalidate(
                user_scope_key(user.pk, "list"),
                user_scope_key(user.pk, "unread"),
            )
        return updated

    def broadcast(self, *, title: str, body: str, category: str, role: str = "") -> Notification:
        """Admin broadcast: create a single broadcast row for a role (or all).

        Returns the created broadcast :class:`Notification`. Delivery to push
        channels is enqueued to Celery so the request never blocks.
        """
        instance = self.create(
            recipient=None,
            broadcast_role=role or "",
            title=title,
            body=body,
            category=category,
            read=False,
        )
        # Broadcasts affect many users -> bust the whole prefix.
        invalidate_prefix(NOTIFICATIONS_PREFIX)
        # Enqueue async push fan-out (stub).
        from notifications.tasks import send_push_notification

        send_push_notification.delay(str(instance.pk))
        return instance
