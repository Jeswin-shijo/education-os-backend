"""Materials domain model.

A :class:`Material` is a piece of course content a faculty member shares with a
class — a note, a video, a slide deck, or an external link. It backs two mobile
surfaces:

* the student-facing ``materialService.list(subjectId?)`` — the app's
  ``types.ts`` ``Material`` shape (``subjectId``/``kind``/``sizeLabel``/
  ``addedAt``), keyed by subject; and
* the faculty ``facultyMaterialService`` (``FacultyMaterial``) — keyed by class
  (``classId``/``addedOn``), an upload-metadata record.

To serve both without duplicating rows, a Material carries an optional
``subject`` FK (student view / ``?subjectId=`` filter) and an optional
``faculty_class`` FK (faculty view / ``?classId=`` filter). The actual bytes live
in ``file`` (S3/FileSystem storage) for uploads, or ``url`` for ``link``/video
references; ``size_label`` is the human label the app renders (e.g. "2.4 MB").
Every model extends :class:`core.models.BaseModel` (UUID PK, audit, soft-delete).
"""
from django.db import models

from core.models import BaseModel


class Material(BaseModel):
    """A shared course material (note / video / slide / link)."""

    KIND_NOTE = "note"
    KIND_VIDEO = "video"
    KIND_SLIDE = "slide"
    KIND_LINK = "link"
    KIND_CHOICES = [
        (KIND_NOTE, "Note"),
        (KIND_VIDEO, "Video"),
        (KIND_SLIDE, "Slide"),
        (KIND_LINK, "Link"),
    ]

    # Optional subject (drives the student `?subjectId=` view). Nullable so a
    # material can be attached to a class without a subject and vice versa.
    subject = models.ForeignKey(
        "academics.Subject",
        on_delete=models.CASCADE,
        related_name="materials",
        null=True,
        blank=True,
    )
    # Optional faculty class (drives the faculty `?classId=` view + ownership).
    faculty_class = models.ForeignKey(
        "faculty.FacultyClass",
        on_delete=models.CASCADE,
        related_name="materials",
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=255)
    kind = models.CharField(
        max_length=16, choices=KIND_CHOICES, default=KIND_NOTE, db_index=True
    )
    # Human-readable size the app renders (e.g. "2.4 MB", "12 min"). Optional.
    size_label = models.CharField(max_length=64, blank=True, default="")
    # Uploaded bytes (S3 when USE_S3, else FileSystem). Optional for link/video.
    file = models.FileField(upload_to="materials/", null=True, blank=True)
    # External reference (used for `link` / hosted `video`). Optional.
    url = models.URLField(max_length=1024, blank=True, default="")
    # When the material was shared; mirrors the app's `addedAt` / `addedOn`.
    added_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-added_at"]
        verbose_name = "Material"
        verbose_name_plural = "Materials"
        indexes = [
            models.Index(fields=["subject", "added_at"]),
            models.Index(fields=["faculty_class", "added_at"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.kind})"
