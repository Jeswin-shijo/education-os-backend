"""Realtime notifications WebSocket consumer (JWT-authed).

The client connects to ``ws://<host>/ws/notifications/`` with a JWT. The
integrate step wires the ASGI stack so that ``config/asgi.py`` runs a JWT-auth
middleware which populates ``scope["user"]``; as a defensive fallback this
consumer also accepts a token via ``?token=<jwt>`` or the ``Authorization``
header and validates it itself. Each authenticated user joins a per-user group
(:func:`user_group_name`) so :func:`notifications.tasks.send_push_notification`
can push freshly-created notifications to connected clients in realtime.

Kept intentionally simple + importable: one group per user, JSON messages of the
shape ``{ type: "notification", data: <NotificationItem> }``.
"""
from __future__ import annotations

from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer


def user_group_name(user_id) -> str:
    """Channels group name for a single user's notification stream."""
    return f"notifications_user_{user_id}"


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    """Per-user realtime notification stream."""

    async def connect(self):
        user = await self._get_user()
        if user is None:
            # Reject unauthenticated connections.
            await self.close(code=4401)
            return
        self.user = user
        self.group_name = user_group_name(user.pk)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        group_name = getattr(self, "group_name", None)
        if group_name and self.channel_layer is not None:
            await self.channel_layer.group_discard(group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        """Support a lightweight ping/keepalive; the stream is server -> client."""
        if content.get("type") == "ping":
            await self.send_json({"type": "pong"})

    # -- group event handler ---------------------------------------------
    async def notify(self, event):
        """Handle a ``group_send`` of ``{"type": "notify", "payload": {...}}``."""
        await self.send_json({"type": "notification", "data": event["payload"]})

    # -- auth -------------------------------------------------------------
    async def _get_user(self):
        """Resolve the connecting user from scope, then from a JWT fallback."""
        user = self.scope.get("user")
        if user is not None and getattr(user, "is_authenticated", False):
            return user
        token = self._extract_token()
        if not token:
            return None
        return await self._user_from_token(token)

    def _extract_token(self):
        # ?token=<jwt>
        query = parse_qs(self.scope.get("query_string", b"").decode())
        token_list = query.get("token")
        if token_list:
            return token_list[0]
        # Authorization: Bearer <jwt>
        for name, value in self.scope.get("headers", []):
            if name == b"authorization":
                raw = value.decode()
                if raw.lower().startswith("bearer "):
                    return raw.split(" ", 1)[1].strip()
        return None

    @database_sync_to_async
    def _user_from_token(self, token):
        try:
            from django.contrib.auth import get_user_model
            from rest_framework_simplejwt.tokens import AccessToken

            access = AccessToken(token)
            user_id = access.get("user_id")
            if user_id is None:
                return None
            User = get_user_model()
            return User.objects.filter(pk=user_id, is_active=True).first()
        except Exception:
            return None
