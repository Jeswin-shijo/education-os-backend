"""Business-logic layer for the dashboards app.

Each service composes the source apps' data (via
:class:`dashboards.repositories.DashboardRepository`) into one per-role dashboard
payload and caches it in Redis. The dashboards app **never writes** domain data,
so these services do not extend :class:`core.services.BaseService` (there is no
create/update/delete to audit) — they are read-and-cache aggregators built on the
core cache primitives.

Caching
-------
Every dashboard read goes through :func:`core.cache.cache_get_or_set` with a
per-subject key under the ``dashboards`` prefix and the documented dashboard TTL
(300s, :data:`core.cache.TTL_DASHBOARD`):

* student  → ``dashboards:student:<student_id>``
* parent   → ``dashboards:parent:<parent_user_id>``
* faculty  → ``dashboards:faculty:<faculty_profile_id>``

Invalidation
------------
A dashboard is a *composition* of other apps' data, so it can go stale when any
of those apps writes. Two mechanisms keep it fresh:

1. **TTL (primary).** Dashboards are cheap-to-recompute, tolerate ~5 min of
   staleness, and use the standard 300s dashboard TTL, so every entry self-heals
   without any cross-app coupling.
2. **Explicit bust (targeted).** For write paths that should reflect instantly,
   call :func:`invalidate_student_dashboard` / :func:`invalidate_parent_dashboards`
   / :func:`invalidate_faculty_dashboard` (or :func:`invalidate_all_dashboards`
   for a broad change). These are safe to call from a source app's service
   ``invalidate_cache`` hook; the whole-prefix helper is also exposed so a
   coarse "something changed" signal can bust every dashboard at once.

The dashboards app owns the ``dashboards`` cache prefix exclusively, so busting
the prefix never affects another module's cache.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Optional

from rest_framework.exceptions import NotFound

from academics.models import ClassSession
from core.cache import (
    TTL_DASHBOARD,
    cache_get_or_set,
    cache_key,
    invalidate,
    invalidate_prefix,
)
from exams.services import ExamResultService

from dashboards.repositories import DashboardRepository

# Cache-key prefix owned exclusively by this app.
DASHBOARDS_PREFIX = "dashboards"

# How near a due date counts an assignment as "pending" on the faculty board.
FACULTY_PENDING_HORIZON_DAYS = 3

# Map Python weekday() (Mon=0) to the app's Mon..Sat codes (Sunday -> None).
_WEEKDAY_BY_INDEX = {
    0: ClassSession.DAY_MON,
    1: ClassSession.DAY_TUE,
    2: ClassSession.DAY_WED,
    3: ClassSession.DAY_THU,
    4: ClassSession.DAY_FRI,
    5: ClassSession.DAY_SAT,
}


def _today_code() -> Optional[str]:
    return _WEEKDAY_BY_INDEX.get(date.today().weekday())


# --- Cache-key + invalidation helpers ---------------------------------------
def student_dashboard_key(student_id) -> str:
    return cache_key(DASHBOARDS_PREFIX, "student", student_id)


def parent_dashboard_key(parent_user_id) -> str:
    return cache_key(DASHBOARDS_PREFIX, "parent", parent_user_id)


def faculty_dashboard_key(faculty_profile_id) -> str:
    return cache_key(DASHBOARDS_PREFIX, "faculty", faculty_profile_id)


def invalidate_student_dashboard(student_id) -> None:
    """Bust one student's cached dashboard."""
    invalidate(student_dashboard_key(student_id))


def invalidate_parent_dashboards(parent_user_ids) -> None:
    """Bust the cached dashboards of the given parent user id(s)."""
    for uid in parent_user_ids:
        invalidate(parent_dashboard_key(uid))


def invalidate_faculty_dashboard(faculty_profile_id) -> None:
    """Bust one faculty member's cached dashboard."""
    invalidate(faculty_dashboard_key(faculty_profile_id))


def invalidate_all_dashboards() -> None:
    """Bust every cached dashboard (coarse "something changed" signal)."""
    invalidate_prefix(DASHBOARDS_PREFIX)


class DashboardService:
    """Read-and-cache aggregator for the per-role dashboards.

    Constructed with the acting ``user`` (and optional ``ip`` for parity with the
    other services). All methods are reads; nothing mutates domain data.
    """

    def __init__(self, actor=None, ip=None):
        self.actor = actor
        self.ip = ip
        self.repo = DashboardRepository()

    # -- Student --------------------------------------------------------------
    def student_dashboard(self, student) -> dict[str, Any]:
        """Aggregate + cache one student's dashboard.

        Composition mirrors the app's mock ``studentService.getDashboard``:
        profile + overall attendance % + credit-weighted CGPA + pending
        assignments + today's classes + due-fees total + unread notifications +
        next exam. Cached under ``dashboards:student:<id>`` (TTL 300s).
        """
        return cache_get_or_set(
            student_dashboard_key(student.pk),
            TTL_DASHBOARD,
            lambda: self._build_student_dashboard(student),
        )

    def _build_student_dashboard(self, student) -> dict[str, Any]:
        from dashboards.serializers import StudentDashboardSerializer

        gpa = ExamResultService(actor=self.actor).gpa_for_student(student.pk)
        next_exam = self.repo.next_exam_for_student(student)
        today_sessions = list(
            self.repo.today_sessions(student.section_id, _today_code())
        )

        payload = {
            "student": student,
            "attendancePct": self.repo.attendance_percent(student),
            "cgpa": gpa,
            "pendingAssignments": self.repo.pending_assignment_count(student),
            "todayClasses": today_sessions,
            "dueFees": self.repo.due_fees_total(student),
            "unread": self.repo.unread_notification_count(student.user)
            if student.user_id
            else 0,
            "nextExam": next_exam,
        }
        # Round-trip through the serializer so the cached value is the exact
        # JSON-ready dict the endpoint returns (and the OpenAPI shape).
        return StudentDashboardSerializer(payload).data

    # -- Parent ---------------------------------------------------------------
    def parent_dashboard(self, parent_user) -> dict[str, Any]:
        """Aggregate + cache the parent's dashboard for their (primary) child.

        Mirrors ``parentService.getDashboard``: child summary + attendance % +
        CGPA + due fees + pending leave approvals + unread chats + unread
        notifications + next exam. Cached under ``dashboards:parent:<uid>``.
        """
        return cache_get_or_set(
            parent_dashboard_key(parent_user.pk),
            TTL_DASHBOARD,
            lambda: self._build_parent_dashboard(parent_user),
        )

    def _build_parent_dashboard(self, parent_user) -> dict[str, Any]:
        from dashboards.serializers import ParentDashboardSerializer

        link = self.repo.primary_child_link(parent_user)
        if link is None:
            raise NotFound("No child is linked to this parent account.")
        child = link.student

        gpa = ExamResultService(actor=self.actor).gpa_for_student(child.pk)
        payload = {
            "child": child,
            "attendancePct": self.repo.attendance_percent(child),
            "cgpa": gpa,
            "dueFees": self.repo.due_fees_total(child),
            "pendingApprovals": self.repo.pending_child_leaves(child),
            "unreadChats": self.repo.unread_chat_count(parent_user),
            "unreadNotifications": self.repo.unread_notification_count(parent_user),
            "nextExam": self.repo.next_exam_for_student(child),
        }
        return ParentDashboardSerializer(payload).data

    # -- Faculty --------------------------------------------------------------
    def faculty_dashboard(self, profile) -> dict[str, Any]:
        """Aggregate + cache a faculty member's dashboard.

        Mirrors ``facultyService.getDashboard``: faculty user + class count +
        student count + today's classes (``{class, slot}``) + pending assignments
        + quiz count + unread notifications. Cached under
        ``dashboards:faculty:<profile_id>``.
        """
        return cache_get_or_set(
            faculty_dashboard_key(profile.pk),
            TTL_DASHBOARD,
            lambda: self._build_faculty_dashboard(profile),
        )

    def _build_faculty_dashboard(self, profile) -> dict[str, Any]:
        from faculty.serializers import FacultyClassAppSerializer

        classes = list(self.repo.faculty_classes(profile))
        today_code = _today_code()
        today_classes = []
        if today_code is not None:
            for klass in classes:
                for slot in klass.slots or []:
                    if slot.get("day") == today_code:
                        today_classes.append(
                            {
                                "class": FacultyClassAppSerializer(klass).data,
                                "slot": slot,
                            }
                        )
            # Stable order: earliest slot first.
            today_classes.sort(key=lambda e: e["slot"].get("start", ""))

        horizon = date.today() + timedelta(days=FACULTY_PENDING_HORIZON_DAYS)
        u = profile.user
        return {
            "faculty": {
                "id": str(u.id),
                "name": u.full_name,
                "email": u.email,
                "role": u.role,
                "avatarColor": u.avatar_color,
            },
            "classCount": len(classes),
            "studentCount": self.repo.faculty_student_count(profile),
            "todayClasses": today_classes,
            "pendingAssignments": self.repo.faculty_pending_assignments(
                profile, horizon
            ),
            "quizCount": self.repo.faculty_quiz_count(profile),
            "unreadNotifications": self.repo.unread_notification_count(u),
        }
