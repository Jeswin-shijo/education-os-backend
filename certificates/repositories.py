"""Data-access layer for the certificates app.

Wraps :class:`~certificates.models.Certificate` over the soft-delete-aware
default manager and adds ``select_related("student")`` so serializers touching
the owning student never trigger N+1 queries.
"""
from __future__ import annotations

from core.repositories import BaseRepository

from certificates.models import Certificate


class CertificateRepository(BaseRepository):
    model = Certificate

    def get_queryset(self, include_deleted: bool = False):
        return super().get_queryset(include_deleted).select_related("student")

    def for_student(self, student, include_deleted: bool = False):
        """Certificates belonging to ``student`` (most recent issue first)."""
        return self.get_queryset(include_deleted).filter(student=student)
