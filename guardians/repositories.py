"""Data-access layer for the guardians app.

Repositories wrap :class:`~guardians.models.ParentLink` over the soft-delete-aware
default manager and eager-load the related parent/student rows the serializers
touch, avoiding N+1 queries.
"""
from __future__ import annotations

from core.repositories import BaseRepository

from guardians.models import ParentLink


class ParentLinkRepository(BaseRepository):
    model = ParentLink

    def get_queryset(self, include_deleted: bool = False):
        return (
            super()
            .get_queryset(include_deleted)
            .select_related(
                "parent",
                "student",
                "student__program",
                "student__department",
                "student__semester",
                "student__section",
            )
        )

    def for_parent(self, parent):
        """Return the live links owned by ``parent``."""
        return self.get_queryset().filter(parent=parent)
