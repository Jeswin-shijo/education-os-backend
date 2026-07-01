"""Business-logic layer for the materials app.

:class:`MaterialService` extends :class:`core.services.BaseService` so writes
auto-stamp ``created_by``/``updated_by``, emit an :class:`~core.models.AuditLog`
row, and bust cached material listings. Reads are cached under the ``materials``
prefix; any write invalidates the whole prefix.
"""
from __future__ import annotations

from core.cache import invalidate_prefix
from core.services import BaseService

from materials.models import Material
from materials.repositories import MaterialRepository

# Cache-key prefix owned by this app.
MATERIALS_PREFIX = "materials"


class MaterialService(BaseService):
    model = Material
    repository_class = MaterialRepository
    entity_name = "Material"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(MATERIALS_PREFIX)
