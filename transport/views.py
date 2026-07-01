"""HTTP layer for the transport app.

- ``GET /transport/routes/`` — list routes (app-shaped, nested stops), cached.
- ``GET /transport/routes/{id}/`` — a single route (app-shaped), cached.
- ``GET /transport/routes/{id}/live/`` — live status for a route, cached.
- Admin CRUD on routes (and stops / live-status management viewsets) flows
  through the service layer (audit + cache-invalidation) via
  :class:`core.viewsets.BaseModelViewSet`.

The realtime WebSocket consumer (live push) is added in a later step; this
module exposes the REST reads now.
"""
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from core.cache import TTL_LIBRARY, cache_get_or_set, cache_key
from core.viewsets import BaseModelViewSet

from transport.models import BusLiveStatus, BusRoute, BusStop
from transport.permissions import ADMIN_WRITE_MATRIX, TRANSPORT_MATRIX
from transport.serializers import (
    BusLiveStatusAppSerializer,
    BusLiveStatusSerializer,
    BusRouteAppSerializer,
    BusRouteSerializer,
    BusStopSerializer,
)
from transport.services import (
    BusLiveStatusService,
    BusRouteService,
    BusStopService,
)

# Transport reads are relatively static; reuse the library TTL (600s).
TTL_TRANSPORT = TTL_LIBRARY
TRANSPORT_PREFIX = "transport"


class BusRouteViewSet(BaseModelViewSet):
    """Bus routes: ``GET /transport/routes`` + admin CRUD + ``.../{id}/live``."""

    queryset = BusRoute.objects.prefetch_related("stops").all()
    serializer_class = BusRouteSerializer
    service_class = BusRouteService
    permission_matrix = TRANSPORT_MATRIX
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["number"]
    search_fields = ["name", "number", "driver"]
    ordering_fields = ["number", "name", "created_at"]

    def list(self, request, *args, **kwargs):
        """App-shaped list of routes (camelCase, nested stops), cached."""
        data = cache_get_or_set(
            cache_key(TRANSPORT_PREFIX, "routes", "all"),
            TTL_TRANSPORT,
            lambda: BusRouteAppSerializer(
                self.filter_queryset(self.get_queryset()), many=True
            ).data,
        )
        return Response(data)

    def retrieve(self, request, *args, **kwargs):
        """App-shaped single route (camelCase, nested stops), cached."""
        instance = self.get_object()
        data = cache_get_or_set(
            cache_key(TRANSPORT_PREFIX, "route", instance.pk),
            TTL_TRANSPORT,
            lambda: BusRouteAppSerializer(instance).data,
        )
        return Response(data)

    @extend_schema(responses={200: BusLiveStatusAppSerializer})
    @action(detail=True, methods=["get"])
    def live(self, request, pk=None):
        """``GET /transport/routes/{id}/live`` — live status for a route (cached)."""
        route = self.get_object()

        def build():
            status = (
                BusLiveStatus.objects.select_related("route")
                .filter(route_id=route.pk)
                .first()
            )
            if status is None:
                return None
            return BusLiveStatusAppSerializer(status).data

        data = cache_get_or_set(
            cache_key(TRANSPORT_PREFIX, "live", route.pk), TTL_TRANSPORT, build
        )
        if data is None:
            raise NotFound("No live status available for this route.")
        return Response(data)


class BusStopViewSet(BaseModelViewSet):
    """Admin management of individual stops on a route."""

    queryset = BusStop.objects.select_related("route").all()
    serializer_class = BusStopSerializer
    service_class = BusStopService
    permission_matrix = ADMIN_WRITE_MATRIX
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["route"]
    search_fields = ["name"]
    ordering_fields = ["order", "name", "created_at"]


class BusLiveStatusViewSet(BaseModelViewSet):
    """Admin management of the per-route live status rows."""

    queryset = BusLiveStatus.objects.select_related("route").all()
    serializer_class = BusLiveStatusSerializer
    service_class = BusLiveStatusService
    permission_matrix = ADMIN_WRITE_MATRIX
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ["route"]
    ordering_fields = ["eta_mins", "occupancy", "created_at"]
