"""Business-logic layer for the placement app.

Services extend :class:`core.services.BaseService` so every write auto-stamps
``created_by``/``updated_by``, emits an :class:`~core.models.AuditLog` row and
invalidates the cached placement views (``placement`` prefix).

:class:`PlacementApplicationService.apply` is idempotent per (opening, student):
a student who already applied gets their existing application back rather than a
duplicate.
"""
from __future__ import annotations

from core.cache import invalidate_prefix
from core.services import BaseService

from placement.models import PlacementApplication, PlacementOpening
from placement.repositories import (
    PlacementApplicationRepository,
    PlacementOpeningRepository,
)

# Cache key prefix owned by this app.
PLACEMENT_PREFIX = "placement"


class PlacementOpeningService(BaseService):
    model = PlacementOpening
    repository_class = PlacementOpeningRepository
    entity_name = "PlacementOpening"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(PLACEMENT_PREFIX)


class PlacementApplicationService(BaseService):
    model = PlacementApplication
    repository_class = PlacementApplicationRepository
    entity_name = "PlacementApplication"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(PLACEMENT_PREFIX)

    def apply(self, opening: PlacementOpening, student) -> PlacementApplication:
        """Apply ``student`` to ``opening`` (idempotent).

        Returns the existing application if one is already on file; otherwise
        creates a fresh one (audited + cache-invalidated via ``create``).
        """
        existing = self.repository.get_queryset().filter(
            opening=opening, student=student
        ).first()
        if existing is not None:
            return existing
        return self.create(
            opening=opening,
            student=student,
            status=PlacementApplication.STATUS_APPLIED,
        )
