"""I/O serializers for the chat app.

The mobile app (``types.ts``) expects camelCase:

    ChatMessage = { id, sender: 'parent'|'teacher', text, at }
    ChatThread  = { id, teacherName, teacherSubject, avatarColor,
                    lastMessageAt, unread, messages }

``ChatThreadSerializer`` needs the *requesting* user to compute ``unread`` (the
per-user counter). The view passes it via serializer ``context['request']``.
"""
from rest_framework import serializers

from chat.models import ChatMessage, ChatThread


class ChatMessageSerializer(serializers.ModelSerializer):
    """Matches ``types.ts`` ``ChatMessage`` (camelCase)."""

    id = serializers.CharField(read_only=True)
    sender = serializers.CharField(source="sender_role", read_only=True)
    text = serializers.CharField(read_only=True)
    at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = ChatMessage
        fields = ["id", "sender", "text", "at"]


class ChatThreadSerializer(serializers.ModelSerializer):
    """Matches ``types.ts`` ``ChatThread`` (camelCase, nested messages).

    ``unread`` is resolved for the requesting user from the thread's per-user
    ``unread_count`` map.
    """

    id = serializers.CharField(read_only=True)
    teacherName = serializers.CharField(source="teacher_name", read_only=True)
    teacherSubject = serializers.CharField(source="subject_label", read_only=True)
    avatarColor = serializers.CharField(source="avatar_color", read_only=True)
    # The parent participant's name — the counterpart shown in the FACULTY view
    # (the faculty's Messages screen lists parents, not themselves). Parent
    # screens ignore it and keep using teacherName.
    parentName = serializers.CharField(source="parent.full_name", read_only=True)
    lastMessageAt = serializers.DateTimeField(source="last_message_at", read_only=True)
    unread = serializers.SerializerMethodField()
    messages = ChatMessageSerializer(many=True, read_only=True)

    class Meta:
        model = ChatThread
        fields = [
            "id",
            "teacherName",
            "teacherSubject",
            "avatarColor",
            "parentName",
            "lastMessageAt",
            "unread",
            "messages",
        ]

    def get_unread(self, obj) -> int:
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is None or not getattr(user, "is_authenticated", False):
            return 0
        return obj.unread_for(user)


class SendMessageSerializer(serializers.Serializer):
    """Validates ``POST /chat/threads/:id/messages`` body ``{ text }``."""

    text = serializers.CharField(min_length=1, trim_whitespace=True)


# ---------------------------------------------------------------------------
# Mobile API contract (spec) serializers — snake_case.
# ---------------------------------------------------------------------------
class ChatMessageSpecSerializer(serializers.ModelSerializer):
    """Spec message shape: ``{ id, sender, text, at }`` (``sender`` = role)."""

    id = serializers.CharField(read_only=True)
    sender = serializers.CharField(source="sender_role", read_only=True)
    text = serializers.CharField(read_only=True)
    at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = ChatMessage
        fields = ["id", "sender", "text", "at"]


class ChatThreadSpecSerializer(serializers.ModelSerializer):
    """Spec conversation shape (snake_case) with nested history.

    ``{ id, teacher_name, subject, avatar_color, last_message_at, unread,
    messages }``. ``unread`` is the requesting user's per-user counter.
    """

    id = serializers.CharField(read_only=True)
    teacher_name = serializers.CharField(read_only=True)
    subject = serializers.CharField(source="subject_label", read_only=True)
    avatar_color = serializers.CharField(read_only=True)
    last_message_at = serializers.DateTimeField(read_only=True)
    unread = serializers.SerializerMethodField()
    messages = ChatMessageSpecSerializer(many=True, read_only=True)

    class Meta:
        model = ChatThread
        fields = [
            "id",
            "teacher_name",
            "subject",
            "avatar_color",
            "last_message_at",
            "unread",
            "messages",
        ]

    def get_unread(self, obj) -> int:
        # A staff caller listing another user's threads wants *that* user's
        # unread count, passed as ``context['unread_user']``; otherwise fall
        # back to the requesting user.
        user = self.context.get("unread_user")
        if user is None:
            request = self.context.get("request")
            user = getattr(request, "user", None)
        if user is None or not getattr(user, "is_authenticated", False):
            return 0
        return obj.unread_for(user)


class ChatCreateSerializer(serializers.Serializer):
    """Validates ``POST /api/v1/chat`` — create a conversation.

    The requesting participant is inferred from their role; the other
    participant is supplied (``teacher_id`` for a parent caller, ``parent_id``
    for a teacher caller). Staff/admin must supply both.
    """

    teacher_id = serializers.UUIDField(required=False)
    parent_id = serializers.UUIDField(required=False)
    subject = serializers.CharField(required=False, allow_blank=True, default="")


class ChatMessageInputSerializer(serializers.Serializer):
    """Validates ``POST /api/v1/chat/message`` — ``{ conversation_id, text }``."""

    conversation_id = serializers.UUIDField()
    text = serializers.CharField(min_length=1, trim_whitespace=True)
