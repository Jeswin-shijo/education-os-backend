"""Exams URLs. ``config/urls.py`` mounts this under ``/api/v1/`` so the paths
resolve to:

- ``/api/v1/exams/``            (list) and ``/api/v1/exams/upcoming/``
- ``/api/v1/results/``          (list) and ``/api/v1/results/gpa/``
- ``/api/v1/marks/``            (POST — faculty marks-sheet upsert)
- ``/api/v1/faculty/marks/``    (GET  — the faculty's marks sheets)
- plus admin/faculty CRUD detail routes for exams/results.

The two faculty-marks endpoints have bespoke paths (``/marks`` and
``/faculty/marks``) so they are wired explicitly rather than via the router
prefix, while exams/results use a standard :class:`DefaultRouter`.
"""
from django.urls import path
from rest_framework.routers import DefaultRouter

from exams.views import ExamResultViewSet, ExamViewSet, MarksSheetViewSet

app_name = "exams"

router = DefaultRouter()
router.register("exams", ExamViewSet, basename="exams")
router.register("results", ExamResultViewSet, basename="results")

# Faculty marks entry — explicit paths (POST /marks, GET /faculty/marks).
marks_save = MarksSheetViewSet.as_view({"post": "save_marks"})
faculty_marks = MarksSheetViewSet.as_view({"get": "faculty_marks"})

urlpatterns = [
    path("marks/", marks_save, name="marks-save"),
    path("faculty/marks/", faculty_marks, name="faculty-marks"),
] + router.urls
