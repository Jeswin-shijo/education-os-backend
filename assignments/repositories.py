"""Data-access layer for the assignments app.

Repositories wrap each model over the soft-delete-aware default manager and add
``select_related``/``prefetch_related`` where serializers touch related rows,
avoiding N+1 queries.
"""
from __future__ import annotations

from core.repositories import BaseRepository

from assignments.models import Assignment, Submission


class AssignmentRepository(BaseRepository):
    model = Assignment

    def get_queryset(self, include_deleted: bool = False):
        return (
            super()
            .get_queryset(include_deleted)
            .select_related("subject", "faculty_class", "faculty_class__subject")
        )


class SubmissionRepository(BaseRepository):
    model = Submission

    def get_queryset(self, include_deleted: bool = False):
        return (
            super()
            .get_queryset(include_deleted)
            .select_related("assignment", "student")
        )

    def for_assignment_and_student(self, assignment_id, student_id):
        """Return the live submission for (assignment, student) or ``None``."""
        return (
            self.get_queryset()
            .filter(assignment_id=assignment_id, student_id=student_id)
            .first()
        )
