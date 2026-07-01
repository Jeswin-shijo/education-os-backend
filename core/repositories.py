"""Data-access layer. Repositories wrap a model and expose CRUD over the
soft-delete-aware default manager. Services depend on repositories, never on
the ORM directly."""
from __future__ import annotations

from typing import Any, Iterable, Optional

from django.db import models


class BaseRepository:
    """Generic repository bound to a single model.

    Subclass and set ``model``, or instantiate as ``BaseRepository(MyModel)``.
    All reads go through the model's default (soft-delete-aware) manager unless
    ``include_deleted=True`` is passed.
    """

    model: type[models.Model] | None = None

    def __init__(self, model: type[models.Model] | None = None):
        if model is not None:
            self.model = model
        if self.model is None:
            raise ValueError("BaseRepository requires a model.")

    # -- managers ---------------------------------------------------------
    def get_queryset(self, include_deleted: bool = False) -> models.QuerySet:
        if include_deleted and hasattr(self.model, "all_objects"):
            return self.model.all_objects.all()
        return self.model.objects.all()

    # -- reads ------------------------------------------------------------
    def get(self, id: Any, include_deleted: bool = False) -> models.Model:
        return self.get_queryset(include_deleted).get(pk=id)

    def get_or_none(
        self, id: Any, include_deleted: bool = False
    ) -> Optional[models.Model]:
        try:
            return self.get(id, include_deleted=include_deleted)
        except self.model.DoesNotExist:
            return None

    def get_by(self, **filters) -> Optional[models.Model]:
        return self.get_queryset().filter(**filters).first()

    def list(self, **filters) -> models.QuerySet:
        qs = self.get_queryset()
        return qs.filter(**filters) if filters else qs

    def filter(self, *args, **kwargs) -> models.QuerySet:
        return self.get_queryset().filter(*args, **kwargs)

    def all(self, include_deleted: bool = False) -> models.QuerySet:
        return self.get_queryset(include_deleted)

    def exists(self, **filters) -> bool:
        return self.get_queryset().filter(**filters).exists()

    def count(self, **filters) -> int:
        qs = self.get_queryset()
        return (qs.filter(**filters) if filters else qs).count()

    # -- writes -----------------------------------------------------------
    def create(self, **data) -> models.Model:
        return self.model.objects.create(**data)

    def bulk_create(self, objs: Iterable[models.Model]) -> list[models.Model]:
        return self.model.objects.bulk_create(list(objs))

    def update(self, instance: models.Model, **data) -> models.Model:
        update_fields = []
        for field, value in data.items():
            setattr(instance, field, value)
            update_fields.append(field)
        if update_fields:
            if hasattr(instance, "updated_at"):
                update_fields.append("updated_at")
            instance.save(update_fields=update_fields)
        return instance

    def soft_delete(self, instance: models.Model) -> models.Model:
        instance.delete()  # BaseModel.delete() is a soft delete
        return instance

    def hard_delete(self, instance: models.Model) -> None:
        if hasattr(instance, "hard_delete"):
            instance.hard_delete()
        else:
            models.Model.delete(instance)

    def restore(self, instance: models.Model) -> models.Model:
        if hasattr(instance, "restore"):
            instance.restore()
        return instance
