"""Business-logic layer for the ai app.

:class:`AIThreadService` extends :class:`core.services.BaseService` so writes
auto-stamp ``created_by``/``updated_by``, emit :class:`~core.models.AuditLog`
rows, and bust the per-user cached thread views. It owns the two mutating flows
the mobile ``aiService`` exercises:

- :meth:`get_or_create_thread` — find-or-create the user's single thread for a
  feature (mirrors ``aiService.getThread``).
- :meth:`send_message` — append the user's turn, generate the assistant reply
  through the pluggable LLM (:mod:`ai.llm`), append it, and return the updated
  thread (mirrors ``aiService.send``). The whole exchange is atomic + audited.

Cached reads live under the ``ai`` prefix, scoped per user; any write busts that
user's threads. TTL follows notifications-style short freshness (60s) since a
conversation changes often.
"""
from __future__ import annotations

from django.db import transaction

from core.cache import TTL_NOTIFICATIONS, cache_key, invalidate
from core.models import AuditLog
from core.services import BaseService

from ai import llm
from ai.models import FEATURE_TITLES, AIFeature, AIMessage, AIThread
from ai.repositories import AIThreadRepository

# Cache-key prefix owned by this app; short TTL (conversations move fast).
AI_PREFIX = "ai"
TTL_AI = TTL_NOTIFICATIONS


def user_threads_key(user_id) -> str:
    return cache_key(AI_PREFIX, "threads", user_id)


def user_feature_key(user_id, feature) -> str:
    return cache_key(AI_PREFIX, "thread", user_id, feature)


def invalidate_thread_cache(user_id) -> None:
    """Bust all cached thread views for a single user."""
    keys = [user_threads_key(user_id)]
    for feature, _label in AIFeature.choices:
        keys.append(user_feature_key(user_id, feature))
    invalidate(*keys)


class AIThreadService(BaseService):
    model = AIThread
    repository_class = AIThreadRepository
    entity_name = "AIThread"

    def invalidate_cache(self, instance=None) -> None:
        user_id = getattr(instance, "user_id", None) if instance else None
        if user_id is None:
            user_id = getattr(self.actor, "id", None)
        if user_id is not None:
            invalidate_thread_cache(user_id)

    # -- thread lifecycle ------------------------------------------------
    def get_or_create_thread(self, user, feature: str) -> AIThread:
        """Return the user's active thread for ``feature``, creating it if absent."""
        existing = self.repository.get_for_user(user, feature)
        if existing is not None:
            return existing
        title = FEATURE_TITLES.get(feature) or dict(AIFeature.choices).get(
            feature, "AI Assistant"
        )
        # Route through BaseService.create for stamping + audit + invalidation.
        return self.create(user=user, feature=feature, title=title)

    def _audit_message(self, message: AIMessage) -> None:
        """Write an AuditLog row for a single AIMessage (correct entity name)."""
        AuditLog.objects.create(
            actor=self._actor_or_none(),
            action=AuditLog.ACTION_CREATE,
            entity="AIMessage",
            entity_id=str(message.pk),
            changes={"thread": str(message.thread_id), "role": message.role},
            ip=self.ip,
        )

    # -- message send ----------------------------------------------------
    @transaction.atomic
    def send_message(self, user, feature: str, text: str) -> AIThread:
        """Append the user's turn + the assistant reply; return the thread.

        Mirrors ``aiService.send``: persists the user message, generates the
        assistant reply via the pluggable LLM (canned fallback with no key),
        persists it, touches the thread, audits both turns, and invalidates the
        user's cached thread views.
        """
        thread = self.get_or_create_thread(user, feature)

        history = [
            {"role": m.role, "text": m.text}
            for m in thread.messages.all().order_by("at")
        ]

        user_msg = AIMessage.objects.create(
            thread=thread,
            role=AIMessage.ROLE_USER,
            text=text,
            created_by=self._actor_or_none(),
            updated_by=self._actor_or_none(),
        )
        self._audit_message(user_msg)

        reply_text = llm.generate(feature, text, history=history)

        assistant_msg = AIMessage.objects.create(
            thread=thread,
            role=AIMessage.ROLE_ASSISTANT,
            text=reply_text,
            created_by=self._actor_or_none(),
            updated_by=self._actor_or_none(),
        )
        self._audit_message(assistant_msg)

        # Touch the thread so it sorts to the top by recent activity.
        thread.save(update_fields=["updated_at"])
        self.invalidate_cache(thread)
        # Refresh so the returned instance carries both new messages.
        return self.repository.get(thread.pk)

    # -- respond (stateless) ---------------------------------------------
    def respond(self, feature: str, prompt: str) -> str:
        """Compute a one-off reply (no persistence). Mirrors ``aiService.respond``."""
        return llm.generate(feature, prompt)
