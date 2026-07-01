"""I/O serializers for the quizzes app.

The mobile app (``types.ts``) expects camelCase shapes:

    QuizQuestion = { id, q, options, answerIndex }
    Quiz         = { id, subjectId, title, questions }

and ``quizService.create`` posts ``CreateQuizInput = { subjectId, title,
questions }``. These serializers translate between those app shapes and the
snake_cased model fields (``text``/``answer_index``/``subject``).
"""
from rest_framework import serializers

from academics.models import Subject
from quizzes.models import Quiz, QuizQuestion


# --- App-shaped read serializers (mobile contract) ---------------------------
class QuizQuestionSerializer(serializers.ModelSerializer):
    """Matches ``types.ts`` ``QuizQuestion`` (camelCase)."""

    id = serializers.CharField(read_only=True)
    q = serializers.CharField(source="text", read_only=True)
    options = serializers.JSONField(read_only=True)
    answerIndex = serializers.IntegerField(source="answer_index", read_only=True)

    class Meta:
        model = QuizQuestion
        fields = ["id", "q", "options", "answerIndex"]


class QuizSerializer(serializers.ModelSerializer):
    """Matches ``types.ts`` ``Quiz`` (camelCase, nested questions)."""

    id = serializers.CharField(read_only=True)
    subjectId = serializers.CharField(source="subject_id", read_only=True)
    questions = QuizQuestionSerializer(many=True, read_only=True)

    class Meta:
        model = Quiz
        fields = ["id", "subjectId", "title", "questions"]


# --- Write serializer (faculty POST /quizzes) --------------------------------
class QuizQuestionWriteSerializer(serializers.Serializer):
    """One nested question in a ``CreateQuizInput``.

    Accepts the app's camelCase ``q``/``answerIndex`` and maps them to the model
    field names ``text``/``answer_index`` in ``validated_data``.
    """

    q = serializers.CharField(source="text")
    options = serializers.ListField(child=serializers.CharField(), min_length=2)
    answerIndex = serializers.IntegerField(source="answer_index", min_value=0)

    def validate(self, attrs):
        options = attrs.get("options", [])
        answer_index = attrs.get("answer_index", 0)
        if not (0 <= answer_index < len(options)):
            raise serializers.ValidationError(
                {"answerIndex": "answerIndex is out of range for options."}
            )
        return attrs


class QuizCreateSerializer(serializers.ModelSerializer):
    """Validates ``CreateQuizInput`` = ``{ subjectId, title, questions }``.

    On write, ``validated_data`` carries ``subject`` (resolved FK), ``title`` and
    a list of question dicts under ``questions`` — exactly the kwargs
    :meth:`quizzes.services.QuizService.create` expects. On read (the create
    response) it re-serializes through :class:`QuizSerializer`.
    """

    subjectId = serializers.PrimaryKeyRelatedField(
        source="subject", queryset=Subject.objects.all()
    )
    questions = QuizQuestionWriteSerializer(many=True, write_only=True)

    class Meta:
        model = Quiz
        fields = ["id", "subjectId", "title", "questions"]
        read_only_fields = ["id"]

    def validate_questions(self, value):
        if not value:
            raise serializers.ValidationError(
                "A quiz must have at least one question."
            )
        return value

    def to_representation(self, instance):
        return QuizSerializer(instance, context=self.context).data
