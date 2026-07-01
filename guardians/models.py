"""Guardians domain models.

A :class:`ParentLink` connects a parent login (``accounts.User`` with role
``parent``) to a :class:`students.Student` they are the guardian of, recording
the ``relation`` (father/mother/guardian/...). This is the authoritative
parent↔child mapping used by the parent role's endpoints (``GET /parent/children``
and, later, the parent dashboard); the ``students.Guardian`` table only stores
the display contact info on the student record.

Every model extends :class:`core.models.BaseModel` (UUID PK, audit fields,
soft-delete).
"""
from django.conf import settings
from django.db import models

from core.models import BaseModel


class ParentLink(BaseModel):
    """Links a parent :class:`~accounts.User` to a :class:`students.Student`.

    A parent may be linked to several children and a student may have several
    guardians; the ``(parent, student)`` pair is unique among live rows.
    """

    RELATION_FATHER = "father"
    RELATION_MOTHER = "mother"
    RELATION_GUARDIAN = "guardian"
    RELATION_OTHER = "other"
    RELATION_CHOICES = [
        (RELATION_FATHER, "Father"),
        (RELATION_MOTHER, "Mother"),
        (RELATION_GUARDIAN, "Guardian"),
        (RELATION_OTHER, "Other"),
    ]

    parent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="parent_links",
    )
    student = models.ForeignKey(
        "students.Student",
        on_delete=models.CASCADE,
        related_name="parent_links",
    )
    relation = models.CharField(
        max_length=32,
        choices=RELATION_CHOICES,
        default=RELATION_GUARDIAN,
    )
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_primary", "student__roll_no"]
        verbose_name = "Parent Link"
        verbose_name_plural = "Parent Links"
        constraints = [
            models.UniqueConstraint(
                fields=["parent", "student"],
                condition=models.Q(is_deleted=False),
                name="uniq_parentlink_parent_student",
            )
        ]
        indexes = [
            models.Index(fields=["parent"]),
            models.Index(fields=["student"]),
        ]

    def __str__(self):
        return f"{self.parent_id} → {self.student_id} ({self.relation})"
