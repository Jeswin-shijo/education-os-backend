"""Data-access layer for the students app.

Repositories wrap each model over the soft-delete-aware default manager and add
``select_related``/``prefetch_related`` where serializers touch related objects,
avoiding N+1 queries on the roster and profile endpoints.
"""
from __future__ import annotations

from core.repositories import BaseRepository

from students.models import (
    Guardian,
    Medical,
    Student,
    StudentAddress,
    StudentDocument,
)


class StudentRepository(BaseRepository):
    model = Student

    def get_queryset(self, include_deleted: bool = False):
        return (
            super()
            .get_queryset(include_deleted)
            .select_related(
                "user", "program", "department", "semester", "section"
            )
        )

    def with_details(self, include_deleted: bool = False):
        """Queryset prefetching the child collections for the detail view."""
        return self.get_queryset(include_deleted).prefetch_related(
            "addresses", "guardians", "documents", "medical"
        )

    def get_for_user(self, user):
        """Return the Student profile linked to ``user`` (or None)."""
        return self.with_details().filter(user=user).first()


class StudentAddressRepository(BaseRepository):
    model = StudentAddress


class GuardianRepository(BaseRepository):
    model = Guardian


class MedicalRepository(BaseRepository):
    model = Medical


class StudentDocumentRepository(BaseRepository):
    model = StudentDocument
