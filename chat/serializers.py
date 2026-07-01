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
