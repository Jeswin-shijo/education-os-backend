"""Data-access layer for the complaints app.

Wraps :class:`~complaints.models.Complaint` over the soft-delete-aware default
manager and eager-loads the owning user to avoid N+1 in the monitor/list views.
"""
from __future__ import annotations

from core.repositories import BaseRepository

from complaints.models import Complaint


class ComplaintRepository(BaseRepository):
    model = Complaint

    def get_queryset(self, include_deleted: bool = False):
        return (
            super()
            .get_queryset(include_deleted)
            .select_related("user")
        )

    def for_user(self, user):
        """Complaints owned by ``user`` (the own-complaint scope)."""
        return self.get_queryset().filter(user=user)

    def by_status(self, status):
        return self.get_queryset().filter(status=status)
