"""Analytics URLs — HOD + Principal read-only aggregation endpoints.

``config/urls.py`` mounts this under ``/api/v1/`` so the paths resolve to
``/api/v1/hod/*`` and ``/api/v1/principal/*``. These are function-free
``APIView`` routes (no router) because the endpoints are bespoke read
aggregations, not model CRUD.
"""
from django.urls import path

from analytics.views import (
    HodAttendanceView,
    HodDashboardView,
    HodFacultyDetailView,
    HodFacultyView,
    HodProfileView,
    HodStudentsView,
    PrincipalComplaintsView,
    PrincipalDashboardView,
    PrincipalFacultyView,
    PrincipalFeesView,
    PrincipalInsightsView,
    PrincipalPlacementsView,
    PrincipalProfileView,
    PrincipalStudentsView,
)

app_name = "analytics"

urlpatterns = [
    # --- HOD (department scope) ---
    path("hod/dashboard", HodDashboardView.as_view(), name="hod-dashboard"),
    path("hod/me", HodProfileView.as_view(), name="hod-me"),
    path("hod/faculty", HodFacultyView.as_view(), name="hod-faculty"),
    path(
        "hod/faculty/<uuid:faculty_id>",
        HodFacultyDetailView.as_view(),
        name="hod-faculty-detail",
    ),
    path("hod/students", HodStudentsView.as_view(), name="hod-students"),
    path("hod/attendance", HodAttendanceView.as_view(), name="hod-attendance"),
    # --- Principal (institution scope) ---
    path(
        "principal/dashboard",
        PrincipalDashboardView.as_view(),
        name="principal-dashboard",
    ),
    path("principal/me", PrincipalProfileView.as_view(), name="principal-me"),
    path(
        "principal/students",
        PrincipalStudentsView.as_view(),
        name="principal-students",
    ),
    path(
        "principal/faculty", PrincipalFacultyView.as_view(), name="principal-faculty"
    ),
    path("principal/fees", PrincipalFeesView.as_view(), name="principal-fees"),
    path(
        "principal/placements",
        PrincipalPlacementsView.as_view(),
        name="principal-placements",
    ),
    path(
        "principal/complaints",
        PrincipalComplaintsView.as_view(),
        name="principal-complaints",
    ),
    path(
        "principal/insights",
        PrincipalInsightsView.as_view(),
        name="principal-insights",
    ),
]
