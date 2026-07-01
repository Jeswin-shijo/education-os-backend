"""Complaints URLs. ``config/urls.py`` mounts this under ``/api/v1/`` so the
router paths resolve to ``/api/v1/complaints/``, ``/api/v1/complaints/{id}/``,
and ``/api/v1/complaints/monitor/``.
"""
from rest_framework.routers import DefaultRouter

from complaints.views import ComplaintViewSet

app_name = "complaints"

router = DefaultRouter()
router.register("complaints", ComplaintViewSet, basename="complaints")

urlpatterns = router.urls
