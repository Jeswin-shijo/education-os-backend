"""Administration URLs. ``config/urls.py`` mounts this under ``/api/v1/`` so the
paths resolve to ``/api/v1/admin/...``:

- ``/admin/audit-logs`` (+ ``/{id}``)
- ``/admin/dashboard``
- ``/admin/users`` (+ ``/{id}``, ``/{id}/role``, ``/{id}/active``)
- ``/admin/roles``
- ``/admin/permissions``
"""
from django.urls import path
from rest_framework.routers import DefaultRouter

from administration.views import (
    AdminDashboardView,
    AdminUserViewSet,
    AuditLogViewSet,
    PermissionsView,
    RolesView,
)

app_name = "administration"

router = DefaultRouter()
router.register("admin/audit-logs", AuditLogViewSet, basename="admin-audit-logs")
router.register("admin/users", AdminUserViewSet, basename="admin-users")

urlpatterns = [
    path("admin/dashboard", AdminDashboardView.as_view(), name="admin-dashboard"),
    path("admin/roles", RolesView.as_view(), name="admin-roles"),
    path("admin/permissions", PermissionsView.as_view(), name="admin-permissions"),
    *router.urls,
]
