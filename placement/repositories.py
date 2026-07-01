"""Data-access layer for the placement app.

Repositories wrap each model over the soft-delete-aware default manager and add
``select_related`` where serializers touch related objects, avoiding N+1 queries
on the applications endpoints.
"""
from __future__ import annotations

from core.repositories import BaseRepository

from placement.models import PlacementApplication, PlacementOpening


class PlacementOpeningRepository(BaseRepository):
    model = PlacementOpening

    def active(self, include_deleted: bool = False):
        """Currently-open postings (most recent last-date first)."""
        return self.get_queryset(include_deleted).filter(is_active=True)


class PlacementApplicationRepository(BaseRepository):
    model = PlacementApplication

    def get_queryset(self, include_deleted: bool = False):
        return (
            super()
            .get_queryset(include_deleted)
            .select_related("opening", "student")
        )

    def for_student(self, student, include_deleted: bool = False):
        """Applications belonging to ``student`` (most recent first)."""
        return self.get_queryset(include_deleted).filter(student=student)
