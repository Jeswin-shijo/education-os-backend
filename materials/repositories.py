"""Data-access layer for the materials app.

Wraps :class:`~materials.models.Material` over the soft-delete-aware default
manager and eager-loads the FK rows the serializers touch to avoid N+1.
"""
from __future__ import annotations

from core.repositories import BaseRepository

from materials.models import Material


class MaterialRepository(BaseRepository):
    model = Material

    def get_queryset(self, include_deleted: bool = False):
        return (
            super()
            .get_queryset(include_deleted)
            .select_related(
                "subject",
                "faculty_class",
                "faculty_class__subject",
                "faculty_class__faculty",
                "faculty_class__faculty__user",
            )
        )

    def for_subject(self, subject_id):
        return self.get_queryset().filter(subject_id=subject_id)

    def for_class(self, faculty_class_id):
        return self.get_queryset().filter(faculty_class_id=faculty_class_id)
