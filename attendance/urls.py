"""Attendance URLs. ``config/urls.py`` mounts this under ``/api/v1/`` so the
paths resolve to the mobile contract exactly:

Student self-scoped reads:
- ``GET  /api/v1/attendance/summary``
- ``GET  /api/v1/attendance/overall``
- ``GET  /api/v1/attendance/records`` (``?subjectId=``)

Faculty session endpoints:
- ``POST /api/v1/attendance``                 (save a session)
- ``GET  /api/v1/faculty/attendance``         (``?classId=``)

Admin CRUD over raw attendance records lives under ``/api/v1/attendance/records``
via the router (list/create/retrieve/update/destroy), keeping the bare
``/attendance`` collection root free for the faculty save-session POST.

All routes are served by the single :class:`AttendanceViewSet`; ``as_view`` maps
HTTP methods to viewset actions so ``RoleModelPermission`` sees the right
``action`` for the per-endpoint RBAC matrix.
"""
from django.urls import path
from rest_framework.routers import DefaultRouter

from attendance.views import AttendanceViewSet

app_name = "attendance"

# Admin CRUD surface for raw AttendanceRecord rows (not part of the mobile
# contract but the standard management surface for this domain). Mounted under
# ``attendance/manage`` so the contract's ``/attendance/records`` GET stays free.
router = DefaultRouter()
router.register("attendance/manage", AttendanceViewSet, basename="attendance-manage")

urlpatterns = [
    # Student self-scoped reads.
    path(
        "attendance/summary",
        AttendanceViewSet.as_view({"get": "summary"}),
        name="attendance-summary",
    ),
    path(
        "attendance/overall",
        AttendanceViewSet.as_view({"get": "overall"}),
        name="attendance-overall",
    ),
    path(
        "attendance/records",
        AttendanceViewSet.as_view({"get": "records"}),
        name="attendance-records",
    ),
    # Faculty: save a session (POST /attendance) + list sessions.
    path(
        "attendance",
        AttendanceViewSet.as_view({"post": "create_session"}),
        name="attendance-save-session",
    ),
    path(
        "faculty/attendance",
        AttendanceViewSet.as_view({"get": "faculty_sessions"}),
        name="attendance-faculty-sessions",
    ),
] + router.urls
