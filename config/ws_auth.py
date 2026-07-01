"""JWT authentication middleware for Channels WebSocket connections.

Reads a SimpleJWT access token from the ``?token=`` query param (or an
``Authorization: Bearer <token>`` header) and sets ``scope["user"]``.
Falls back to AnonymousUser when the token is missing/invalid.
"""
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware


@database_sync_to_async
def _get_user(user_id):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    try:
        return User.objects.get(id=user_id, is_active=True)
    except User.DoesNotExist:
        return None


def _extract_token(scope):
    query = parse_qs((scope.get("query_string") or b"").decode())
    if query.get("token"):
        return query["token"][0]
    for name, value in scope.get("headers", []):
        if name == b"authorization":
            parts = value.decode().split()
            if len(parts) == 2 and parts[0].lower() == "bearer":
                return parts[1]
    return None


class JWTAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        from django.contrib.auth.models import AnonymousUser
        from rest_framework_simplejwt.exceptions import TokenError
        from rest_framework_simplejwt.tokens import AccessToken

        scope = dict(scope)
        scope["user"] = AnonymousUser()

        token = _extract_token(scope)
        if token:
            try:
                validated = AccessToken(token)
                user = await _get_user(validated["user_id"])
                if user is not None:
                    scope["user"] = user
            except (TokenError, KeyError):
                pass

        return await super().__call__(scope, receive, send)


def JWTAuthMiddlewareStack(inner):
    """Convenience wrapper mirroring channels' AuthMiddlewareStack naming."""
    return JWTAuthMiddleware(inner)
