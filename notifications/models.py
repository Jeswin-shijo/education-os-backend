"""Notifications domain model.

Mirrors the mobile app's ``NotificationItem`` shape (``types.ts``):
``{ id, title, body, category, createdAt, read }``. Server-side each row also
has a ``recipient`` FK (nullable) so a broadcast (recipient ``NULL``) can be a
single row that fans out to a role/all, while a per-user notification targets
one recipient. ``broadcast_role`` records the audience of a broadcast row.

Extends :class:`core.models.BaseModel` (UUID PK, audit fields, soft-delete).
The BaseModel ``created_at`` field already provides the app's ``createdAt``.
"""
from django.conf import settings
from django.db import models

from core.models import BaseModel
from core.permissions import Role


class Notification(BaseModel):
    """A notification targeted at one recipient, or a broadcast (recipient null)."""

    CATEGORY_ACADEMIC = "academic"
    CATEGORY_FEE = "fee"
    CATEGORY_EVENT = "event"
    CATEGORY_GENERAL = "general"
    CATEGORY_ALERT = "alert"
    CATEGORY_CHOICES = [
        (CATEGORY_ACADEMIC, "Academic"),
        (CATEGORY_FEE, "Fee"),
        (CATEGORY_EVENT, "Event"),
        (CATEGORY_GENERAL, "General"),
        (CATEGORY_ALERT, "Alert"),
    ]

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        null=True,
        blank=True,
        help_text="Target user; NULL denotes a broadcast (audience in broadcast_role).",
    )
    # For broadcast rows: the role targeted, or NULL/blank for "all roles".
    broadcast_role = models.CharField(
        max_length=32,
        choices=Role.CHOICES,
        blank=True,
        default="",
        help_text="Audience role for a broadcast row; blank means all roles.",
    )
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True, default="")
    category = models.CharField(
        max_length=16,
        choices=CATEGORY_CHOICES,
        default=CATEGORY_GENERAL,
        db_index=True,
    )
    read = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        indexes = [
            models.Index(fields=["recipient", "read"]),
            models.Index(fields=["recipient", "-created_at"]),
        ]

    def __str__(self):
        target = self.recipient_id or f"broadcast:{self.broadcast_role or 'all'}"
        return f"{self.category}: {self.title} -> {target}"
