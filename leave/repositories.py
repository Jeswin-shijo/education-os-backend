"""Data-access layer for the leave app.

Wraps :class:`~leave.models.LeaveRequest` over the soft-delete-aware default
manager and ``select_related``s the ``user``/``decided_by`` FKs the serializer
touches, avoiding N+1 queries.
"""
from __future__ import annotations

from core.repositories import BaseRepository

from leave.models import LeaveRequest


class LeaveRequestRepository(BaseRepository):
    model = LeaveRequest

    def get_queryset(self, include_deleted: bool = False):
        return (
            super()
            .get_queryset(include_deleted)
            .select_related("user", "decided_by")
        )

    def for_user(self, user_id):
        """Live leave requests filed by ``user_id`` (newest first)."""
        return self.get_queryset().filter(user_id=user_id)
