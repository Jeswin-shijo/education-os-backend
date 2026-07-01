"""Business-logic layer for the chat app.

Services extend :class:`core.services.BaseService` so writes auto-stamp
``created_by``/``updated_by``, emit an :class:`~core.models.AuditLog` row, and
invalidate cached chat views. Chat reads are cached under the ``chat`` prefix;
any write busts that prefix.

:class:`ChatService` owns the two mutating flows the app exercises:

- ``send_message(thread, user, text)`` — append a message, bump
  ``last_message_at``, increment the *other* participant's unread counter, then
  broadcast the new message to the thread's realtime group.
- ``mark_read(thread, user)`` — zero the requesting user's unread counter and
  flag their inbound messages as read.
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from core.cache import invalidate_prefix
from core.models import AuditLog
from core.permissions import Role
from core.services import BaseService

from chat.models import ChatMessage, ChatThread
from chat.repositories import ChatMessageRepository, ChatThreadRepository

# Cache-key prefix owned by this app.
CHAT_PREFIX = "chat"


def _sender_role_for(user) -> str:
    """Map a participant user to the app's 'parent'|'teacher' discriminator."""
    if getattr(user, "role", None) == Role.PARENT:
        return ChatMessage.SENDER_PARENT
    return ChatMessage.SENDER_TEACHER


class ChatThreadService(BaseService):
    model = ChatThread
    repository_class = ChatThreadRepository
    entity_name = "ChatThread"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(CHAT_PREFIX)


class ChatService(BaseService):
    """Message-level operations on a thread."""

    model = ChatMessage
    repository_class = ChatMessageRepository
    entity_name = "ChatMessage"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(CHAT_PREFIX)

    @transaction.atomic
    def send_message(self, thread: ChatThread, user, text: str) -> ChatMessage:
        """Append ``text`` from ``user`` to ``thread`` and fan out.

        Increments the *other* participant's unread counter, updates
        ``last_message_at``, audits the write, invalidates the chat cache, and
        broadcasts the new message to the thread's Channels group.
        """
        now = timezone.now()
        actor = self._actor_or_none()
        message = self.repository.create(
            thread=thread,
            sender=user,
            sender_role=_sender_role_for(user),
            text=text,
            at=now,
            read=False,
            created_by=actor,
            updated_by=actor,
        )

        # Bump the recipient's unread counter (the other participant).
        recipient_id = (
            thread.parent_id if user.id == thread.teacher_id else thread.teacher_id
        )
        counts = dict(thread.unread_count or {})
        counts[str(recipient_id)] = int(counts.get(str(recipient_id), 0)) + 1
        thread.unread_count = counts
        thread.last_message_at = now
        thread.save(update_fields=["unread_count", "last_message_at", "updated_at"])

        self.audit(
            AuditLog.ACTION_CREATE,
            entity_id=message.pk,
            changes={"thread": str(thread.pk), "text": text},
        )
        self.invalidate_cache(message)
        self._broadcast(thread, message)
        return message

    @transaction.atomic
    def mark_read(self, thread: ChatThread, user) -> ChatThread:
        """Zero ``user``'s unread counter and mark inbound messages read."""
        counts = dict(thread.unread_count or {})
        counts[str(user.id)] = 0
        thread.unread_count = counts
        thread.save(update_fields=["unread_count", "updated_at"])

        # Flag messages addressed to this user (i.e. not sent by them) as read.
        thread.messages.filter(read=False).exclude(sender_id=user.id).update(read=True)

        self.audit(
            AuditLog.ACTION_UPDATE,
            entity_id=thread.pk,
            changes={"read_by": str(user.id)},
        )
        self.invalidate_cache()
        return thread

    # -- realtime ---------------------------------------------------------
    def _broadcast(self, thread: ChatThread, message: ChatMessage) -> None:
        """Push the new message to the thread's Channels group (best-effort)."""
        try:
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer

            from chat.serializers import ChatMessageSerializer

            layer = get_channel_layer()
            if layer is None:
                return
            payload = ChatMessageSerializer(message).data
            payload["at"] = message.at.isoformat()
            async_to_sync(layer.group_send)(
                thread_group_name(thread.pk),
                {"type": "chat.message", "message": payload},
            )
        except Exception:  # pragma: no cover - realtime is best-effort
            # Never fail a request because the realtime fan-out hiccuped.
            pass


def thread_group_name(thread_id) -> str:
    """Channels group name for a thread (shared by service + consumer)."""
    return f"chat_{thread_id}"
