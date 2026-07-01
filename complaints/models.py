"""Complaints domain model.

A :class:`Complaint` is a grievance a campus member (typically a student or a
parent-on-behalf-of-child) raises against the institution: a category, a subject
line, a free-text description, and a status that moves through a small workflow
(``open`` -> ``in_progress`` -> ``resolved``).

It backs the mobile ``complaintService`` (``types.ts`` ``Complaint`` shape:
``category``/``subject``/``description``/``status``/``createdOn``) plus the
Principal/Admin ``complaintMonitoring`` surface (all complaints + status counts).

Every complaint is owned by the ``user`` who filed it (drives the "own"
scoping of ``GET /complaints``). Every model extends
:class:`core.models.BaseModel` (UUID PK, audit, soft-delete).
"""
from django.conf import settings
from django.db import models

from core.models import BaseModel


class Complaint(BaseModel):
    """A grievance raised by a campus member, with a small status workflow."""

    STATUS_OPEN = "open"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_RESOLVED = "resolved"
    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_IN_PROGRESS, "In Progress"),
        (STATUS_RESOLVED, "Resolved"),
    ]

    # The member who filed the complaint (owner; drives own-complaint scoping).
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="complaints",
    )
    # Free-text category the app renders (e.g. "Hostel", "Academics", "Fees").
    category = models.CharField(max_length=64, db_index=True)
    subject = models.CharField(max_length=255)
    description = models.TextField()
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_OPEN,
        db_index=True,
    )
    # When the complaint was filed; mirrors the app's `createdOn`.
    created_on = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_on"]
        verbose_name = "Complaint"
        verbose_name_plural = "Complaints"
        indexes = [
            models.Index(fields=["user", "created_on"]),
            models.Index(fields=["status", "created_on"]),
        ]

    def __str__(self):
        return f"{self.subject} ({self.status})"
