"""Business-logic layer for the quizzes app.

Services extend :class:`core.services.BaseService` so writes auto-stamp
``created_by``/``updated_by``, emit an :class:`~core.models.AuditLog` row, and
invalidate cached quiz views. Quiz reads are cached under the ``quizzes`` prefix;
any write busts that prefix.

:class:`QuizService` overrides ``create`` to accept nested ``questions`` and
persist them alongside the quiz in a single transaction, so a faculty ``POST
/quizzes`` (with nested questions) is one atomic, audited operation.
"""
from __future__ import annotations

from django.db import transaction

from core.cache import invalidate_prefix
from core.models import AuditLog
from core.services import BaseService

from quizzes.models import Quiz, QuizQuestion
from quizzes.repositories import QuizQuestionRepository, QuizRepository

# Cache-key prefix owned by this app.
QUIZZES_PREFIX = "quizzes"


class QuizService(BaseService):
    model = Quiz
    repository_class = QuizRepository
    entity_name = "Quiz"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(QUIZZES_PREFIX)

    @transaction.atomic
    def create(self, **data) -> Quiz:
        """Create a quiz plus its nested questions atomically.

        ``questions`` (if present) is a list of validated dicts
        ``{text, options, answer_index, order?}``. The quiz row is stamped +
        audited by the parent ``create``; each question is stamped and audited
        too so the audit trail is complete.
        """
        questions = data.pop("questions", None) or []
        quiz = super().create(**data)

        actor = self._actor_or_none()
        for index, q in enumerate(questions):
            fields = dict(q)
            fields.setdefault("order", index)
            if actor is not None:
                fields.setdefault("created_by", actor)
                fields.setdefault("updated_by", actor)
            question = QuizQuestion.objects.create(quiz=quiz, **fields)
            AuditLog.objects.create(
                actor=actor,
                action=AuditLog.ACTION_CREATE,
                entity="QuizQuestion",
                entity_id=str(question.pk),
                changes={"quiz": str(quiz.pk), "text": question.text},
                ip=self.ip,
            )
        return quiz


class QuizQuestionService(BaseService):
    model = QuizQuestion
    repository_class = QuizQuestionRepository
    entity_name = "QuizQuestion"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(QUIZZES_PREFIX)
