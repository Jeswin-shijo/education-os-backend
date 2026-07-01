"""Events domain models.

:class:`Event` mirrors the mobile app's ``EventItem`` type
(``title``/``date``/``time``/``venue``/``category``) plus a ``description`` for
detail views. :class:`EventRegistration` records a single user's registration for
an event; the app's ``registered`` flag is derived per-requesting-user from these
rows (see :mod:`events.serializers`).

Every model extends :class:`core.models.BaseModel` (UUID PK, audit fields,
soft-delete).
"""
from django.conf import settings
from django.db import models

from core.models import BaseModel


class Event(BaseModel):
    """A campus event that users may register for.

    ``category`` is constrained to the four values the mobile app's ``EventItem``
    type uses (``tech``/``cultural``/``sports``/``workshop``).
    """

    CATEGORY_TECH = "tech"
    CATEGORY_CULTURAL = "cultural"
    CATEGORY_SPORTS = "sports"
    CATEGORY_WORKSHOP = "workshop"
    CATEGORY_CHOICES = [
        (CATEGORY_TECH, "Tech"),
        (CATEGORY_CULTURAL, "Cultural"),
        (CATEGORY_SPORTS, "Sports"),
        (CATEGORY_WORKSHOP, "Workshop"),
    ]

    title = models.CharField(max_length=255, db_index=True)
    date = models.DateField(db_index=True)
    time = models.CharField(max_length=32, blank=True, default="")
    venue = models.CharField(max_length=255, blank=True, default="")
    category = models.CharField(
        max_length=16,
        choices=CATEGORY_CHOICES,
        default=CATEGORY_TECH,
        db_index=True,
    )
    description = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["date", "title"]
        verbose_name = "Event"
        verbose_name_plural = "Events"
        indexes = [
            models.Index(fields=["category", "date"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.date})"


class EventRegistration(BaseModel):
    """A single user's registration for an :class:`Event`.

    Unique per (event, user) among live rows; toggling re-registration reuses the
    soft-deleted row rather than creating duplicates (handled in the service).
    """

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="registrations",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="event_registrations",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Event registration"
        verbose_name_plural = "Event registrations"
        constraints = [
            models.UniqueConstraint(
                fields=["event", "user"],
                condition=models.Q(is_deleted=False),
                name="uniq_live_event_registration",
            )
        ]
        indexes = [
            models.Index(fields=["event", "user"]),
            models.Index(fields=["user", "is_deleted"]),
        ]

    def __str__(self):
        return f"{self.user_id} → {self.event_id}"
