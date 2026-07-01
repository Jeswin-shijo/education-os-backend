"""Business-logic layer for the guardians app.

:class:`ParentLinkService` extends :class:`core.services.BaseService` so writes
auto-stamp ``created_by``/``updated_by``, emit an :class:`~core.models.AuditLog`
row, and bust cached parent reads. Parent ``children`` reads are cached under the
``guardians`` prefix; any write invalidates that prefix.
"""
from __future__ import annotations

from core.cache import invalidate_prefix
from core.services import BaseService

from guardians.models import ParentLink
from guardians.repositories import ParentLinkRepository

# Cache-key prefix owned by this app.
GUARDIANS_PREFIX = "guardians"


class ParentLinkService(BaseService):
    model = ParentLink
    repository_class = ParentLinkRepository
    entity_name = "ParentLink"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(GUARDIANS_PREFIX)
