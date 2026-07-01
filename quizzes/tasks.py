"""Background jobs for the quizzes app.

Currently a placeholder: quiz creation is synchronous and cheap. AI-assisted
quiz generation (the ``ai`` module's ``quiz-gen`` feature) enqueues its work
there; if we later add heavy post-create work (e.g. notifying enrolled students
that a new quiz is live), it belongs here as a Celery task.
"""
from __future__ import annotations

from celery import shared_task


@shared_task
def notify_quiz_published(quiz_id: str) -> str:
    """Placeholder: notify enrolled students that a new quiz is available.

    Wired for future use; returns the quiz id it was called with.
    """
    return str(quiz_id)
