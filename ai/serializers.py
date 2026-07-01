"""I/O serializers for the ai app.

The mobile app (``types.ts`` / ``aiService.ts``) expects:

    AIMessage = { id, role, text, at }
    AIThread  = { id, feature, title, messages: AIMessage[] }

plus request bodies:

    POST /ai/:feature/respond          -> { prompt }   -> { text }
    POST /ai/threads/:feature/messages -> { text }     -> AIThread

These serializers translate between those app shapes and the model fields.
"""
from rest_framework import serializers

from ai.models import AIFeature, AIMessage, AIThread


# --- App-shaped read serializers (mobile contract) ---------------------------
class AIMessageSerializer(serializers.ModelSerializer):
    """Matches ``types.ts`` ``AIMessage``."""

    id = serializers.CharField(read_only=True)
    at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = AIMessage
        fields = ["id", "role", "text", "at"]


class AIThreadSerializer(serializers.ModelSerializer):
    """Matches ``types.ts`` ``AIThread`` (nested messages, chronological)."""

    id = serializers.CharField(read_only=True)
    messages = AIMessageSerializer(many=True, read_only=True)

    class Meta:
        model = AIThread
        fields = ["id", "feature", "title", "messages"]


# --- Request serializers -----------------------------------------------------
class RespondRequestSerializer(serializers.Serializer):
    """``POST /ai/:feature/respond`` body = ``{ prompt }``."""

    prompt = serializers.CharField(allow_blank=True, trim_whitespace=False)


class RespondResponseSerializer(serializers.Serializer):
    """``POST /ai/:feature/respond`` response = ``{ text }``."""

    text = serializers.CharField()


class SendMessageRequestSerializer(serializers.Serializer):
    """``POST /ai/threads/:feature/messages`` body = ``{ text }``."""

    text = serializers.CharField()


class FeatureField(serializers.ChoiceField):
    """Validates a path ``feature`` against :class:`AIFeature`."""

    def __init__(self, **kwargs):
        super().__init__(choices=AIFeature.choices, **kwargs)
