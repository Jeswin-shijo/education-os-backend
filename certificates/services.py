"""Business-logic layer for the certificates app.

:class:`CertificateService` extends :class:`core.services.BaseService` so every
write auto-stamps ``created_by``/``updated_by``, emits an
:class:`~core.models.AuditLog` row and invalidates the cached certificate views
(``certificates`` prefix).
"""
from __future__ import annotations

from core.cache import invalidate_prefix
from core.services import BaseService

from certificates.models import Certificate
from certificates.repositories import CertificateRepository

# Cache key prefix owned by this app.
CERTIFICATES_PREFIX = "certificates"


class CertificateService(BaseService):
    model = Certificate
    repository_class = CertificateRepository
    entity_name = "Certificate"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(CERTIFICATES_PREFIX)
