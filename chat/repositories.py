"""Data-access layer for the chat app.

Repositories wrap each model over the soft-delete-aware default manager and add
``select_related``/``prefetch_related`` where serializers touch related rows,
avoiding N+1 queries.
"""
from __future__ import annotations

from django.db.models import Q

from core.repositories import BaseRepository

from chat.models import ChatMessage, ChatThread


class ChatThreadRepository(BaseRepository):
    model = ChatThread

    def get_queryset(self, include_deleted: bool = False):
        return (
            super()
            .get_queryset(include_deleted)
            .select_related("teacher", "parent")
            .prefetch_related("messages")
        )

    def for_participant(self, user):
        """Threads where ``user`` is the teacher or the parent."""
        return self.get_queryset().filter(
            Q(teacher_id=user.id) | Q(parent_id=user.id)
        )


class ChatMessageRepository(BaseRepository):
    model = ChatMessage

    def get_queryset(self, include_deleted: bool = False):
        return super().get_queryset(include_deleted).select_related("thread", "sender")

    def for_thread(self, thread_id):
        return self.get_queryset().filter(thread_id=thread_id).order_by("at")
