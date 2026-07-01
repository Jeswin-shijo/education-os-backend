"""Chat domain models — parent ↔ teacher messaging.

Mirrors the mobile app's ``types.ts`` (``ChatThread`` / ``ChatMessage``) as
consumed by ``chatService``:

    ChatMessage = { id, sender: 'parent'|'teacher', text, at }
    ChatThread  = { id, teacherName, teacherSubject, avatarColor,
                    lastMessageAt, unread, messages }

Backend shape adds proper FKs so RBAC can be enforced object-level: a thread has
a ``teacher`` (a ``faculty`` user) and a ``parent`` (a ``parent`` user) — the two
participants. ``teacher_name``/``teacher_subject``/``avatar_color`` are denormalised
onto the thread so the list view can render without extra joins (they mirror the
app fields), while the participant FKs are the source of truth for authorization.

``unread_count`` is a JSON map ``{ "<user_id>": <int> }`` so each participant has
their own unread counter (the app surfaces the *requesting* user's count as
``unread``). ``last_message_at`` powers the app's ``lastMessageAt`` desc sort.

Every model extends :class:`core.models.BaseModel` (UUID PK, audit fields,
soft-delete).
"""
from django.conf import settings
from django.db import models

from core.models import BaseModel


class ChatThread(BaseModel):
    """A parent ↔ teacher conversation (two participants)."""

    # The faculty participant (app ``teacherName``/``teacherSubject`` owner).
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_threads_as_teacher",
    )
    # The parent participant.
    parent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_threads_as_parent",
    )
    # Denormalised display fields mirroring the app's ChatThread.
    teacher_name = models.CharField(max_length=255, blank=True)
    subject_label = models.CharField(max_length=255, blank=True)
    avatar_color = models.CharField(max_length=9, blank=True)
    # Sort key for the threads list (app ``lastMessageAt``).
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)
    # Per-user unread counters: { "<user_id>": <int> }.
    unread_count = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-last_message_at", "-created_at"]
        verbose_name = "Chat Thread"
        verbose_name_plural = "Chat Threads"
        indexes = [
            models.Index(fields=["teacher"]),
            models.Index(fields=["parent"]),
            models.Index(fields=["-last_message_at"]),
        ]

    def __str__(self):
        return f"{self.teacher_name or self.teacher_id} ↔ {self.parent_id}"

    # -- participant helpers ---------------------------------------------
    def is_participant(self, user) -> bool:
        """Whether ``user`` is one of the two thread participants."""
        uid = getattr(user, "id", None)
        return uid is not None and uid in (self.teacher_id, self.parent_id)

    def unread_for(self, user) -> int:
        """The unread count for ``user`` (0 if none)."""
        return int((self.unread_count or {}).get(str(getattr(user, "id", "")), 0))


class ChatMessage(BaseModel):
    """One message in a :class:`ChatThread`."""

    SENDER_PARENT = "parent"
    SENDER_TEACHER = "teacher"
    SENDER_CHOICES = [
        (SENDER_PARENT, "Parent"),
        (SENDER_TEACHER, "Teacher"),
    ]

    thread = models.ForeignKey(
        ChatThread,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_messages",
    )
    # App ``sender`` discriminator ('parent' | 'teacher').
    sender_role = models.CharField(
        max_length=16, choices=SENDER_CHOICES, default=SENDER_PARENT
    )
    text = models.TextField()
    # App ``at`` — when the message was sent.
    at = models.DateTimeField(db_index=True)
    read = models.BooleanField(default=False)

    class Meta:
        ordering = ["at"]
        verbose_name = "Chat Message"
        verbose_name_plural = "Chat Messages"
        indexes = [
            models.Index(fields=["thread", "at"]),
        ]

    def __str__(self):
        return f"{self.sender_role}: {self.text[:40]}"
