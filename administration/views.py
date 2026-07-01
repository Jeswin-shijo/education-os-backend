"""HTTP layer for the admin console (``/api/v1/admin/``).

All endpoints are restricted to ``super_admin``/``admin`` via
:class:`core.permissions.RoleModelPermission` + :data:`ADMIN_ONLY_MATRIX`.

- ``GET /admin/audit-logs`` — browse ``core.AuditLog`` (filter entity/actor/
  action/entity_id, searchable, paginated).
- ``GET /admin/dashboard`` — system-wide counts across every domain app (cached).
- ``GET/POST /admin/users`` · ``GET/PATCH/DELETE /admin/users/{id}`` — user
  management; plus ``PATCH /admin/users/{id}/role`` and
  ``PATCH /admin/users/{id}/active``. Guards the last active admin.
- ``GET /admin/roles`` — the RBAC role catalogue.
- ``GET /admin/permissions`` — the per-area RBAC matrix (read).

Writes flow through :class:`administration.services.AdminUserService` (audit +
cache-invalidation).
"""
from django.contrib.auth import get_user_model
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import AuditLog
from core.permissions import Role, RoleModelPermission

from administration.permissions import ADMIN_ONLY_MATRIX
from administration.repositories import AuditLogRepository
from administration.serializers import (
    AdminUserCreateSerializer,
    AdminUserSerializer,
    AdminUserUpdateSerializer,
    AuditLogSerializer,
    RoleSerializer,
    SetActiveSerializer,
    SetRoleSerializer,
)
from administration.services import (
    AdminDashboardService,
    AdminUserService,
    LastAdminError,
)

User = get_user_model()


def _client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


# --- Audit logs --------------------------------------------------------------
class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only browsing of the immutable audit trail."""

    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated, RoleModelPermission]
    permission_matrix = ADMIN_ONLY_MATRIX
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["entity", "action", "actor", "entity_id"]
    search_fields = ["entity", "entity_id"]
    ordering_fields = ["at", "action", "entity"]
    ordering = ["-at"]
    queryset = AuditLog.objects.select_related("actor").all()

    def get_queryset(self):
        return AuditLogRepository().all()


# --- Dashboard ---------------------------------------------------------------
class AdminDashboardView(APIView):
    """``GET /admin/dashboard`` — system counts across all apps (cached 300s)."""

    permission_classes = [IsAuthenticated, RoleModelPermission]
    permission_matrix = ADMIN_ONLY_MATRIX

    @extend_schema(responses={200: dict})
    def get(self, request):
        return Response(AdminDashboardService().counts())


# --- Users -------------------------------------------------------------------
class AdminUserViewSet(viewsets.ModelViewSet):
    """User management: directory, create, role change, activate/deactivate."""

    permission_classes = [IsAuthenticated, RoleModelPermission]
    permission_matrix = ADMIN_ONLY_MATRIX
    serializer_class = AdminUserSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["role", "is_active"]
    search_fields = ["full_name", "email", "phone"]
    ordering_fields = ["full_name", "email", "role", "created_at"]
    ordering = ["full_name"]
    queryset = User.objects.all()

    def get_service(self):
        return AdminUserService(actor=self.request.user, ip=_client_ip(self.request))

    # -- create ----------------------------------------------------------
    @extend_schema(request=AdminUserCreateSerializer, responses={201: AdminUserSerializer})
    def create(self, request, *args, **kwargs):
        serializer = AdminUserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = self.get_service().create_user(**serializer.validated_data)
        return Response(AdminUserSerializer(user).data, status=status.HTTP_201_CREATED)

    # -- patch profile / role / active -----------------------------------
    @extend_schema(request=AdminUserUpdateSerializer, responses={200: AdminUserSerializer})
    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = AdminUserUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            user = self.get_service().update_user(instance, **serializer.validated_data)
        except LastAdminError as exc:
            raise ValidationError(str(exc))
        return Response(AdminUserSerializer(user).data)

    def update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.partial_update(request, *args, **kwargs)

    # -- delete ----------------------------------------------------------
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            self.get_service().delete_user(instance)
        except LastAdminError as exc:
            raise ValidationError(str(exc))
        return Response(status=status.HTTP_204_NO_CONTENT)

    # -- set role --------------------------------------------------------
    @extend_schema(request=SetRoleSerializer, responses={200: AdminUserSerializer})
    @action(detail=True, methods=["patch"], url_path="role")
    def set_role(self, request, pk=None):
        instance = self.get_object()
        serializer = SetRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = self.get_service().set_role(instance, serializer.validated_data["role"])
        except LastAdminError as exc:
            raise ValidationError(str(exc))
        return Response(AdminUserSerializer(user).data)

    # -- activate / deactivate -------------------------------------------
    @extend_schema(request=SetActiveSerializer, responses={200: AdminUserSerializer})
    @action(detail=True, methods=["patch"], url_path="active")
    def set_active(self, request, pk=None):
        instance = self.get_object()
        serializer = SetActiveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = self.get_service().set_active(instance, serializer.validated_data["active"])
        except LastAdminError as exc:
            raise ValidationError(str(exc))
        return Response(AdminUserSerializer(user).data)


# --- Roles & permissions -----------------------------------------------------
class RolesView(APIView):
    """``GET /admin/roles`` — the canonical RBAC role catalogue."""

    permission_classes = [IsAuthenticated, RoleModelPermission]
    permission_matrix = ADMIN_ONLY_MATRIX

    @extend_schema(responses={200: RoleSerializer(many=True)})
    def get(self, request):
        data = [{"value": value, "label": label} for value, label in Role.CHOICES]
        return Response(data)


# Per-area RBAC matrix, mirroring the BUILD_CONTRACT table. Read-only reference
# so the console can render who-can-do-what.
PERMISSION_MATRIX = {
    "own_profile_dashboard": {
        "student": "RW(self)", "parent": "R(child)", "faculty": "RW(self)",
        "hod": "RW(self)", "principal": "R", "admin": "R",
    },
    "attendance": {
        "student": "R(self)", "parent": "R(child)", "faculty": "RW(own classes)",
        "hod": "R(dept)", "principal": "R", "admin": "RW",
    },
    "marks_results": {
        "student": "R(self)", "parent": "R(child)", "faculty": "RW(own classes)",
        "hod": "R(dept)", "principal": "R", "admin": "RW",
    },
    "fees": {
        "student": "R(self)", "parent": "R+pay(child)", "faculty": "-",
        "hod": "R(dept)", "principal": "R", "admin": "RW",
    },
    "assignments_materials_quizzes": {
        "student": "R+submit", "parent": "R(child)", "faculty": "RW(own)",
        "hod": "R(dept)", "principal": "R", "admin": "RW",
    },
    "library_hostel_transport_events_certificates": {
        "student": "R", "parent": "R(child)", "faculty": "R",
        "hod": "R", "principal": "R", "admin": "RW",
    },
    "complaints": {
        "student": "RW(self)", "parent": "RW(child)", "faculty": "R",
        "hod": "R", "principal": "R(monitor)", "admin": "RW",
    },
    "leave": {
        "student": "RW(self)", "parent": "approve(child)", "faculty": "RW(self)+approve(students)",
        "hod": "approve", "principal": "R", "admin": "RW",
    },
    "notifications": {
        "student": "R(self)", "parent": "R(self)", "faculty": "R(self)",
        "hod": "R", "principal": "R", "admin": "RW(broadcast)",
    },
    "analytics_reports": {
        "student": "-", "parent": "-", "faculty": "-",
        "hod": "R(dept)", "principal": "R(institution)", "admin": "R",
    },
    "user_role_permission_mgmt": {
        "student": "-", "parent": "-", "faculty": "-",
        "hod": "-", "principal": "-", "admin": "RW",
    },
}


class PermissionsView(APIView):
    """``GET /admin/permissions`` — the per-area RBAC matrix (read)."""

    permission_classes = [IsAuthenticated, RoleModelPermission]
    permission_matrix = ADMIN_ONLY_MATRIX

    @extend_schema(responses={200: dict})
    def get(self, request):
        return Response({
            "roles": [value for value, _ in Role.CHOICES],
            "matrix": PERMISSION_MATRIX,
        })
