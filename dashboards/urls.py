"""Dashboards URLs.

``config/urls.py`` mounts this under ``/api/v1/`` so the router paths resolve to:

- ``/api/v1/students/me/dashboard/`` — :class:`StudentDashboardViewSet`
- ``/api/v1/parent/dashboard/``      — :class:`ParentDashboardViewSet`
- ``/api/v1/faculty/dashboard/``     — :class:`FacultyDashboardViewSet`

Each viewset exposes a single ``dashboard`` action (via ``@action`` ``url_path``)
under its role's base prefix. The base prefixes overlap with the students/parent/
faculty apps' own routers, but DRF routers only own the exact paths they register
(here: the ``.../dashboard`` sub-paths), so mounting alongside those apps is safe.
"""
from rest_framework.routers import DefaultRouter

from dashboards.views import (
    FacultyDashboardViewSet,
    ParentDashboardViewSet,
    StudentDashboardViewSet,
)

app_name = "dashboards"

router = DefaultRouter()
router.register("students", StudentDashboardViewSet, basename="student-dashboard")
router.register("parent", ParentDashboardViewSet, basename="parent-dashboard")
router.register("faculty", FacultyDashboardViewSet, basename="faculty-dashboard")

urlpatterns = router.urls
