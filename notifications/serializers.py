"""I/O serializers for the notifications app.

* :class:`NotificationSerializer` — full CRUD/admin shape (model fields + FK ids).
* :class:`NotificationAppSerializer` — the exact ``types.ts`` ``NotificationItem``
  shape the mobile app expects (``{ id, title, body, category, createdAt, read }``).
* :class:`UnreadCountSerializer` — ``{ count }`` response.
* :class:`BroadcastInputSerializer` — validated admin broadcast body
  (``{ title, body, category, role? }``).
"""
from rest_framework import serializers

from core.permissions import Role

from notifications.models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    """Admin/CRUD serializer: full model fields including recipient FK."""

    class Meta:
        model = Notification
        fields = [
            "id",
            "recipient",
            "broadcast_role",
            "title",
            "body",
            "category",
            "read",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class NotificationAppSerializer(serializers.ModelSerializer):
    """Matches ``types.ts`` ``NotificationItem`` (camelCase ``createdAt``)."""

    id = serializers.CharField(read_only=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = Notification
        fields = ["id", "title", "body", "category", "createdAt", "read"]


class UnreadCountSerializer(serializers.Serializer):
    """``{ count: number }`` response for the unread-count endpoint."""

    count = serializers.IntegerField(read_only=True)


class BroadcastInputSerializer(serializers.Serializer):
    """Validated input for ``POST /notifications/broadcast``.

    ``role`` is optional; when omitted/blank the broadcast targets all roles.
    """

    title = serializers.CharField(max_length=255)
    body = serializers.CharField(allow_blank=True, required=False, default="")
    category = serializers.ChoiceField(choices=Notification.CATEGORY_CHOICES)
    role = serializers.ChoiceField(
        choices=Role.CHOICES, required=False, allow_blank=True, default=""
    )
