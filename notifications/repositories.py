"""Data-access layer for the notifications app.

Repository queries wrap the soft-delete-aware default manager and
``select_related`` the recipient where serializers touch it, avoiding N+1.
"""
from __future__ import annotations

from django.db.models import Q

from core.repositories import BaseRepository

from notifications.models import Notification


class NotificationRepository(BaseRepository):
    model = Notification

    def get_queryset(self, include_deleted: bool = False):
        return super().get_queryset(include_deleted).select_related("recipient")

    def for_user(self, user):
        """Notifications visible to ``user``: their own rows + relevant broadcasts.

        A broadcast (``recipient`` NULL) is visible when it targets the user's
        role or targets all roles (blank ``broadcast_role``). Newest first.
        """
        role = getattr(user, "role", None)
        broadcast_q = Q(recipient__isnull=True) & (
            Q(broadcast_role="") | Q(broadcast_role=role)
        )
        return (
            self.get_queryset()
            .filter(Q(recipient=user) | broadcast_q)
            .order_by("-created_at")
        )

    def owned_by(self, user):
        """Only the rows directly targeted at ``user`` (excludes broadcasts)."""
        return self.get_queryset().filter(recipient=user)
