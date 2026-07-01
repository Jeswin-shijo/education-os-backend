"""Business-logic layer.

A :class:`BaseService` wraps a repository and is the only place that mutates
data. It stamps ``created_by``/``updated_by`` from the acting user, writes an
:class:`~core.models.AuditLog` row for every mutation, and exposes an
``invalidate_cache`` hook that subclasses override to clear Redis entries.
"""
from __future__ import annotations

from typing import Any, Optional

from django.db import models

from core.models import AuditLog
from core.repositories import BaseRepository


class BaseService:
    """Service bound to a repository.

    Subclass and set ``repository_class`` (or ``model``) plus ``entity_name``.
    Pass the acting user as ``actor`` so audit + stamping work.
    """

    repository_class: type[BaseRepository] = BaseRepository
    model: type[models.Model] | None = None
    entity_name: str | None = None

    def __init__(self, actor=None, repository: BaseRepository | None = None, ip=None):
        self.actor = actor
        self.ip = ip
        if repository is not None:
            self.repository = repository
        elif self.model is not None:
            self.repository = self.repository_class(self.model)
        else:
            self.repository = self.repository_class()
        if self.model is None:
            self.model = self.repository.model
        if self.entity_name is None and self.model is not None:
            self.entity_name = self.model.__name__

    # -- audit ------------------------------------------------------------
    def _actor_or_none(self):
        actor = self.actor
        if actor is not None and getattr(actor, "is_authenticated", False):
            return actor
        return None

    def audit(self, action: str, entity_id: Any = None, changes: dict | None = None) -> AuditLog:
        return AuditLog.objects.create(
            actor=self._actor_or_none(),
            action=action,
            entity=self.entity_name or "",
            entity_id=str(entity_id) if entity_id is not None else None,
            changes=changes or {},
            ip=self.ip,
        )

    # -- cache hook -------------------------------------------------------
    def invalidate_cache(self, instance: models.Model | None = None) -> None:
        """Override in subclasses to invalidate the entity's cached views."""
        return None

    # -- reads ------------------------------------------------------------
    def get(self, id: Any):
        return self.repository.get(id)

    def get_or_none(self, id: Any):
        return self.repository.get_or_none(id)

    def list(self, **filters):
        return self.repository.list(**filters)

    # -- writes -----------------------------------------------------------
    def create(self, **data) -> models.Model:
        actor = self._actor_or_none()
        if actor is not None:
            data.setdefault("created_by", actor)
            data.setdefault("updated_by", actor)
        instance = self.repository.create(**data)
        self.audit(AuditLog.ACTION_CREATE, entity_id=instance.pk, changes=self._serialize(data))
        self.invalidate_cache(instance)
        return instance

    def update(self, instance: models.Model, **data) -> models.Model:
        actor = self._actor_or_none()
        if actor is not None and hasattr(instance, "updated_by"):
            data.setdefault("updated_by", actor)
        instance = self.repository.update(instance, **data)
        self.audit(AuditLog.ACTION_UPDATE, entity_id=instance.pk, changes=self._serialize(data))
        self.invalidate_cache(instance)
        return instance

    def delete(self, instance: models.Model) -> models.Model:
        entity_id = instance.pk
        self.repository.soft_delete(instance)
        self.audit(AuditLog.ACTION_DELETE, entity_id=entity_id)
        self.invalidate_cache(instance)
        return instance

    def restore(self, instance: models.Model) -> models.Model:
        self.repository.restore(instance)
        self.audit(AuditLog.ACTION_RESTORE, entity_id=instance.pk)
        self.invalidate_cache(instance)
        return instance

    # -- helpers ----------------------------------------------------------
    @staticmethod
    def _serialize(data: dict) -> dict:
        """Make a change dict JSON-safe for the audit log."""
        safe = {}
        for key, value in data.items():
            if isinstance(value, models.Model):
                safe[key] = str(value.pk)
            elif isinstance(value, (str, int, float, bool)) or value is None:
                safe[key] = value
            else:
                safe[key] = str(value)
        return safe
