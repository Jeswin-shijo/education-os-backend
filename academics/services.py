"""Business-logic layer for the academics app.

Each service extends :class:`core.services.BaseService` so writes auto-stamp
``created_by``/``updated_by``, emit an :class:`~core.models.AuditLog` row, and
invalidate the relevant cached views. Timetable and subject reads are cached
(TTL 3600s per the contract); any write to a subject or class session busts the
``timetable``/``subjects`` cache prefixes.
"""
from __future__ import annotations

from core.cache import invalidate_prefix
from core.services import BaseService

from academics.models import (
    ClassSession,
    Department,
    Program,
    Section,
    Semester,
    Subject,
)
from academics.repositories import (
    ClassSessionRepository,
    DepartmentRepository,
    ProgramRepository,
    SectionRepository,
    SemesterRepository,
    SubjectRepository,
)

# Cache key prefixes owned by this app.
TIMETABLE_PREFIX = "timetable"
SUBJECTS_PREFIX = "subjects"


class DepartmentService(BaseService):
    model = Department
    repository_class = DepartmentRepository
    entity_name = "Department"


class ProgramService(BaseService):
    model = Program
    repository_class = ProgramRepository
    entity_name = "Program"


class SemesterService(BaseService):
    model = Semester
    repository_class = SemesterRepository
    entity_name = "Semester"


class SectionService(BaseService):
    model = Section
    repository_class = SectionRepository
    entity_name = "Section"

    def invalidate_cache(self, instance=None) -> None:
        # Sections shape the timetable grid grouping.
        invalidate_prefix(TIMETABLE_PREFIX)


class SubjectService(BaseService):
    model = Subject
    repository_class = SubjectRepository
    entity_name = "Subject"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(SUBJECTS_PREFIX)
        invalidate_prefix(TIMETABLE_PREFIX)


class ClassSessionService(BaseService):
    model = ClassSession
    repository_class = ClassSessionRepository
    entity_name = "ClassSession"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(TIMETABLE_PREFIX)
