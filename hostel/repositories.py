"""Data-access layer for the hostel app.

Repositories wrap each model over the soft-delete-aware default manager and add
``select_related`` where serializers touch related objects, avoiding N+1 queries
on the list and per-student allocation endpoints.
"""
from __future__ import annotations

from core.repositories import BaseRepository

from hostel.models import HostelAllocation, HostelBlock, HostelRoom


class HostelBlockRepository(BaseRepository):
    model = HostelBlock


class HostelRoomRepository(BaseRepository):
    model = HostelRoom

    def get_queryset(self, include_deleted: bool = False):
        return (
            super().get_queryset(include_deleted).select_related("block")
        )


class HostelAllocationRepository(BaseRepository):
    model = HostelAllocation

    def get_queryset(self, include_deleted: bool = False):
        return (
            super()
            .get_queryset(include_deleted)
            .select_related("student", "room", "room__block")
        )

    def get_for_student(self, student):
        """Return the allocation for ``student`` (joined to room+block) or None."""
        return self.get_queryset().filter(student=student).first()
