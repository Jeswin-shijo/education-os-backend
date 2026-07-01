"""Aggregated WebSocket URL patterns.

Modules with realtime consumers (transport, notifications, chat, ...) append
their ``websocket_urlpatterns`` here, e.g. in the app's ``apps.py`` ready() or
by extending this list. Starts empty so ASGI is importable with no consumers.
"""

websocket_urlpatterns = []
