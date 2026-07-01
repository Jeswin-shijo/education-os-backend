"""Business-logic layer for the attendance app.

Each service extends :class:`core.services.BaseService` so writes auto-stamp
``created_by``/``updated_by``, emit an :class:`~core.models.AuditLog` row, and
invalidate cached attendance views. All attendance reads are cached under the
``attendance`` prefix (TTL 300s); any write busts that prefix.

The interesting logic lives in :meth:`AttendanceSessionService.save_session`,
which upserts a faculty attendance take by ``(faculty_class, date)`` and replaces
its entries transactionally.
"""
from __future__ import annotations

from django.db import transaction

from core.cache import invalidate_prefix
from core.services import BaseService

from attendance.models import (
    AttendanceEntry,
    AttendanceRecord,
    AttendanceSession,
)
from attendance.repositories import (
    AttendanceEntryRepository,
    AttendanceRecordRepository,
    AttendanceSessionRepository,
)

# Cache-key prefix owned by this app.
ATTENDANCE_PREFIX = "attendance"


class AttendanceRecordService(BaseService):
    model = AttendanceRecord
    repository_class = AttendanceRecordRepository
    entity_name = "AttendanceRecord"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(ATTENDANCE_PREFIX)


class AttendanceSessionService(BaseService):
    model = AttendanceSession
    repository_class = AttendanceSessionRepository
    entity_name = "AttendanceSession"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(ATTENDANCE_PREFIX)

    @transaction.atomic
    def save_session(self, faculty_class, date, entries):
        """Upsert an attendance session for ``(faculty_class, date)``.

        ``entries`` is a list of ``{"student_ref", "roll_no", "status"}`` dicts.
        Any existing session for that class/date is reused (its entries replaced)
        so re-saving is idempotent — matching the app's upsert-by-(classId,date)
        behaviour. Writes are audited + cache-invalidated.
        """
        session = (
            AttendanceSession.objects.filter(
                faculty_class=faculty_class, date=date
            ).first()
        )
        if session is None:
            session = self.create(faculty_class=faculty_class, date=date)
        else:
            # Touch/stamp + audit the update, then clear old entries.
            session = self.update(session, date=date)
            AttendanceEntry.objects.filter(session=session).delete()

        actor = self._actor_or_none()
        AttendanceEntry.objects.bulk_create(
            [
                AttendanceEntry(
                    session=session,
                    student_ref=e.get("student_ref"),
                    roll_no=e.get("roll_no", ""),
                    status=e["status"],
                    created_by=actor,
                    updated_by=actor,
                )
                for e in entries
            ]
        )
        self.invalidate_cache(session)
        return session


class AttendanceEntryService(BaseService):
    model = AttendanceEntry
    repository_class = AttendanceEntryRepository
    entity_name = "AttendanceEntry"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(ATTENDANCE_PREFIX)
