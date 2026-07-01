"""Data-access layer for the academics app.

Repositories wrap each model over the soft-delete-aware default manager and add
``select_related`` where the serializers touch FK fields, avoiding N+1 queries.
"""
from __future__ import annotations

from core.repositories import BaseRepository

from academics.models import (
    ClassSession,
    Department,
    Program,
    Section,
    Semester,
    Subject,
)


class DepartmentRepository(BaseRepository):
    model = Department


class ProgramRepository(BaseRepository):
    model = Program

    def get_queryset(self, include_deleted: bool = False):
        return super().get_queryset(include_deleted).select_related("department")


class SemesterRepository(BaseRepository):
    model = Semester

    def get_queryset(self, include_deleted: bool = False):
        return (
            super()
            .get_queryset(include_deleted)
            .select_related("program", "program__department")
        )


class SectionRepository(BaseRepository):
    model = Section

    def get_queryset(self, include_deleted: bool = False):
        return (
            super()
            .get_queryset(include_deleted)
            .select_related("semester", "semester__program")
        )


class SubjectRepository(BaseRepository):
    model = Subject

    def get_queryset(self, include_deleted: bool = False):
        return super().get_queryset(include_deleted).select_related("department")


class ClassSessionRepository(BaseRepository):
    model = ClassSession

    def get_queryset(self, include_deleted: bool = False):
        return (
            super()
            .get_queryset(include_deleted)
            .select_related("subject", "section", "section__semester")
        )
