"""Data-access layer for the exams app.

Repositories wrap each model over the soft-delete-aware default manager and add
``select_related``/``prefetch_related`` where serializers touch related rows to
avoid N+1 queries.
"""
from __future__ import annotations

from core.repositories import BaseRepository

from exams.models import Exam, ExamResult, MarkEntry, MarksSheet


class ExamRepository(BaseRepository):
    model = Exam

    def get_queryset(self, include_deleted: bool = False):
        return super().get_queryset(include_deleted).select_related("subject")


class ExamResultRepository(BaseRepository):
    model = ExamResult

    def get_queryset(self, include_deleted: bool = False):
        return (
            super()
            .get_queryset(include_deleted)
            .select_related("student", "subject", "exam_ref")
        )

    def for_student(self, student_id):
        return self.get_queryset().filter(student_id=student_id)


class MarksSheetRepository(BaseRepository):
    model = MarksSheet

    def get_queryset(self, include_deleted: bool = False):
        return (
            super()
            .get_queryset(include_deleted)
            .select_related(
                "faculty_class",
                "faculty_class__subject",
                "faculty_class__semester",
                "faculty_class__section",
            )
            .prefetch_related("entries__student")
        )

    def for_class(self, faculty_class_id):
        return self.get_queryset().filter(faculty_class_id=faculty_class_id)


class MarkEntryRepository(BaseRepository):
    model = MarkEntry

    def get_queryset(self, include_deleted: bool = False):
        return (
            super()
            .get_queryset(include_deleted)
            .select_related("sheet", "student")
        )
