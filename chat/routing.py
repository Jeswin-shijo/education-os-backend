"""WebSocket URL patterns for chat realtime.

The integrate step extends ``config.routing.websocket_urlpatterns`` with these
so ``config/asgi.py`` routes ``ws://…/ws/chat/<thread_id>/`` to
:class:`chat.consumers.ChatConsumer` (behind the JWT auth middleware).
"""
from django.urls import re_path

from chat.consumers import ChatConsumer

websocket_urlpatterns = [
    re_path(
        r"^ws/chat/(?P<thread_id>[0-9a-f-]+)/$",
        ChatConsumer.as_asgi(),
    ),
]
