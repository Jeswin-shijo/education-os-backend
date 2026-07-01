"""Data-access layer for the events app.

Repositories wrap each model over the soft-delete-aware default manager and add
``select_related`` where serializers touch related objects.
"""
from __future__ import annotations

from core.repositories import BaseRepository

from events.models import Event, EventRegistration


class EventRepository(BaseRepository):
    model = Event


class EventRegistrationRepository(BaseRepository):
    model = EventRegistration

    def get_queryset(self, include_deleted: bool = False):
        return super().get_queryset(include_deleted).select_related("event", "user")

    def live_for(self, event, user):
        """The user's live (non-deleted) registration for ``event``, or None."""
        return self.get_queryset().filter(event=event, user=user).first()

    def any_for(self, event, user):
        """The user's registration for ``event`` including soft-deleted, or None."""
        return (
            EventRegistration.all_objects.filter(event=event, user=user)
            .order_by("-created_at")
            .first()
        )
