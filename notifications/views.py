"""HTTP layer for the notifications app.

Endpoints (mounted under ``/api/v1/`` by the integrate step):

- ``GET  /notifications``               — the requesting user's notifications (newest first), cached.
- ``POST /notifications/{id}/read``      — mark one notification read.
- ``POST /notifications/read-all``       — mark all of the user's own notifications read.
- ``GET  /notifications/unread-count``   — ``{ count }`` (cached).
- ``POST /notifications/broadcast``      — admin: create a broadcast for a role/all.
- admin CRUD (``create``/``update``/``destroy``) flows through the service.

Business logic + cache invalidation live in :class:`NotificationService`; the
viewset stays thin. All reads are scoped to ``request.user``.
"""
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from core.cache import TTL_NOTIFICATIONS, cache_get_or_set
from core.viewsets import BaseModelViewSet

from notifications.models import Notification
from notifications.permissions import NOTIFICATIONS_MATRIX
from notifications.serializers import (
    BroadcastInputSerializer,
    NotificationAppSerializer,
    NotificationSerializer,
    UnreadCountSerializer,
)
from notifications.services import NotificationService, user_scope_key


class NotificationViewSet(BaseModelViewSet):
    """Per-user notifications + admin broadcast, backed by ``NotificationService``."""

    queryset = Notification.objects.select_related("recipient").all()
    serializer_class = NotificationSerializer
    service_class = NotificationService
    permission_matrix = NOTIFICATIONS_MATRIX
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["category", "read"]
    search_fields = ["title", "body"]
    ordering_fields = ["created_at", "category", "read"]

    # Admin-only actions operate across all rows; the rest are self-scoped.
    ADMIN_ACTIONS = {"create", "update", "partial_update", "destroy", "broadcast"}

    def get_queryset(self):
        """Scope reads/per-user mutations to the requesting user's notifications.

        List/retrieve/read/read-all only ever see the caller's own rows +
        broadcasts targeting them, so a user can never touch another user's
        notification. Admin CRUD actions operate over the full queryset.
        """
        user = self.request.user
        if not (user and user.is_authenticated):
            return Notification.objects.none()
        if getattr(self, "action", None) in self.ADMIN_ACTIONS:
            return Notification.objects.select_related("recipient").all()
        return self.service_class(actor=user).list_for_user(user)

    def list(self, request, *args, **kwargs):
        """App-shaped list of the user's notifications (newest first), cached."""
        user = request.user

        def build():
            qs = self.filter_queryset(self.get_queryset())
            return NotificationAppSerializer(qs, many=True).data

        # Cache the unfiltered default view; skip cache when filters/search applied.
        if request.query_params:
            data = NotificationAppSerializer(
                self.filter_queryset(self.get_queryset()), many=True
            ).data
            page = self.paginate_queryset(data)
            if page is not None:
                return self.get_paginated_response(page)
            return Response(data)

        data = cache_get_or_set(
            user_scope_key(user.pk, "list"), TTL_NOTIFICATIONS, build
        )
        page = self.paginate_queryset(data)
        if page is not None:
            return self.get_paginated_response(page)
        return Response(data)

    @extend_schema(request=None, responses={200: NotificationAppSerializer})
    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        """``POST /notifications/{id}/read`` — mark a single notification read."""
        instance = self.get_object()
        # Broadcast rows have no recipient; a user marking a shared broadcast
        # read would flip it for everyone, so reject that here.
        if instance.recipient_id is None:
            raise PermissionDenied("Broadcast notifications cannot be marked read per-user.")
        service = self.get_service()
        instance = service.mark_read(instance)
        return Response(NotificationAppSerializer(instance).data)

    @extend_schema(request=None, responses={200: UnreadCountSerializer})
    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        """``POST /notifications/read-all`` — mark all own notifications read."""
        service = self.get_service()
        updated = service.mark_all_read(request.user)
        return Response({"updated": updated})

    @extend_schema(responses={200: UnreadCountSerializer})
    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        """``GET /notifications/unread-count`` — ``{ count }`` (cached)."""
        user = request.user
        service = self.service_class(actor=user)
        count = cache_get_or_set(
            user_scope_key(user.pk, "unread"),
            TTL_NOTIFICATIONS,
            lambda: service.unread_count(user),
        )
        return Response({"count": count})

    @extend_schema(request=BroadcastInputSerializer, responses={201: NotificationSerializer})
    @action(detail=False, methods=["post"])
    def broadcast(self, request):
        """``POST /notifications/broadcast`` — admin: broadcast to a role/all."""
        serializer = BroadcastInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        service = self.get_service()
        instance = service.broadcast(**serializer.validated_data)
        return Response(NotificationSerializer(instance).data, status=201)
