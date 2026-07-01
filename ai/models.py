"""AI assistant domain models.

Mirrors the mobile app's ``types.ts`` shapes:

    AIFeatureKey = 'mentor' | 'doubt' | 'notes' | 'assignment'
                 | 'resume' | 'career' | 'chat'
    AIMessage    = { id, role: 'user' | 'assistant', text, at }
    AIThread     = { id, feature, title, messages: AIMessage[] }

An :class:`AIThread` is one per-feature conversation owned by a single
``user`` (the app keeps a single thread per feature — see
``aiService.getThread`` which finds/creates by feature). An :class:`AIMessage`
is one turn in that thread, either the ``user`` prompt or the ``assistant``
reply, timestamped by ``at``.

Every model extends :class:`core.models.BaseModel` (UUID PK, audit fields,
soft-delete). Ownership is enforced in the view/service layer (own threads
only).
"""
from django.conf import settings
from django.db import models

from core.models import BaseModel


class AIFeature(models.TextChoices):
    """The feature surfaces the app exposes (``AIFeatureKey``)."""

    MENTOR = "mentor", "AI Mentor"
    DOUBT = "doubt", "AI Doubt Solver"
    NOTES = "notes", "AI Lecture Notes"
    ASSIGNMENT = "assignment", "AI Assignment Helper"
    RESUME = "resume", "AI Resume Analyzer"
    CAREER = "career", "AI Career Guide"
    CHAT = "chat", "AI Assistant"


# Default per-feature thread titles (mirror aiService FEATURE_TITLES).
FEATURE_TITLES = {
    AIFeature.MENTOR: "AI Mentor",
    AIFeature.DOUBT: "AI Doubt Solver",
    AIFeature.NOTES: "AI Lecture Notes",
    AIFeature.ASSIGNMENT: "AI Assignment Helper",
    AIFeature.RESUME: "AI Resume Analyzer",
    AIFeature.CAREER: "AI Career Guide",
    AIFeature.CHAT: "AI Assistant",
}


class AIThread(BaseModel):
    """A per-feature AI conversation owned by one user."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ai_threads",
    )
    feature = models.CharField(
        max_length=32, choices=AIFeature.choices, db_index=True
    )
    title = models.CharField(max_length=255)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "AI Thread"
        verbose_name_plural = "AI Threads"
        # The app keeps one live thread per (user, feature).
        constraints = [
            models.UniqueConstraint(
                fields=["user", "feature"],
                condition=models.Q(is_deleted=False),
                name="uniq_ai_thread_user_feature_active",
            )
        ]
        indexes = [
            models.Index(fields=["user", "feature"]),
        ]

    def __str__(self):
        return f"{self.get_feature_display()} — {self.user_id}"


class AIMessage(BaseModel):
    """One turn (user prompt or assistant reply) within an :class:`AIThread`."""

    ROLE_USER = "user"
    ROLE_ASSISTANT = "assistant"
    ROLE_CHOICES = [
        (ROLE_USER, "User"),
        (ROLE_ASSISTANT, "Assistant"),
    ]

    thread = models.ForeignKey(
        AIThread,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(max_length=16, choices=ROLE_CHOICES)
    text = models.TextField()
    # Conversation timestamp (app ``at``); defaults to creation time.
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["at"]
        verbose_name = "AI Message"
        verbose_name_plural = "AI Messages"
        indexes = [
            models.Index(fields=["thread", "at"]),
        ]

    def __str__(self):
        return f"{self.role}: {self.text[:50]}"
