"""Placement domain models.

:class:`PlacementOpening` is a campus recruitment posting (mirrors the mobile
app's ``PlacementOpening`` type: ``company``/``role``/``ctc``/``location``/
``eligibility``/``lastDate``/``logoColor``/``applied``). The ``applied`` flag in
the app is per-student and is derived at serialization time from the requesting
student's :class:`PlacementApplication`, not stored on the opening.

:class:`PlacementApplication` records a :class:`students.Student` applying to an
opening and its recruitment ``status``.

Every model extends :class:`core.models.BaseModel` (UUID PK, audit fields,
soft-delete).
"""
from django.db import models
from django.utils import timezone

from core.models import BaseModel


class PlacementOpening(BaseModel):
    """A campus recruitment posting students can apply to."""

    company = models.CharField(max_length=255, db_index=True)
    role = models.CharField(max_length=255)
    # Money -> Decimal (annual CTC). Stored with two decimal places.
    ctc = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    location = models.CharField(max_length=255, blank=True, default="")
    eligibility = models.CharField(max_length=512, blank=True, default="")
    last_date = models.DateField()
    logo_color = models.CharField(max_length=16, blank=True, default="#13327F")
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["-last_date", "company"]
        verbose_name = "Placement opening"
        verbose_name_plural = "Placement openings"
        indexes = [
            models.Index(fields=["is_active", "last_date"]),
        ]

    def __str__(self):
        return f"{self.company} — {self.role}"


class PlacementApplication(BaseModel):
    """A :class:`students.Student`'s application to a :class:`PlacementOpening`."""

    STATUS_APPLIED = "applied"
    STATUS_SHORTLISTED = "shortlisted"
    STATUS_SELECTED = "selected"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [
        (STATUS_APPLIED, "Applied"),
        (STATUS_SHORTLISTED, "Shortlisted"),
        (STATUS_SELECTED, "Selected"),
        (STATUS_REJECTED, "Rejected"),
    ]

    opening = models.ForeignKey(
        PlacementOpening,
        on_delete=models.CASCADE,
        related_name="applications",
    )
    student = models.ForeignKey(
        "students.Student",
        on_delete=models.CASCADE,
        related_name="placement_applications",
    )
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_APPLIED,
        db_index=True,
    )
    applied_on = models.DateField(default=timezone.localdate)

    class Meta:
        ordering = ["-applied_on"]
        verbose_name = "Placement application"
        verbose_name_plural = "Placement applications"
        constraints = [
            # A student applies to a given opening at most once (among the
            # non-deleted rows the default manager exposes).
            models.UniqueConstraint(
                fields=["opening", "student"],
                condition=models.Q(is_deleted=False),
                name="uniq_active_application_per_student_opening",
            ),
        ]
        indexes = [
            models.Index(fields=["student", "status"]),
            models.Index(fields=["opening", "status"]),
        ]

    def __str__(self):
        return f"{self.student_id} → {self.opening_id} ({self.status})"
