"""HTTP layer for the dashboards app.

Three read-only, Redis-cached, per-role aggregation endpoints (mounted under
``/api/v1/`` by the integrate step):

- ``GET /students/me/dashboard`` — the requesting student's dashboard
  (``studentService.StudentDashboard``).
- ``GET /parent/dashboard``      — the requesting parent's child summary
  (``parentService.ParentDashboard``).
- ``GET /faculty/dashboard``     — the requesting faculty's dashboard
  (``facultyService.FacultyDashboard``).

All business logic + caching live in :class:`dashboards.services.DashboardService`;
the views only resolve the caller's linked record, enforce self-scoping, and
return the cached payload. RBAC is applied via
:class:`core.permissions.RoleModelPermission` + the per-endpoint matrices.
"""
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from core.permissions import Role, RoleModelPermission

from dashboards.permissions import (
    FACULTY_DASHBOARD_MATRIX,
    PARENT_DASHBOARD_MATRIX,
    STUDENT_DASHBOARD_MATRIX,
)
from dashboards.serializers import (
    FacultyDashboardSerializer,
    ParentDashboardSerializer,
    StudentDashboardSerializer,
)
from dashboards.services import DashboardService

_STAFF_ROLES = set(Role.STAFF)


class _DashboardViewMixin:
    """Shared wiring: service construction + client IP (mirrors BaseModelViewSet)."""

    permission_classes = [IsAuthenticated, RoleModelPermission]

    def _client_ip(self):
        xff = self.request.META.get("HTTP_X_FORWARDED_FOR")
        if xff:
            return xff.split(",")[0].strip()
        return self.request.META.get("REMOTE_ADDR")

    def get_service(self) -> DashboardService:
        return DashboardService(actor=self.request.user, ip=self._client_ip())


class StudentDashboardViewSet(_DashboardViewMixin, ViewSet):
    """``GET /students/me/dashboard`` — the requesting student's dashboard."""

    permission_matrix = STUDENT_DASHBOARD_MATRIX

    @extend_schema(responses={200: StudentDashboardSerializer})
    @action(detail=False, methods=["get"], url_path="me/dashboard")
    def dashboard(self, request):
        service = self.get_service()
        student = service.repo.student_for_user(request.user)
        if student is None:
            raise NotFound("No student profile is linked to this account.")
        return Response(service.student_dashboard(student))


class ParentDashboardViewSet(_DashboardViewMixin, ViewSet):
    """``GET /parent/dashboard`` — the requesting parent's child summary."""

    permission_matrix = PARENT_DASHBOARD_MATRIX

    @extend_schema(responses={200: ParentDashboardSerializer})
    @action(detail=False, methods=["get"], url_path="dashboard")
    def dashboard(self, request):
        service = self.get_service()
        return Response(service.parent_dashboard(request.user))


class FacultyDashboardViewSet(_DashboardViewMixin, ViewSet):
    """``GET /faculty/dashboard`` — the requesting faculty's dashboard."""

    permission_matrix = FACULTY_DASHBOARD_MATRIX

    @extend_schema(responses={200: FacultyDashboardSerializer})
    @action(detail=False, methods=["get"], url_path="dashboard")
    def dashboard(self, request):
        service = self.get_service()
        profile = service.repo.faculty_profile_for_user(request.user)
        if profile is None:
            raise NotFound("No faculty profile is linked to this account.")
        return Response(service.faculty_dashboard(profile))
