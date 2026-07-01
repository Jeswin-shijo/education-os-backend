"""Business-logic layer for the transport app.

Each service extends :class:`core.services.BaseService` so writes auto-stamp
``created_by``/``updated_by``, emit an :class:`~core.models.AuditLog` row, and
invalidate the cached route reads. Route/stop/live-status writes all bust the
``transport`` cache prefix.
"""
from __future__ import annotations

from core.cache import invalidate_prefix
from core.services import BaseService

from transport.models import BusLiveStatus, BusRoute, BusStop
from transport.repositories import (
    BusLiveStatusRepository,
    BusRouteRepository,
    BusStopRepository,
)

# Cache key prefix owned by this app.
TRANSPORT_PREFIX = "transport"


class BusRouteService(BaseService):
    model = BusRoute
    repository_class = BusRouteRepository
    entity_name = "BusRoute"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(TRANSPORT_PREFIX)


class BusStopService(BaseService):
    model = BusStop
    repository_class = BusStopRepository
    entity_name = "BusStop"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(TRANSPORT_PREFIX)


class BusLiveStatusService(BaseService):
    model = BusLiveStatus
    repository_class = BusLiveStatusRepository
    entity_name = "BusLiveStatus"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(TRANSPORT_PREFIX)
