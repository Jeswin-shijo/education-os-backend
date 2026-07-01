"""HTTP layer for the events app.

``EventViewSet`` serves:

* ``GET  /events``               — app-shaped event list with a per-user
  ``registered`` flag (the mobile ``eventService.list()`` contract).
* ``POST /events/{id}/register`` — toggle the requesting user's registration and
  return the updated app-shaped event (``eventService.toggleRegister(id)``).
* admin CRUD under ``/events-admin/…`` (create/update/delete events).

Writes flow through :class:`EventService` / :class:`EventRegistrationService`
(audit + cache-invalidate). The list read is cached under the ``events`` prefix,
scoped per user so each user's ``registered`` flags are correct.
"""
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from core.cache import TTL_DASHBOARD, cache_get_or_set, cache_key
from core.viewsets import BaseModelViewSet

from events.models import Event, EventRegistration
from events.permissions import EVENT_MATRIX
from events.serializers import EventAppSerializer, EventSerializer
from events.services import EventRegistrationService, EventService


class EventViewSet(BaseModelViewSet):
    queryset = Event.objects.all()
    serializer_class = EventSerializer
    service_class = EventService
    permission_matrix = EVENT_MATRIX
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["category", "date"]
    search_fields = ["title", "venue", "description"]
    ordering_fields = ["date", "title", "created_at"]

    # -- helpers ----------------------------------------------------------
    def _registered_ids(self, user) -> set:
        """Set of event ids the user currently has a live registration for."""
        return set(
            EventRegistration.objects.filter(user=user).values_list(
                "event_id", flat=True
            )
        )

    # -- GET /events (app-shaped list) ------------------------------------
    @extend_schema(responses={200: EventAppSerializer(many=True)})
    def events(self, request):
        registered_ids = self._registered_ids(request.user)
        key = cache_key("events", "list", request.user.id)

        def produce():
            qs = Event.objects.all().order_by("date", "title")
            return EventAppSerializer(
                qs, many=True, context={"registered_ids": registered_ids}
            ).data

        return Response(cache_get_or_set(key, TTL_DASHBOARD, produce))

    # -- POST /events/{id}/register (toggle) ------------------------------
    @extend_schema(request=None, responses={200: EventAppSerializer})
    def register(self, request, pk=None):
        event = self.get_object()
        service = EventRegistrationService(
            actor=request.user, ip=self._client_ip()
        )
        service.toggle(event, request.user)
        registered_ids = self._registered_ids(request.user)
        data = EventAppSerializer(
            event, context={"registered_ids": registered_ids}
        ).data
        return Response(data)
