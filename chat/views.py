"""HTTP layer for the chat app.

A single :class:`ChatThreadViewSet` serves the mobile ``chatService`` contract:

- ``GET  /chat/threads``                    — the requesting user's threads
  (``ChatThread[]``, ``lastMessageAt`` desc), paginated/filterable.
- ``GET  /chat/threads/{id}``               — one thread (``ChatThread``).
- ``POST /chat/threads/{id}/messages``      — send a message (``{ text }`` →
  ``ChatThread``); increments the recipient's unread + broadcasts realtime.
- ``POST /chat/threads/{id}/read``          — mark the thread read for the
  requesting user (``void``).

Only the two thread participants (or an admin) may see or act on a thread —
enforced object-level by :class:`chat.permissions.IsThreadParticipant`. The
queryset is *also* scoped to the requesting user's threads so list never leaks
other conversations. Writes flow through :class:`chat.services.ChatService`
(audit + cache-invalidation).
"""
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.permissions import Role, RoleModelPermission

from chat.models import ChatThread
from chat.permissions import CHAT_MATRIX, IsThreadParticipant
from chat.repositories import ChatThreadRepository
from chat.serializers import ChatThreadSerializer, SendMessageSerializer
from chat.services import ChatService


class ChatThreadViewSet(viewsets.ReadOnlyModelViewSet):
    """List/retrieve the requesting user's chat threads + message/read actions."""

    serializer_class = ChatThreadSerializer
    permission_classes = [IsAuthenticated, RoleModelPermission, IsThreadParticipant]
    permission_matrix = CHAT_MATRIX
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["teacher_name", "subject_label"]
    ordering_fields = ["last_message_at", "created_at"]
    ordering = ["-last_message_at"]

    def get_queryset(self):
        """Scope to threads the requesting user participates in.

        Admins see every thread (support/oversight); everyone else only their
        own conversations, so ``list`` cannot leak another user's threads.
        """
        repo = ChatThreadRepository()
        user = self.request.user
        if getattr(user, "role", None) in set(Role.ADMINS):
            return repo.get_queryset()
        return repo.for_participant(user)

    # -- service helpers --------------------------------------------------
    def _client_ip(self):
        xff = self.request.META.get("HTTP_X_FORWARDED_FOR")
        if xff:
            return xff.split(",")[0].strip()
        return self.request.META.get("REMOTE_ADDR")

    def _chat_service(self):
        return ChatService(actor=self.request.user, ip=self._client_ip())

    # -- POST /chat/threads/{id}/messages ---------------------------------
    @action(detail=True, methods=["post"])
    def messages(self, request, *args, **kwargs):
        """Send a message to the thread; returns the updated thread."""
        thread = self.get_object()  # runs object-level participant check
        serializer = SendMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        self._chat_service().send_message(
            thread=thread, user=request.user, text=serializer.validated_data["text"]
        )
        thread = self.get_queryset().get(pk=thread.pk)  # refreshed with new message
        return Response(
            ChatThreadSerializer(thread, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )

    # -- POST /chat/threads/{id}/read -------------------------------------
    @action(detail=True, methods=["post"])
    def read(self, request, *args, **kwargs):
        """Mark the thread read for the requesting user (``void``)."""
        thread = self.get_object()  # runs object-level participant check
        self._chat_service().mark_read(thread=thread, user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
