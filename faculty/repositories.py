"""Data-access layer for the faculty app.

Repositories wrap each model over the soft-delete-aware default manager and add
``select_related``/``prefetch_related`` where the serializers touch related
rows, avoiding N+1 queries.
"""
from __future__ import annotations

from core.repositories import BaseRepository

from faculty.models import FacultyClass, FacultyProfile, RosterEntry


class FacultyProfileRepository(BaseRepository):
    model = FacultyProfile

    def get_queryset(self, include_deleted: bool = False):
        return (
            super()
            .get_queryset(include_deleted)
            .select_related("user", "department")
            .prefetch_related("classes__subject", "classes__section")
        )

    def get_by_user(self, user):
        """Return the profile for a user (or ``None``)."""
        return self.get_by(user=user)


class FacultyClassRepository(BaseRepository):
    model = FacultyClass

    def get_queryset(self, include_deleted: bool = False):
        return (
            super()
            .get_queryset(include_deleted)
            .select_related(
                "subject",
                "semester",
                "section",
                "faculty",
                "faculty__user",
            )
        )


class RosterEntryRepository(BaseRepository):
    model = RosterEntry

    def get_queryset(self, include_deleted: bool = False):
        return super().get_queryset(include_deleted).select_related("faculty_class")

    def for_class(self, faculty_class_id):
        return self.get_queryset().filter(faculty_class_id=faculty_class_id)
