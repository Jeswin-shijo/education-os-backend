"""Data-access layer for the quizzes app.

Repositories wrap each model over the soft-delete-aware default manager and add
``select_related``/``prefetch_related`` where serializers touch related rows,
avoiding N+1 queries.
"""
from __future__ import annotations

from core.repositories import BaseRepository

from quizzes.models import Quiz, QuizQuestion


class QuizRepository(BaseRepository):
    model = Quiz

    def get_queryset(self, include_deleted: bool = False):
        return (
            super()
            .get_queryset(include_deleted)
            .select_related("subject", "faculty_class")
            .prefetch_related("questions")
        )


class QuizQuestionRepository(BaseRepository):
    model = QuizQuestion

    def get_queryset(self, include_deleted: bool = False):
        return super().get_queryset(include_deleted).select_related("quiz")

    def for_quiz(self, quiz_id):
        return self.get_queryset().filter(quiz_id=quiz_id).order_by("order")
