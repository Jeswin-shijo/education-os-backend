"""Data-access layer for the ai app.

Repositories wrap each model over the soft-delete-aware default manager and add
``prefetch_related`` where serializers touch related rows (thread messages),
avoiding N+1 queries. Ownership filtering (own threads only) lives here as a
convenience helper the service/view compose.
"""
from __future__ import annotations

from core.repositories import BaseRepository

from ai.models import AIMessage, AIThread


class AIThreadRepository(BaseRepository):
    model = AIThread

    def get_queryset(self, include_deleted: bool = False):
        return (
            super()
            .get_queryset(include_deleted)
            .select_related("user")
            .prefetch_related("messages")
        )

    def for_user(self, user):
        """Threads owned by ``user`` (newest activity first)."""
        return self.get_queryset().filter(user=user).order_by("-updated_at")

    def get_for_user(self, user, feature):
        """The user's active thread for ``feature`` (or ``None``)."""
        return self.get_queryset().filter(user=user, feature=feature).first()


class AIMessageRepository(BaseRepository):
    model = AIMessage

    def get_queryset(self, include_deleted: bool = False):
        return super().get_queryset(include_deleted).select_related("thread")

    def for_thread(self, thread_id):
        return self.get_queryset().filter(thread_id=thread_id).order_by("at")
