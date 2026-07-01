"""Academics URLs. ``config/urls.py`` mounts this under ``/api/v1/`` so the
router paths resolve to ``/api/v1/departments/``, ``/api/v1/subjects/{id}``,
``/api/v1/timetable/week/``, etc.
"""
from rest_framework.routers import DefaultRouter

from academics.views import (
    DepartmentViewSet,
    ProgramViewSet,
    SectionViewSet,
    SemesterViewSet,
    SubjectViewSet,
    TimetableViewSet,
)

app_name = "academics"

router = DefaultRouter()
router.register("departments", DepartmentViewSet, basename="department")
router.register("programs", ProgramViewSet, basename="program")
router.register("semesters", SemesterViewSet, basename="semester")
router.register("sections", SectionViewSet, basename="section")
router.register("subjects", SubjectViewSet, basename="subject")
router.register("timetable", TimetableViewSet, basename="timetable")

urlpatterns = router.urls
