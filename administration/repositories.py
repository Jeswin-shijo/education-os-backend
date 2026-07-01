"""Data-access for the admin console.

``AuditLogRepository`` reads ``core.AuditLog`` (a plain, non-soft-delete model,
so it does not use :class:`core.repositories.BaseRepository`). User queries reuse
``accounts.repositories.UserRepository``.
"""
from __future__ import annotations

from core.models import AuditLog


class AuditLogRepository:
    """Read-only browsing of the immutable audit trail."""

    model = AuditLog

    def all(self):
        return AuditLog.objects.select_related("actor").all()

    def filter(self, *, entity=None, action=None, actor=None, entity_id=None):
        qs = self.all()
        if entity:
            qs = qs.filter(entity__iexact=entity)
        if action:
            qs = qs.filter(action=action)
        if actor:
            qs = qs.filter(actor_id=actor)
        if entity_id:
            qs = qs.filter(entity_id=str(entity_id))
        return qs
