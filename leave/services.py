"""Business-logic layer for the leave app.

:class:`LeaveRequestService` extends :class:`core.services.BaseService` so writes
auto-stamp ``created_by``/``updated_by``, emit an :class:`~core.models.AuditLog`
row, and invalidate cached leave views (``leave`` prefix).

It also owns the approval workflow and its *scoping* rules — the question of
*whose* leave a given approver may decide:

- **admin / super_admin** — any request.
- **parent** — a child they are linked to (``guardians.ParentLink`` →
  ``student.user``).
- **faculty / hod** — a student whose ``department`` matches the approver's
  :class:`faculty.FacultyProfile` department.

An approver may never decide their own request, and only ``pending`` requests
can be approved/rejected.
"""
from __future__ import annotations

from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from core.cache import invalidate_prefix
from core.permissions import Role
from core.services import BaseService

from leave.models import LeaveRequest
from leave.repositories import LeaveRequestRepository

# Cache-key prefix owned by this app.
LEAVE_PREFIX = "leave"


class LeaveRequestService(BaseService):
    model = LeaveRequest
    repository_class = LeaveRequestRepository
    entity_name = "LeaveRequest"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(LEAVE_PREFIX)

    # -- application ------------------------------------------------------
    def apply(self, user, *, type, start_date, end_date, reason="") -> LeaveRequest:
        """File a new leave request for ``user`` (status ``pending``)."""
        if end_date < start_date:
            raise ValidationError("end_date cannot be before start_date.")
        return self.create(
            user=user,
            type=type,
            start_date=start_date,
            end_date=end_date,
            reason=reason,
            status=LeaveRequest.STATUS_PENDING,
        )

    # -- approval workflow -----------------------------------------------
    def approve(self, leave: LeaveRequest, approver) -> LeaveRequest:
        return self._decide(leave, approver, LeaveRequest.STATUS_APPROVED)

    def reject(self, leave: LeaveRequest, approver) -> LeaveRequest:
        return self._decide(leave, approver, LeaveRequest.STATUS_REJECTED)

    def _decide(self, leave: LeaveRequest, approver, status: str) -> LeaveRequest:
        if leave.status != LeaveRequest.STATUS_PENDING:
            raise ValidationError(
                f"Leave request is already {leave.status}; only pending "
                "requests can be decided."
            )
        if leave.user_id == getattr(approver, "id", None):
            raise PermissionDenied("You cannot decide your own leave request.")
        if not self.can_decide(approver, leave):
            raise PermissionDenied(
                "You are not authorised to decide this leave request."
            )
        return self.update(leave, status=status, decided_by=approver)

    # -- scoping ----------------------------------------------------------
    def can_decide(self, approver, leave: LeaveRequest) -> bool:
        """Whether ``approver`` may approve/reject ``leave`` (see module docs)."""
        role = getattr(approver, "role", None)

        # Admins decide everything.
        if role in set(Role.ADMINS):
            return True

        # Parent decides their linked children's requests.
        if role == Role.PARENT:
            return self._is_parent_of(approver, leave.user_id)

        # Faculty / HOD decide students in their department.
        if role in (Role.FACULTY, Role.HOD):
            return self._is_student_in_department(approver, leave.user_id)

        return False

    @staticmethod
    def _is_parent_of(parent, student_user_id) -> bool:
        from guardians.models import ParentLink

        if not student_user_id:
            return False
        return ParentLink.objects.filter(
            parent=parent, student__user_id=student_user_id
        ).exists()

    @staticmethod
    def _is_student_in_department(approver, student_user_id) -> bool:
        from faculty.models import FacultyProfile
        from students.models import Student

        if not student_user_id:
            return False
        profile = (
            FacultyProfile.objects.filter(user=approver)
            .select_related("department")
            .first()
        )
        if profile is None:
            return False
        return Student.objects.filter(
            user_id=student_user_id, department_id=profile.department_id
        ).exists()

    # -- queryset scoping (for list/retrieve) ----------------------------
    def visible_queryset(self, viewer):
        """Return the leave requests ``viewer`` may see.

        Everyone sees their own requests. Approvers additionally see the
        requests they are entitled to decide (children / department students),
        so the mobile "pending approvals" surface has data to act on. Admins see
        all.
        """
        from django.db.models import Q

        from faculty.models import FacultyProfile
        from guardians.models import ParentLink

        base = self.repository.get_queryset()
        role = getattr(viewer, "role", None)

        if role in set(Role.ADMINS):
            return base

        # Own requests always visible.
        scope = Q(user_id=viewer.id)

        if role == Role.PARENT:
            child_user_ids = list(
                ParentLink.objects.filter(parent=viewer)
                .exclude(student__user__isnull=True)
                .values_list("student__user_id", flat=True)
            )
            if child_user_ids:
                scope |= Q(user_id__in=child_user_ids)

        elif role in (Role.FACULTY, Role.HOD):
            profile = FacultyProfile.objects.filter(user=viewer).first()
            if profile is not None:
                from students.models import Student

                dept_user_ids = list(
                    Student.objects.filter(department_id=profile.department_id)
                    .exclude(user__isnull=True)
                    .values_list("user_id", flat=True)
                )
                if dept_user_ids:
                    scope |= Q(user_id__in=dept_user_ids)

        return base.filter(scope)
