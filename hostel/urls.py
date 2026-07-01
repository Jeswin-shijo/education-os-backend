"""Hostel URLs. ``config/urls.py`` mounts this under ``/api/v1/`` so the router
paths resolve to ``/api/v1/hostel/`` (the allocation collection),
``/api/v1/hostel/info/`` (the requesting student's ``HostelInfo``),
``/api/v1/hostel-blocks/`` and ``/api/v1/hostel-rooms/``.

The router registers the ``info`` custom action ahead of the ``{pk}`` detail
route, so ``/hostel/info/`` never collides with a UUID lookup.
"""
from rest_framework.routers import DefaultRouter

from hostel.views import (
    HostelAllocationViewSet,
    HostelBlockViewSet,
    HostelRoomViewSet,
)

app_name = "hostel"

router = DefaultRouter()
# `hostel` is the allocation collection; its `info` action serves GET /hostel.
router.register("hostel", HostelAllocationViewSet, basename="hostel-allocation")
router.register("hostel-blocks", HostelBlockViewSet, basename="hostel-block")
router.register("hostel-rooms", HostelRoomViewSet, basename="hostel-room")

urlpatterns = router.urls
