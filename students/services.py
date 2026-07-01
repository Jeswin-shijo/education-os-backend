"""Business-logic layer for the students app.

Services extend :class:`core.services.BaseService` so every write auto-stamps
``created_by``/``updated_by``, emits an :class:`~core.models.AuditLog` row and
invalidates the cached roster/profile views. The student roster and per-student
profile are cached under the ``students`` prefix.
"""
from __future__ import annotations

from core.cache import invalidate_prefix
from core.services import BaseService

from students.models import (
    Guardian,
    Medical,
    Student,
    StudentAddress,
    StudentDocument,
)
from students.repositories import (
    GuardianRepository,
    MedicalRepository,
    StudentAddressRepository,
    StudentDocumentRepository,
    StudentRepository,
)

# Cache key prefix owned by this app.
STUDENTS_PREFIX = "students"


class StudentService(BaseService):
    model = Student
    repository_class = StudentRepository
    entity_name = "Student"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(STUDENTS_PREFIX)


class StudentAddressService(BaseService):
    model = StudentAddress
    repository_class = StudentAddressRepository
    entity_name = "StudentAddress"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(STUDENTS_PREFIX)


class GuardianService(BaseService):
    model = Guardian
    repository_class = GuardianRepository
    entity_name = "Guardian"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(STUDENTS_PREFIX)


class MedicalService(BaseService):
    model = Medical
    repository_class = MedicalRepository
    entity_name = "Medical"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(STUDENTS_PREFIX)


class StudentDocumentService(BaseService):
    model = StudentDocument
    repository_class = StudentDocumentRepository
    entity_name = "StudentDocument"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(STUDENTS_PREFIX)
