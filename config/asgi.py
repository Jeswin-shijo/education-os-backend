"""ASGI entrypoint: routes HTTP to Django and WebSocket to Channels.

Module `routing.py` files append their websocket urlpatterns to
``config.routing.websocket_urlpatterns`` as they are built; this file stays
importable with no module routing wired yet.
"""
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.core.asgi import get_asgi_application

# Initialise Django (populates apps) before importing anything model-aware.
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

from config.routing import websocket_urlpatterns  # noqa: E402
from config.ws_auth import JWTAuthMiddlewareStack  # noqa: E402

# Realtime modules append their websocket urlpatterns here.
from chat.routing import websocket_urlpatterns as chat_ws  # noqa: E402
from notifications.routing import (  # noqa: E402
    websocket_urlpatterns as notifications_ws,
)

websocket_urlpatterns = [
    *websocket_urlpatterns,
    *notifications_ws,
    *chat_ws,
]

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(
            JWTAuthMiddlewareStack(URLRouter(websocket_urlpatterns))
        ),
    }
)
