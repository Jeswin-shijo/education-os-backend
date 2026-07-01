"""I/O serializers for the exams app.

Two flavours:

* CRUD serializers (``ExamSerializer``, ``ExamResultSerializer``) — admin/faculty
  management surface; accept/return model fields plus FK ids.
* App-shaped serializers (``ExamAppSerializer``, ``ExamResultAppSerializer``,
  ``MarksSheetAppSerializer``) — emit the exact camelCase shapes ``types.ts``
  expects (``Exam``, ``ExamResult``, ``MarksSheet``/``MarkEntry``) for the mobile
  read endpoints.
* Input serializer (``SaveSheetInputSerializer``) — validates the faculty
  ``POST /marks`` body (``facultyMarksService.SaveSheetInput``).
"""
from rest_framework import serializers

from exams.models import Exam, ExamResult, MarkEntry, MarksSheet


# --- CRUD serializers --------------------------------------------------------
class ExamSerializer(serializers.ModelSerializer):
    """Admin/faculty CRUD serializer for :class:`Exam`."""

    subject_code = serializers.CharField(source="subject.code", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)

    class Meta:
        model = Exam
        fields = [
            "id",
            "subject",
            "subject_code",
            "subject_name",
            "name",
            "date",
            "time",
            "room",
            "duration_mins",
            "type",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class ExamResultSerializer(serializers.ModelSerializer):
    """Admin/faculty CRUD serializer for :class:`ExamResult`."""

    class Meta:
        model = ExamResult
        fields = [
            "id",
            "student",
            "subject",
            "exam_ref",
            "exam",
            "marks",
            "max_marks",
            "grade",
            "grade_point",
            "credits",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


# --- App-shaped read serializers (mobile contract) ---------------------------
class ExamAppSerializer(serializers.ModelSerializer):
    """Matches ``types.ts`` ``Exam`` (camelCase)."""

    id = serializers.CharField(read_only=True)
    subjectId = serializers.CharField(source="subject_id", read_only=True)
    durationMins = serializers.IntegerField(source="duration_mins", read_only=True)

    class Meta:
        model = Exam
        fields = [
            "id",
            "subjectId",
            "name",
            "date",
            "time",
            "room",
            "durationMins",
            "type",
        ]


class ExamResultAppSerializer(serializers.ModelSerializer):
    """Matches ``types.ts`` ``ExamResult`` (camelCase, denormalized subject)."""

    id = serializers.CharField(read_only=True)
    subjectId = serializers.CharField(source="subject_id", read_only=True)
    subjectName = serializers.CharField(source="subject.name", read_only=True)
    maxMarks = serializers.DecimalField(
        source="max_marks", max_digits=6, decimal_places=2, read_only=True
    )
    gradePoint = serializers.DecimalField(
        source="grade_point", max_digits=4, decimal_places=2, read_only=True
    )

    class Meta:
        model = ExamResult
        fields = [
            "id",
            "subjectId",
            "subjectName",
            "exam",
            "marks",
            "maxMarks",
            "grade",
            "gradePoint",
            "credits",
        ]


class MarkEntryAppSerializer(serializers.ModelSerializer):
    """Matches ``types.ts`` ``MarkEntry`` (camelCase)."""

    studentId = serializers.CharField(source="student_id", read_only=True)

    class Meta:
        model = MarkEntry
        fields = ["studentId", "marks"]


class MarksSheetAppSerializer(serializers.ModelSerializer):
    """Matches ``types.ts`` ``MarksSheet`` (camelCase, nested entries)."""

    id = serializers.CharField(read_only=True)
    classId = serializers.CharField(source="faculty_class_id", read_only=True)
    maxMarks = serializers.DecimalField(
        source="max_marks", max_digits=6, decimal_places=2, read_only=True
    )
    enteredOn = serializers.DateTimeField(source="entered_on", read_only=True)
    entries = MarkEntryAppSerializer(many=True, read_only=True)

    class Meta:
        model = MarksSheet
        fields = ["id", "classId", "exam", "maxMarks", "enteredOn", "entries"]


# --- Input serializers (mobile write contract) -------------------------------
class MarkEntryInputSerializer(serializers.Serializer):
    """One ``{studentId, marks}`` entry in a ``SaveSheetInput``."""

    studentId = serializers.CharField()
    marks = serializers.DecimalField(max_digits=6, decimal_places=2)


class SaveSheetInputSerializer(serializers.Serializer):
    """Matches ``facultyMarksService.SaveSheetInput`` for ``POST /marks``."""

    classId = serializers.CharField()
    exam = serializers.CharField(max_length=128)
    maxMarks = serializers.DecimalField(max_digits=6, decimal_places=2)
    entries = MarkEntryInputSerializer(many=True)

    def validate_entries(self, value):
        if not value:
            raise serializers.ValidationError("At least one mark entry is required.")
        return value
