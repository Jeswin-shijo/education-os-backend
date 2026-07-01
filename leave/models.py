"""Leave domain model.

A :class:`LeaveRequest` is a leave application filed by any user (student,
faculty, HOD, ...). It carries the ``type`` (casual/medical/event), the
``start_date``/``end_date`` window, a free-text ``reason``, and a ``status``
that moves through the approval workflow (``pending`` → ``approved``/
``rejected``). ``applied_on`` stamps when it was filed; ``decided_by`` records
the approver once a decision is made.

The mobile ``LeaveRequest`` shape (``types.ts``) is camelCase and uses
``from``/``to``/``appliedOn`` — those are mapped in the serializer. Every model
extends :class:`core.models.BaseModel` (UUID PK, audit fields, soft-delete).
"""
from django.conf import settings
from django.db import models

from core.models import BaseModel


class LeaveRequest(BaseModel):
    """A leave application filed by a user, moving through an approval workflow."""

    TYPE_CASUAL = "casual"
    TYPE_MEDICAL = "medical"
    TYPE_EVENT = "event"
    TYPE_CHOICES = [
        (TYPE_CASUAL, "Casual"),
        (TYPE_MEDICAL, "Medical"),
        (TYPE_EVENT, "Event"),
    ]

    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="leave_requests",
    )
    type = models.CharField(
        max_length=16,
        choices=TYPE_CHOICES,
        default=TYPE_CASUAL,
        db_index=True,
    )
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )
    applied_on = models.DateTimeField(auto_now_add=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="leave_decisions",
    )

    class Meta:
        ordering = ["-applied_on"]
        verbose_name = "Leave Request"
        verbose_name_plural = "Leave Requests"
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["status"]),
            models.Index(fields=["applied_on"]),
        ]

    def __str__(self):
        return f"{self.user_id} — {self.type} [{self.status}]"
