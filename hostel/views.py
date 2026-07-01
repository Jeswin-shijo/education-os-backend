"""HTTP layer for the hostel app.

Three admin/staff CRUD viewsets (blocks, rooms, allocations) all flow writes
through their service (audit + cache-invalidate). The mobile app's
``GET /hostel`` is served by the ``info`` custom action on the allocation
viewset: it returns the app-shaped ``HostelInfo`` for the requesting user's
linked student, cached under the ``hostel`` prefix.
"""
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from core.cache import TTL_LIBRARY, cache_get_or_set, cache_key
from core.viewsets import BaseModelViewSet

from hostel.models import HostelAllocation, HostelBlock, HostelRoom
from hostel.permissions import HOSTEL_MATRIX
from hostel.repositories import HostelAllocationRepository
from hostel.serializers import (
    HostelAllocationSerializer,
    HostelBlockSerializer,
    HostelInfoSerializer,
    HostelRoomSerializer,
)
from hostel.services import (
    HostelAllocationService,
    HostelBlockService,
    HostelRoomService,
)


class HostelBlockViewSet(BaseModelViewSet):
    queryset = HostelBlock.objects.all()
    serializer_class = HostelBlockSerializer
    service_class = HostelBlockService
    permission_matrix = HOSTEL_MATRIX
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["name", "warden"]
    ordering_fields = ["name", "created_at"]


class HostelRoomViewSet(BaseModelViewSet):
    queryset = HostelRoom.objects.select_related("block").all()
    serializer_class = HostelRoomSerializer
    service_class = HostelRoomService
    permission_matrix = HOSTEL_MATRIX
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["block", "capacity"]
    search_fields = ["room_no"]
    ordering_fields = ["room_no", "capacity", "created_at"]


class HostelAllocationViewSet(BaseModelViewSet):
    queryset = HostelAllocation.objects.select_related(
        "student", "room", "room__block"
    ).all()
    serializer_class = HostelAllocationSerializer
    service_class = HostelAllocationService
    permission_matrix = HOSTEL_MATRIX
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ["student", "room", "room__block"]
    ordering_fields = ["created_at", "fees"]

    # -- GET /hostel (mobile contract: HostelInfo for the requesting student) --
    @extend_schema(responses={200: HostelInfoSerializer})
    @action(detail=False, methods=["get"], url_path="info")
    def info(self, request):
        """The requesting user's hostel allocation as the app's ``HostelInfo``.

        The already-serialized ``HostelInfo`` dict is cached per user under the
        ``hostel`` prefix (invalidated on any allocation/room/block write).
        """
        cache_id = cache_key("hostel", "info", request.user.id)

        def _load():
            allocation = (
                HostelAllocationRepository()
                .get_queryset()
                .filter(student__user=request.user)
                .first()
            )
            if allocation is None:
                return None
            return HostelInfoSerializer(allocation).data

        data = cache_get_or_set(cache_id, TTL_LIBRARY, _load)
        if data is None:
            raise NotFound("No hostel allocation is linked to this account.")
        return Response(data)
