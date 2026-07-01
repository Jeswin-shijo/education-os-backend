"""Background jobs for the ai app.

:func:`generate_ai_response` is the Celery task that produces an assistant reply
through the **pluggable LLM interface** (:mod:`ai.llm`). It works with no LLM
key configured because :func:`ai.llm.generate` degrades to a canned,
feature-specific fallback that mirrors the app's ``aiService`` responses.

The task supports two modes:

- *stateless* (``thread_id`` omitted): just compute and return the reply text.
  Used by ``POST /ai/:feature/respond`` when it wants the work off the request
  thread. The synchronous endpoint calls :func:`ai.llm.generate` directly for a
  fast round-trip; the task exists so heavier real-LLM calls can be enqueued.
- *persisting* (``thread_id`` given): compute the reply, append an assistant
  :class:`~ai.models.AIMessage` to the thread, touch the thread, and bust the
  cached thread views. Used to finish an async ``send`` when a real (slow) LLM
  is wired in.
"""
from __future__ import annotations

from celery import shared_task
from django.utils import timezone

from ai import llm


@shared_task(name="ai.generate_ai_response")
def generate_ai_response(feature: str, prompt: str, thread_id: str | None = None) -> str:
    """Generate (and optionally persist) an AI assistant reply.

    Returns the assistant text. When ``thread_id`` is supplied, the reply is
    also appended to that thread as an assistant message and the thread's cache
    is invalidated.
    """
    # Local imports keep the task import-light and avoid app-loading order issues.
    from ai.models import AIMessage, AIThread
    from ai.services import invalidate_thread_cache

    history = None
    thread = None
    if thread_id:
        thread = AIThread.objects.filter(pk=thread_id).first()
        if thread is not None:
            history = [
                {"role": m.role, "text": m.text}
                for m in thread.messages.all().order_by("at")
            ]

    text = llm.generate(feature, prompt, history=history)

    if thread is not None:
        AIMessage.objects.create(
            thread=thread,
            role=AIMessage.ROLE_ASSISTANT,
            text=text,
            created_by=thread.user,
            updated_by=thread.user,
        )
        # Touch the thread so ordering-by-activity + updated_at reflect the reply.
        thread.updated_at = timezone.now()
        thread.save(update_fields=["updated_at"])
        invalidate_thread_cache(thread.user_id)

    return text
