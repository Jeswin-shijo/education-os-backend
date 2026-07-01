"""Faculty URLs. ``config/urls.py`` mounts this under ``/api/v1/`` so the router
paths resolve to ``/api/v1/faculty/``, ``/api/v1/faculty/me/``,
``/api/v1/faculty/classes/``, ``/api/v1/faculty/classes/{id}/``, and
``/api/v1/faculty/classes/{id}/roster/``.
"""
from rest_framework.routers import DefaultRouter

from faculty.views import FacultyProfileViewSet

app_name = "faculty"

router = DefaultRouter()
router.register("faculty", FacultyProfileViewSet, basename="faculty")

urlpatterns = router.urls
