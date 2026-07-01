"""HTTP layer for the quizzes app.

A single :class:`QuizViewSet` serves the mobile ``quizService`` contract:

- ``GET /quizzes`` — list all quizzes (``Quiz[]``), paginated/filterable.
- ``GET /quizzes/{id}`` — one quiz (``Quiz``).
- ``POST /quizzes`` — faculty create a quiz with nested questions
  (``CreateQuizInput`` → ``Quiz``).

List/retrieve reads are cached under the ``quizzes`` prefix (TTL 600s); writes
flow through :class:`quizzes.services.QuizService` (audit + cache-invalidation)
via :class:`core.viewsets.BaseModelViewSet`.
"""
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from core.cache import TTL_LIBRARY, cache_get_or_set, cache_key
from core.permissions import Role
from core.viewsets import BaseModelViewSet

from quizzes.models import Quiz
from quizzes.permissions import QUIZ_MATRIX
from quizzes.serializers import QuizCreateSerializer, QuizSerializer
from quizzes.services import QuizService

# Quizzes are library-like content; reuse the 600s library TTL.
TTL_QUIZZES = TTL_LIBRARY


class QuizViewSet(BaseModelViewSet):
    """Quizzes: list/retrieve for all roles, faculty/admin create."""

    queryset = (
        Quiz.objects.select_related("subject", "faculty_class")
        .prefetch_related("questions")
        .all()
    )
    serializer_class = QuizSerializer
    service_class = QuizService
    permission_matrix = QUIZ_MATRIX
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["subject", "faculty_class"]
    search_fields = ["title", "subject__code", "subject__name"]
    ordering_fields = ["title", "created_at"]

    def get_serializer_class(self):
        if self.action == "create":
            return QuizCreateSerializer
        return QuizSerializer

    # -- cached reads ----------------------------------------------------
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            data = self.get_serializer(page, many=True).data
            return self.get_paginated_response(data)
        return Response(self.get_serializer(queryset, many=True).data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()

        def build():
            return QuizSerializer(instance).data

        data = cache_get_or_set(
            cache_key("quizzes", "detail", instance.pk), TTL_QUIZZES, build
        )
        return Response(data)

    # -- owner-scoped mutations ------------------------------------------
    def _assert_owner(self, instance):
        """Faculty may only mutate quizzes they created; staff may mutate any."""
        if self.request.user.role == Role.FACULTY:
            if instance.created_by_id != self.request.user.id:
                raise PermissionDenied("You can only modify your own quizzes.")

    def perform_update(self, serializer):
        self._assert_owner(serializer.instance)
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        self._assert_owner(instance)
        super().perform_destroy(instance)
