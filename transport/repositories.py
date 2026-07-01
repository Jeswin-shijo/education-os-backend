"""Data-access layer for the transport app.

Repositories wrap each model over the soft-delete-aware default manager and
prefetch ``stops`` / ``select_related`` ``route`` where serializers touch them,
avoiding N+1 queries.
"""
from __future__ import annotations

from django.db.models import Prefetch

from core.repositories import BaseRepository

from transport.models import BusLiveStatus, BusRoute, BusStop


class BusRouteRepository(BaseRepository):
    model = BusRoute

    def get_queryset(self, include_deleted: bool = False):
        return (
            super()
            .get_queryset(include_deleted)
            .prefetch_related(
                Prefetch("stops", queryset=BusStop.objects.order_by("order"))
            )
        )


class BusStopRepository(BaseRepository):
    model = BusStop

    def get_queryset(self, include_deleted: bool = False):
        return super().get_queryset(include_deleted).select_related("route")


class BusLiveStatusRepository(BaseRepository):
    model = BusLiveStatus

    def get_queryset(self, include_deleted: bool = False):
        return super().get_queryset(include_deleted).select_related("route")
