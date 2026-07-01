"""Data-access layer for the attendance app.

Repositories wrap each model over the soft-delete-aware default manager and add
``select_related``/``prefetch_related`` where serializers touch related rows,
avoiding N+1 queries.
"""
from __future__ import annotations

from core.repositories import BaseRepository

from attendance.models import AttendanceEntry, AttendanceRecord, AttendanceSession


class AttendanceRecordRepository(BaseRepository):
    model = AttendanceRecord

    def get_queryset(self, include_deleted: bool = False):
        return (
            super()
            .get_queryset(include_deleted)
            .select_related("subject", "student")
        )

    def for_student(self, student):
        return self.get_queryset().filter(student=student)


class AttendanceSessionRepository(BaseRepository):
    model = AttendanceSession

    def get_queryset(self, include_deleted: bool = False):
        return (
            super()
            .get_queryset(include_deleted)
            .select_related("faculty_class", "faculty_class__subject")
            .prefetch_related("entries")
        )

    def for_class(self, faculty_class_id):
        return self.get_queryset().filter(faculty_class_id=faculty_class_id)


class AttendanceEntryRepository(BaseRepository):
    model = AttendanceEntry

    def get_queryset(self, include_deleted: bool = False):
        return super().get_queryset(include_deleted).select_related("session")
