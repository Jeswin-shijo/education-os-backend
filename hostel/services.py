"""Business-logic layer for the hostel app.

Services extend :class:`core.services.BaseService` so every write auto-stamps
``created_by``/``updated_by``, emits an :class:`~core.models.AuditLog` row and
invalidates the cached hostel views. All hostel reads are cached under the
``hostel`` prefix and cleared on any mutation.
"""
from __future__ import annotations

from core.cache import invalidate_prefix
from core.services import BaseService

from hostel.models import HostelAllocation, HostelBlock, HostelRoom
from hostel.repositories import (
    HostelAllocationRepository,
    HostelBlockRepository,
    HostelRoomRepository,
)

# Cache key prefix owned by this app.
HOSTEL_PREFIX = "hostel"


class HostelBlockService(BaseService):
    model = HostelBlock
    repository_class = HostelBlockRepository
    entity_name = "HostelBlock"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(HOSTEL_PREFIX)


class HostelRoomService(BaseService):
    model = HostelRoom
    repository_class = HostelRoomRepository
    entity_name = "HostelRoom"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(HOSTEL_PREFIX)


class HostelAllocationService(BaseService):
    model = HostelAllocation
    repository_class = HostelAllocationRepository
    entity_name = "HostelAllocation"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(HOSTEL_PREFIX)
