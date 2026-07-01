"""Business-logic layer for the assignments app.

Each service extends :class:`core.services.BaseService` so writes auto-stamp
``created_by``/``updated_by``, emit an :class:`~core.models.AuditLog` row, and
invalidate cached assignment views. Assignment reads are cached under the
``assignments`` prefix; any write busts that prefix.
"""
from __future__ import annotations

from django.utils import timezone

from core.cache import invalidate_prefix
from core.services import BaseService

from assignments.models import Assignment, Submission
from assignments.repositories import AssignmentRepository, SubmissionRepository

# Cache-key prefix owned by this app.
ASSIGNMENTS_PREFIX = "assignments"


class AssignmentService(BaseService):
    model = Assignment
    repository_class = AssignmentRepository
    entity_name = "Assignment"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(ASSIGNMENTS_PREFIX)


class SubmissionService(BaseService):
    model = Submission
    repository_class = SubmissionRepository
    entity_name = "Submission"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(ASSIGNMENTS_PREFIX)

    def submit(self, assignment: Assignment, student, file_name: str) -> Submission:
        """Create or update a student's submission for ``assignment``.

        Upserts by (assignment, student): re-submitting updates the existing
        row. Sets ``submitted_at`` to now and marks the parent assignment
        ``submitted`` (or ``late`` when past the due date). Both writes are
        audited and bust the assignments cache.
        """
        now = timezone.now()
        is_late = assignment.due_date is not None and now > assignment.due_date

        existing = self.repository.for_assignment_and_student(
            assignment.pk, student.pk
        )
        if existing is not None:
            submission = self.update(
                existing, file_name=file_name, submitted_at=now
            )
        else:
            submission = self.create(
                assignment=assignment,
                student=student,
                file_name=file_name,
                submitted_at=now,
            )

        # Reflect the turn-in on the parent assignment's status (unless it's
        # already graded — a grade shouldn't be overwritten by a re-submit).
        if assignment.status != Assignment.STATUS_GRADED:
            new_status = (
                Assignment.STATUS_LATE if is_late else Assignment.STATUS_SUBMITTED
            )
            if assignment.status != new_status:
                assignment_service = AssignmentService(actor=self.actor, ip=self.ip)
                assignment_service.update(assignment, status=new_status)

        return submission
