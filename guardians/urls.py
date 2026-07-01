"""Guardians URLs. ``config/urls.py`` mounts this under ``/api/v1/`` so the
router paths resolve to ``/api/v1/guardians/``, ``/api/v1/guardians/{id}/`` and
``/api/v1/guardians/parent/children/``.
"""
from rest_framework.routers import DefaultRouter

from guardians.views import ParentLinkViewSet

app_name = "guardians"

router = DefaultRouter()
router.register("guardians", ParentLinkViewSet, basename="guardians")

urlpatterns = router.urls
