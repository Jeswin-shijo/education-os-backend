"""Business-logic layer for the complaints app.

:class:`ComplaintService` extends :class:`core.services.BaseService` so writes
auto-stamp ``created_by``/``updated_by``, emit an :class:`~core.models.AuditLog`
row, and bust cached complaint listings (the Principal/Admin monitor view).
Reads that are cached live under the ``complaints`` prefix; any write
invalidates the whole prefix.
"""
from __future__ import annotations

from core.cache import invalidate_prefix
from core.services import BaseService

from complaints.models import Complaint
from complaints.repositories import ComplaintRepository

# Cache-key prefix owned by this app.
COMPLAINTS_PREFIX = "complaints"


class ComplaintService(BaseService):
    model = Complaint
    repository_class = ComplaintRepository
    entity_name = "Complaint"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(COMPLAINTS_PREFIX)

    def set_status(self, instance: Complaint, status: str) -> Complaint:
        """Staff status-workflow transition (``open``/``in_progress``/``resolved``).

        Routes through :meth:`BaseService.update` so the change is stamped,
        audited, and cache-invalidated like any other write.
        """
        return self.update(instance, status=status)
