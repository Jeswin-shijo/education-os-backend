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
from django.db.models import Count, Q

from core.cache import (
    TTL_ATTENDANCE,
    cache_get_or_set,
    cache_key,
    invalidate_prefix,
)
from core.services import BaseService

from attendance.models import (
    AttendanceEntry,
    AttendanceRecord,
    AttendanceSession,
    AttendanceStatus,
)
from attendance.repositories import (
    AttendanceEntryRepository,
    AttendanceRecordRepository,
    AttendanceSessionRepository,
)

# Cache-key prefix owned by this app.
ATTENDANCE_PREFIX = "attendance"


def _percent(attended, total) -> int:
    """Attended-over-total as a rounded integer percent (0 when no records)."""
    total = total or 0
    attended = attended or 0
    return round(attended / total * 100) if total else 0


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


class AttendanceAnalyticsService:
    """Read-only rollups powering the admin's attendance graph.

    Aggregates :class:`AttendanceRecord` rows (the source of truth for attendance
    percentages) grouped along the academic hierarchy and the assigned faculty:

    * ``by_department`` — ``AttendanceRecord.subject.department`` (code, name).
    * ``by_program``    — ``AttendanceRecord.subject.semester.program`` (code,
      name); records on subjects with no semester/program are skipped.
    * ``by_faculty``    — ``AttendanceRecord.subject.faculty`` (accounts.User
      id + full name); records on subjects with no assigned faculty are skipped.

    A row counts as *attended* when its status is in
    :data:`AttendanceStatus.ATTENDED` (``present`` or ``late``). Every percent is
    ``round(attended / total * 100)`` and defaults to ``0`` for empty groups /
    empty data. The whole payload is cached under ``attendance:analytics`` (TTL
    300s) and is busted by any attendance write via the ``attendance`` prefix.

    This service is read-only: it never mutates state or emits an ``AuditLog``,
    so — like the ``analytics``/``dashboards`` aggregators — it does not subclass
    :class:`core.services.BaseService`.
    """

    ATTENDED = AttendanceStatus.ATTENDED

    def analytics(self) -> dict:
        """Return the cached analytics payload (computing it on a cache miss)."""
        return cache_get_or_set(
            cache_key(ATTENDANCE_PREFIX, "analytics"),
            TTL_ATTENDANCE,
            self._build,
        )

    # -- internals -------------------------------------------------------
    def _build(self) -> dict:
        records = AttendanceRecord.objects.all()
        return {
            "overall_percent": self._overall_percent(records),
            "by_department": self._grouped(
                records,
                "subject__department__code",
                "subject__department__name",
                id_field=False,
            ),
            "by_program": self._grouped(
                records,
                "subject__semester__program__code",
                "subject__semester__program__name",
                id_field=False,
            ),
            "by_faculty": self._grouped(
                records,
                "subject__faculty",
                "subject__faculty__full_name",
                id_field=True,
            ),
        }

    def _overall_percent(self, records) -> int:
        agg = records.aggregate(
            total=Count("id"),
            attended=Count("id", filter=Q(status__in=self.ATTENDED)),
        )
        return _percent(agg["attended"], agg["total"])

    def _grouped(self, records, key_field, name_field, *, id_field) -> list[dict]:
        """Group records by ``key_field`` returning ``[{code|id, name, percent}]``.

        Rows whose grouping key is ``NULL`` (e.g. a subject with no
        semester/program, or no assigned faculty) are skipped so the graph only
        shows real buckets.
        """
        rows = (
            records.values(key_field, name_field)
            .annotate(
                total=Count("id"),
                attended=Count("id", filter=Q(status__in=self.ATTENDED)),
            )
            .order_by(key_field)
        )
        out = []
        for row in rows:
            key = row[key_field]
            if key is None:
                continue
            entry = {
                "name": row[name_field] or "",
                "percent": _percent(row["attended"], row["total"]),
            }
            if id_field:
                entry = {"id": str(key), **entry}
            else:
                entry = {"code": key, **entry}
            out.append(entry)
        return out
