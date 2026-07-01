"""Quizzes domain models.

A :class:`Quiz` is a faculty-created quiz for a subject (mirroring the app's
``types.ts`` ``Quiz``: ``subjectId`` + ``title`` + ``questions``). It optionally
links to a :class:`faculty.FacultyClass` so a quiz can be scoped to a concrete
teaching assignment (the section the faculty teaches); the app contract keys off
the subject, so ``faculty_class`` is nullable.

A :class:`QuizQuestion` is one multiple-choice question of a quiz — the prompt
``text`` (app ``q``), the ``options`` list, and the ``answer_index`` of the
correct option (app ``answerIndex``). ``order`` keeps the questions stable.

Every model extends :class:`core.models.BaseModel` (UUID PK, audit fields,
soft-delete).
"""
from django.core.exceptions import ValidationError
from django.db import models

from core.models import BaseModel


class Quiz(BaseModel):
    """A faculty-created quiz for a subject."""

    subject = models.ForeignKey(
        "academics.Subject",
        on_delete=models.CASCADE,
        related_name="quizzes",
    )
    title = models.CharField(max_length=255)
    # Optional scoping to a concrete teaching assignment; the app contract keys
    # off the subject, so this stays nullable.
    faculty_class = models.ForeignKey(
        "faculty.FacultyClass",
        on_delete=models.SET_NULL,
        related_name="quizzes",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Quiz"
        verbose_name_plural = "Quizzes"
        indexes = [
            models.Index(fields=["subject"]),
            models.Index(fields=["faculty_class"]),
        ]

    def __str__(self):
        return self.title


class QuizQuestion(BaseModel):
    """A single multiple-choice question belonging to a :class:`Quiz`."""

    quiz = models.ForeignKey(
        Quiz,
        on_delete=models.CASCADE,
        related_name="questions",
    )
    text = models.TextField()
    # A JSON list of answer-option strings, e.g. ["O(1)", "O(n)", "O(log n)"].
    options = models.JSONField(default=list)
    # Zero-based index into ``options`` marking the correct answer.
    answer_index = models.PositiveSmallIntegerField(default=0)
    # Stable presentation order within the quiz.
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["quiz", "order"]
        verbose_name = "Quiz Question"
        verbose_name_plural = "Quiz Questions"
        indexes = [
            models.Index(fields=["quiz"]),
        ]

    def __str__(self):
        return self.text[:60]

    def clean(self):
        """Guard that ``answer_index`` points at a real option."""
        if not isinstance(self.options, list):
            raise ValidationError({"options": "options must be a list."})
        if self.options and not (0 <= self.answer_index < len(self.options)):
            raise ValidationError(
                {"answer_index": "answer_index is out of range for options."}
            )
