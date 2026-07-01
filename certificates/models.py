"""Certificates domain model.

:class:`Certificate` is a credential issued to a :class:`students.Student` and
maps to the mobile app's ``Certificate`` type
(``types.ts``: ``{id, title, issuer, issuedOn, kind}``) plus the file/url the
build spec adds so the app can download/view the artifact.

Every model extends :class:`core.models.BaseModel` (UUID PK, audit fields,
soft-delete).
"""
from django.db import models
from django.utils import timezone

from core.models import BaseModel


class Certificate(BaseModel):
    """A credential (course/event/achievement) issued to a student.

    ``kind`` mirrors the app's union ``'course' | 'event' | 'achievement'``.
    Either an uploaded ``file`` or an external ``url`` may point at the artifact
    (both optional; issuance metadata is the source of truth).
    """

    KIND_COURSE = "course"
    KIND_EVENT = "event"
    KIND_ACHIEVEMENT = "achievement"
    KIND_CHOICES = [
        (KIND_COURSE, "Course"),
        (KIND_EVENT, "Event"),
        (KIND_ACHIEVEMENT, "Achievement"),
    ]

    student = models.ForeignKey(
        "students.Student",
        on_delete=models.CASCADE,
        related_name="certificates",
    )
    title = models.CharField(max_length=255, db_index=True)
    issuer = models.CharField(max_length=255, blank=True, default="")
    issued_on = models.DateField(default=timezone.localdate, db_index=True)
    kind = models.CharField(
        max_length=16,
        choices=KIND_CHOICES,
        default=KIND_COURSE,
        db_index=True,
    )
    file = models.FileField(upload_to="certificates/", null=True, blank=True)
    url = models.URLField(max_length=1024, blank=True, default="")

    class Meta:
        ordering = ["-issued_on", "-created_at"]
        verbose_name = "Certificate"
        verbose_name_plural = "Certificates"
        indexes = [
            models.Index(fields=["student", "kind"]),
            models.Index(fields=["student", "issued_on"]),
        ]

    def __str__(self):
        return f"{self.title} → {self.student_id} ({self.kind})"
