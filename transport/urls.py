"""Transport URLs. ``config/urls.py`` mounts this under ``/api/v1/`` so the
router paths resolve to ``/api/v1/transport/routes/``,
``/api/v1/transport/routes/{id}/live/``, etc.
"""
from rest_framework.routers import DefaultRouter

from transport.views import (
    BusLiveStatusViewSet,
    BusRouteViewSet,
    BusStopViewSet,
)

app_name = "transport"

router = DefaultRouter()
router.register("transport/routes", BusRouteViewSet, basename="busroute")
router.register("transport/stops", BusStopViewSet, basename="busstop")
router.register("transport/live-status", BusLiveStatusViewSet, basename="buslivestatus")

urlpatterns = router.urls
