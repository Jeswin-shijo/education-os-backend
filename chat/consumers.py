"""Realtime WebSocket consumer for chat threads.

Clients connect to ``ws://…/ws/chat/<thread_id>/`` (JWT via ``?token=`` handled by
``config.ws_auth.JWTAuthMiddleware``, which sets ``scope['user']``). The consumer:

1. authenticates — rejects anonymous users,
2. authorises — rejects users who aren't participants in the thread,
3. joins the thread's Channels group so it receives messages broadcast by
   :meth:`chat.services.ChatService.send_message`.

Messages posted over HTTP (``POST /chat/threads/{id}/messages``) are fanned out to
this group by the service; the consumer relays them to the socket via
:meth:`chat_message`. Inbound socket frames are optional — the HTTP endpoint is
the source of truth for persistence — but a ``{ "type": "send", "text": ... }``
frame is accepted as a convenience and routed through the same service so it is
persisted, audited and broadcast identically.
"""
import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from chat.services import thread_group_name


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.thread_id = self.scope["url_route"]["kwargs"]["thread_id"]
        self.group_name = thread_group_name(self.thread_id)
        user = self.scope.get("user")

        if user is None or not getattr(user, "is_authenticated", False):
            await self.close(code=4401)  # unauthenticated
            return
        if not await self._is_participant(user, self.thread_id):
            await self.close(code=4403)  # forbidden
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        group = getattr(self, "group_name", None)
        if group is not None:
            await self.channel_layer.group_discard(group, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        """Optional inbound frame: persist + broadcast via the service."""
        if not text_data:
            return
        try:
            payload = json.loads(text_data)
        except (ValueError, TypeError):
            return
        if payload.get("type") != "send":
            return
        text = (payload.get("text") or "").strip()
        if not text:
            return
        await self._persist_and_broadcast(text)

    # -- group event handler ---------------------------------------------
    async def chat_message(self, event):
        """Relay a broadcast message frame to this socket."""
        await self.send(text_data=json.dumps({
            "type": "message",
            "message": event["message"],
        }))

    # -- db helpers -------------------------------------------------------
    @database_sync_to_async
    def _is_participant(self, user, thread_id):
        from core.permissions import Role

        from chat.models import ChatThread

        thread = (
            ChatThread.objects.filter(pk=thread_id)
            .only("id", "teacher_id", "parent_id")
            .first()
        )
        if thread is None:
            return False
        if getattr(user, "role", None) in set(Role.ADMINS):
            return True
        return thread.is_participant(user)

    @database_sync_to_async
    def _persist_and_broadcast(self, text):
        from chat.models import ChatThread
        from chat.services import ChatService

        thread = ChatThread.objects.filter(pk=self.thread_id).first()
        if thread is None:
            return
        user = self.scope["user"]
        ChatService(actor=user).send_message(thread=thread, user=user, text=text)
