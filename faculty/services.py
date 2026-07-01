"""Business-logic layer for the faculty app.

Each service extends :class:`core.services.BaseService` so writes auto-stamp
``created_by``/``updated_by``, emit an :class:`~core.models.AuditLog` row, and
invalidate cached faculty views. Faculty profile/class reads are cached under
the ``faculty`` prefix; any write busts that prefix.
"""
from __future__ import annotations

from core.cache import invalidate_prefix
from core.services import BaseService

from faculty.models import FacultyClass, FacultyProfile, RosterEntry
from faculty.repositories import (
    FacultyClassRepository,
    FacultyProfileRepository,
    RosterEntryRepository,
)

# Cache-key prefix owned by this app.
FACULTY_PREFIX = "faculty"


class FacultyProfileService(BaseService):
    model = FacultyProfile
    repository_class = FacultyProfileRepository
    entity_name = "FacultyProfile"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(FACULTY_PREFIX)


class FacultyClassService(BaseService):
    model = FacultyClass
    repository_class = FacultyClassRepository
    entity_name = "FacultyClass"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(FACULTY_PREFIX)


class RosterEntryService(BaseService):
    model = RosterEntry
    repository_class = RosterEntryRepository
    entity_name = "RosterEntry"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(FACULTY_PREFIX)
