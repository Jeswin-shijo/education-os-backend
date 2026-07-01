"""Admin-console business logic.

- :class:`AdminUserService` — user management (create, set role, activate /
  deactivate) reusing ``accounts`` primitives, with a guard that refuses to
  remove or deactivate the **last active admin** so the console can never lock
  itself out.
- :class:`AdminDashboardService` — system-wide counts across every domain app,
  cached under the ``dashboard`` prefix (TTL 300s) and invalidated on user
  writes.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models import Count

from core.cache import (
    TTL_DASHBOARD,
    cache_get_or_set,
    cache_key,
    invalidate_prefix,
)
from core.models import AuditLog
from core.permissions import Role
from core.services import BaseService

from accounts.repositories import UserRepository

User = get_user_model()

# Cache namespace for the admin dashboard rollup.
_DASHBOARD_PREFIX = "dashboard"
_ADMIN_DASHBOARD_KEY = cache_key("dashboard", "admin", "system")


class LastAdminError(Exception):
    """Raised when an action would remove/deactivate the last active admin."""


class AdminUserService(BaseService):
    """User CRUD for the admin console (reuses ``accounts.User``)."""

    model = User
    entity_name = "User"

    def __init__(self, actor=None, ip=None):
        super().__init__(actor=actor, ip=ip)
        self.users = UserRepository()

    # -- cache ------------------------------------------------------------
    def invalidate_cache(self, instance=None) -> None:
        # Any user mutation changes the dashboard counts.
        invalidate_prefix(_DASHBOARD_PREFIX)

    # -- guards -----------------------------------------------------------
    def _active_admin_count(self, exclude_id=None) -> int:
        qs = self.users.get_queryset().filter(
            role__in=Role.ADMINS, is_active=True
        )
        if exclude_id is not None:
            qs = qs.exclude(pk=exclude_id)
        return qs.count()

    def _is_admin(self, user) -> bool:
        return getattr(user, "role", None) in set(Role.ADMINS)

    def _assert_not_last_admin(self, user) -> None:
        """Refuse if removing/deactivating ``user`` leaves zero active admins."""
        if self._is_admin(user) and user.is_active:
            if self._active_admin_count(exclude_id=user.pk) == 0:
                raise LastAdminError(
                    "Cannot remove or deactivate the last active administrator."
                )

    # -- writes -----------------------------------------------------------
    def create_user(
        self,
        *,
        email: str,
        full_name: str,
        role: str,
        password: str | None = None,
        phone: str = "",
        avatar_color: str = "",
        is_active: bool = True,
    ):
        actor = self._actor_or_none()
        extra = {}
        if avatar_color:
            extra["avatar_color"] = avatar_color
        user = User.objects.create_user(
            email=email,
            password=password or None,
            full_name=full_name,
            role=role,
            phone=phone,
            is_active=is_active,
            **extra,
        )
        if not password:
            user.set_unusable_password()
            user.save(update_fields=["password", "updated_at"])
        if actor is not None:
            user.created_by = actor
            user.updated_by = actor
            user.save(update_fields=["created_by", "updated_by", "updated_at"])
        self.audit(
            AuditLog.ACTION_CREATE,
            entity_id=user.pk,
            changes={"email": email, "role": role},
        )
        self.invalidate_cache(user)
        return user

    def set_role(self, user, role: str):
        old = user.role
        # Demoting the last active admin out of an admin role is a lockout.
        # Check BEFORE mutating ``user.role`` so the guard sees the old role.
        if old in set(Role.ADMINS) and role not in set(Role.ADMINS):
            self._assert_not_last_admin(user)
        user.role = role
        actor = self._actor_or_none()
        fields = ["role", "updated_at"]
        if actor is not None:
            user.updated_by = actor
            fields.append("updated_by")
        user.save(update_fields=fields)
        self.audit(
            AuditLog.ACTION_UPDATE,
            entity_id=user.pk,
            changes={"role": {"from": old, "to": role}},
        )
        self.invalidate_cache(user)
        return user

    def set_active(self, user, is_active: bool):
        if not is_active:
            self._assert_not_last_admin(user)
        user.is_active = is_active
        actor = self._actor_or_none()
        fields = ["is_active", "updated_at"]
        if actor is not None:
            user.updated_by = actor
            fields.append("updated_by")
        user.save(update_fields=fields)
        self.audit(
            AuditLog.ACTION_UPDATE,
            entity_id=user.pk,
            changes={"is_active": is_active},
        )
        self.invalidate_cache(user)
        return user

    def update_user(self, user, **data):
        """Patch simple profile fields (full_name/phone/avatar_color)."""
        if "role" in data:
            self.set_role(user, data.pop("role"))
        if "is_active" in data:
            self.set_active(user, data.pop("is_active"))
        if data:
            user = super().update(user, **data)
        else:
            user.refresh_from_db()
        return user

    def delete_user(self, user):
        self._assert_not_last_admin(user)
        return super().delete(user)


class AdminDashboardService:
    """System-wide counts for the admin console dashboard (cached)."""

    def counts(self) -> dict:
        return cache_get_or_set(_ADMIN_DASHBOARD_KEY, TTL_DASHBOARD, self._build)

    def invalidate(self) -> None:
        invalidate_prefix(_DASHBOARD_PREFIX)

    def _build(self) -> dict:
        # Import inside the method so the app has no hard import-time coupling to
        # every other app (and stays loadable even if one is absent).
        from academics.models import (
            Department,
            Program,
            Section,
            Semester,
            Subject,
            ClassSession,
        )
        from students.models import Student
        from faculty.models import FacultyProfile
        from assignments.models import Assignment
        from exams.models import Exam
        from fees.models import FeeInvoice
        from library.models import Book
        from transport.models import BusRoute
        from materials.models import Material
        from quizzes.models import Quiz
        from notifications.models import Notification

        users_by_role = {
            row["role"]: row["n"]
            for row in User.objects.values("role").annotate(n=Count("id"))
        }

        return {
            "users": {
                "total": sum(users_by_role.values()),
                "byRole": [
                    {"role": value, "count": users_by_role.get(value, 0)}
                    for value, _label in Role.CHOICES
                ],
                "students": users_by_role.get(Role.STUDENT, 0),
                "faculty": users_by_role.get(Role.FACULTY, 0),
                "parents": users_by_role.get(Role.PARENT, 0),
                "admins": users_by_role.get(Role.ADMIN, 0)
                + users_by_role.get(Role.SUPER_ADMIN, 0),
            },
            "academics": {
                "departments": Department.objects.count(),
                "programs": Program.objects.count(),
                "semesters": Semester.objects.count(),
                "sections": Section.objects.count(),
                "subjects": Subject.objects.count(),
                "classSessions": ClassSession.objects.count(),
            },
            "students": Student.objects.count(),
            "facultyProfiles": FacultyProfile.objects.count(),
            "assignments": Assignment.objects.count(),
            "exams": Exam.objects.count(),
            "fees": FeeInvoice.objects.count(),
            "books": Book.objects.count(),
            "busRoutes": BusRoute.objects.count(),
            "materials": Material.objects.count(),
            "quizzes": Quiz.objects.count(),
            "notifications": Notification.objects.count(),
            "auditLogs": AuditLog.objects.count(),
        }
