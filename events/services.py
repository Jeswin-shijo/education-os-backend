"""Business-logic layer for the events app.

Services extend :class:`core.services.BaseService` so every write auto-stamps
``created_by``/``updated_by``, emits an :class:`~core.models.AuditLog` row and
invalidates the cached events views (``events`` prefix).

:class:`EventRegistrationService.toggle` is the heart of the ``POST
/events/{id}/register`` endpoint: it registers a user if they are not already
registered, or unregisters (soft-delete) them if they are, reusing a previously
soft-deleted row instead of creating duplicates.
"""
from __future__ import annotations

from core.cache import invalidate_prefix
from core.services import BaseService

from events.models import Event, EventRegistration
from events.repositories import EventRegistrationRepository, EventRepository

# Cache key prefix owned by this app.
EVENTS_PREFIX = "events"


class EventService(BaseService):
    model = Event
    repository_class = EventRepository
    entity_name = "Event"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(EVENTS_PREFIX)


class EventRegistrationService(BaseService):
    model = EventRegistration
    repository_class = EventRegistrationRepository
    entity_name = "EventRegistration"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(EVENTS_PREFIX)

    def toggle(self, event: Event, user) -> bool:
        """Toggle ``user``'s registration for ``event``.

        Returns the new registration state (``True`` = registered,
        ``False`` = unregistered). Audited + cache-invalidated via the base
        service's create/delete/restore.
        """
        live = self.repository.live_for(event, user)
        if live is not None:
            self.delete(live)
            return False

        # Reuse a previously soft-deleted row so the unique constraint holds and
        # history stays clean; otherwise create a fresh registration.
        stale = self.repository.any_for(event, user)
        if stale is not None:
            self.restore(stale)
        else:
            self.create(event=event, user=user)
        return True
