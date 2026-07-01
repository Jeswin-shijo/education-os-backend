"""Channels routing for the notifications app.

The integrate step imports ``websocket_urlpatterns`` and appends them to the
project's ``URLRouter`` in ``config/asgi.py``. Endpoint:
``ws://<host>/ws/notifications/`` -> :class:`NotificationConsumer`.
"""
from django.urls import path

from notifications.consumers import NotificationConsumer

websocket_urlpatterns = [
    path("ws/notifications/", NotificationConsumer.as_asgi()),
]
