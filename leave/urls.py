"""Leave URLs. ``config/urls.py`` mounts this under ``/api/v1/`` so paths
resolve to:

- ``/api/v1/leaves/`` (list own; ``POST`` apply),
- ``/api/v1/leaves/{id}/`` (retrieve),
- ``/api/v1/leaves/{id}/approve/`` (approve),
- ``/api/v1/leaves/{id}/reject/`` (reject).
"""
from rest_framework.routers import DefaultRouter

from leave.views import LeaveRequestViewSet

app_name = "leave"

router = DefaultRouter()
router.register("leaves", LeaveRequestViewSet, basename="leaves")

urlpatterns = [
    *router.urls,
]
