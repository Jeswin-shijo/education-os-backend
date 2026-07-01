"""HTTP layer for the ai app.

A single :class:`AIViewSet` serves the mobile ``aiService`` contract, all
self-scoped to ``request.user`` (own threads only):

- ``GET  /ai/threads``                      -> ``AIThread[]`` (the user's threads)
- ``GET  /ai/threads/{feature}``            -> ``AIThread`` (find-or-create)
- ``POST /ai/{feature}/respond``            -> ``{prompt}`` -> ``{text}``
- ``POST /ai/threads/{feature}/messages``   -> ``{text}`` -> ``AIThread``
- ``GET  /ai/suggestions/{feature}``        -> static quick-prompt chips (``string[]``)

Reads are cached per-user under the ``ai`` prefix (TTL 60s); writes flow through
:class:`ai.services.AIThreadService` (audit + cache-invalidation). ``suggestions``
is a static client-contract lookup (no DB, no per-user cache).
"""
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.permissions import RoleModelPermission

from ai.llm import SUGGESTIONS
from ai.models import AIFeature
from ai.permissions import AI_MATRIX
from ai.repositories import AIThreadRepository
from ai.serializers import (
    AIThreadSerializer,
    RespondRequestSerializer,
    RespondResponseSerializer,
    SendMessageRequestSerializer,
)
from ai.services import (
    AIThreadService,
    TTL_AI,
    user_feature_key,
    user_threads_key,
)
from core.cache import cache_get_or_set

VALID_FEATURES = {value for value, _ in AIFeature.choices}


class AIViewSet(viewsets.ViewSet):
    """Personal AI assistant endpoints (own threads only)."""

    permission_classes = [IsAuthenticated, RoleModelPermission]
    permission_matrix = AI_MATRIX

    # -- helpers ---------------------------------------------------------
    def _client_ip(self):
        xff = self.request.META.get("HTTP_X_FORWARDED_FOR")
        if xff:
            return xff.split(",")[0].strip()
        return self.request.META.get("REMOTE_ADDR")

    def _service(self):
        return AIThreadService(actor=self.request.user, ip=self._client_ip())

    @staticmethod
    def _validate_feature(feature: str) -> str:
        if feature not in VALID_FEATURES:
            raise ValidationError(
                {"feature": f"Unknown AI feature '{feature}'."}
            )
        return feature

    # -- GET /ai/threads -------------------------------------------------
    @extend_schema(responses={200: AIThreadSerializer(many=True)})
    @action(detail=False, methods=["get"])
    def threads(self, request):
        """List the current user's AI threads (newest activity first)."""
        user = request.user
        repo = AIThreadRepository()

        def build():
            qs = repo.for_user(user)
            return AIThreadSerializer(qs, many=True).data

        data = cache_get_or_set(user_threads_key(user.id), TTL_AI, build)
        return Response(data)

    # -- GET /ai/threads/{feature} --------------------------------------
    @extend_schema(
        parameters=[
            OpenApiParameter(
                "feature", str, OpenApiParameter.PATH, enum=list(VALID_FEATURES)
            )
        ],
        responses={200: AIThreadSerializer},
    )
    @action(detail=False, methods=["get"], url_path=r"threads/(?P<feature>[^/.]+)")
    def thread_by_feature(self, request, feature=None):
        """Find-or-create the user's thread for ``feature``."""
        feature = self._validate_feature(feature)
        user = request.user

        def build():
            thread = self._service().get_or_create_thread(user, feature)
            return AIThreadSerializer(thread).data

        data = cache_get_or_set(
            user_feature_key(user.id, feature), TTL_AI, build
        )
        return Response(data)

    # -- POST /ai/{feature}/respond -------------------------------------
    @extend_schema(
        request=RespondRequestSerializer,
        responses={200: RespondResponseSerializer},
        parameters=[
            OpenApiParameter(
                "feature", str, OpenApiParameter.PATH, enum=list(VALID_FEATURES)
            )
        ],
    )
    @action(detail=False, methods=["post"], url_path=r"(?P<feature>[^/.]+)/respond")
    def respond(self, request, feature=None):
        """Stateless one-off reply: ``{prompt}`` -> ``{text}`` (not persisted)."""
        feature = self._validate_feature(feature)
        req = RespondRequestSerializer(data=request.data)
        req.is_valid(raise_exception=True)
        text = self._service().respond(feature, req.validated_data["prompt"])
        return Response({"text": text})

    # -- POST /ai/threads/{feature}/messages ----------------------------
    @extend_schema(
        request=SendMessageRequestSerializer,
        responses={201: AIThreadSerializer},
        parameters=[
            OpenApiParameter(
                "feature", str, OpenApiParameter.PATH, enum=list(VALID_FEATURES)
            )
        ],
    )
    @action(
        detail=False,
        methods=["post"],
        url_path=r"threads/(?P<feature>[^/.]+)/messages",
    )
    def send_message(self, request, feature=None):
        """Append the user's message + assistant reply; return the thread."""
        feature = self._validate_feature(feature)
        req = SendMessageRequestSerializer(data=request.data)
        req.is_valid(raise_exception=True)
        thread = self._service().send_message(
            request.user, feature, req.validated_data["text"]
        )
        return Response(
            AIThreadSerializer(thread).data, status=status.HTTP_201_CREATED
        )

    # -- GET /ai/suggestions/{feature} ----------------------------------
    @extend_schema(
        responses={200: RespondResponseSerializer},  # string[] in the envelope
        parameters=[
            OpenApiParameter(
                "feature", str, OpenApiParameter.PATH, enum=list(VALID_FEATURES)
            )
        ],
    )
    @action(
        detail=False, methods=["get"], url_path=r"suggestions/(?P<feature>[^/.]+)"
    )
    def suggestions(self, request, feature=None):
        """Static quick-prompt chips for ``feature`` (``string[]``)."""
        feature = self._validate_feature(feature)
        return Response(SUGGESTIONS.get(feature, []))
