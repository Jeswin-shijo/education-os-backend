"""Background jobs for the faculty app.

Currently the faculty module has no long-running work; ``recount_class_students``
is provided as a Celery task so ``student_count`` can be reconciled from the
roster off the request path (e.g. after bulk roster edits or an import).
"""
from __future__ import annotations

from celery import shared_task

from faculty.models import FacultyClass, RosterEntry


@shared_task(name="faculty.recount_class_students")
def recount_class_students(faculty_class_id: str) -> int:
    """Recompute a class's ``student_count`` from its live roster entries."""
    count = RosterEntry.objects.filter(faculty_class_id=faculty_class_id).count()
    FacultyClass.objects.filter(pk=faculty_class_id).update(student_count=count)
    return count
