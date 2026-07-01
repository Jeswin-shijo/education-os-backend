"""I/O serializers for the assignments app.

Flavours:

* ``AssignmentSerializer`` — CRUD serializer used by the faculty/admin
  management surface (accepts FK ids + fields; also the ``POST /assignments``
  create body).
* ``StudentAssignmentSerializer`` — emits the exact ``types.ts`` ``Assignment``
  shape (camelCase) for the student list/retrieve endpoints. ``status``,
  ``submittedAt``, ``grade`` and ``attachmentName`` are *per-student*, derived
  from the current student's submission when present (passed in via serializer
  ``context["submissions"]``: a ``{assignment_id: Submission}`` map).
* ``FacultyAssignmentSerializer`` — emits ``types.ts`` ``FacultyAssignment``
  (camelCase, ``classId``/``createdOn``/``submissions`` count) for
  ``GET /faculty/assignments``.
* ``SubmitInputSerializer`` — validates the ``POST /assignments/{id}/submit``
  body (``{ fileName }``).
"""
from rest_framework import serializers

from assignments.models import Assignment, Submission


# --- CRUD serializer ---------------------------------------------------------
class AssignmentSerializer(serializers.ModelSerializer):
    """Faculty/admin CRUD serializer for Assignment."""

    subject_code = serializers.CharField(source="subject.code", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)

    class Meta:
        model = Assignment
        fields = [
            "id",
            "subject",
            "subject_code",
            "subject_name",
            "faculty_class",
            "title",
            "description",
            "due_date",
            "max_marks",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "status", "created_at", "updated_at"]

    def validate_max_marks(self, value):
        if value <= 0:
            raise serializers.ValidationError("max_marks must be positive.")
        return value


# --- App-shaped read serializers (mobile contract) ---------------------------
class StudentAssignmentSerializer(serializers.ModelSerializer):
    """Matches ``types.ts`` ``Assignment`` (student-facing, camelCase).

    Per-student fields are derived from ``context["submissions"]`` — a
    ``{assignment_id: Submission}`` map for the requesting student.
    """

    id = serializers.CharField(read_only=True)
    subjectId = serializers.CharField(source="subject_id", read_only=True)
    dueDate = serializers.DateTimeField(source="due_date", read_only=True)
    maxMarks = serializers.IntegerField(source="max_marks", read_only=True)
    status = serializers.SerializerMethodField()
    submittedAt = serializers.SerializerMethodField()
    grade = serializers.SerializerMethodField()
    attachmentName = serializers.SerializerMethodField()

    class Meta:
        model = Assignment
        fields = [
            "id",
            "subjectId",
            "title",
            "description",
            "dueDate",
            "maxMarks",
            "status",
            "submittedAt",
            "grade",
            "attachmentName",
        ]

    def _submission(self, obj):
        return (self.context.get("submissions") or {}).get(obj.id)

    def get_status(self, obj):
        sub = self._submission(obj)
        if sub is None:
            # No submission from this student: pending, unless it's past due.
            return obj.status if obj.status == Assignment.STATUS_LATE else (
                Assignment.STATUS_LATE
                if obj.due_date and obj.due_date < _now()
                else Assignment.STATUS_PENDING
            )
        if sub.grade is not None:
            return Assignment.STATUS_GRADED
        # Submitted after the due date -> late.
        if obj.due_date and sub.submitted_at and sub.submitted_at > obj.due_date:
            return Assignment.STATUS_LATE
        return Assignment.STATUS_SUBMITTED

    def get_submittedAt(self, obj):
        sub = self._submission(obj)
        return sub.submitted_at if sub else None

    def get_grade(self, obj):
        sub = self._submission(obj)
        return sub.grade if sub else None

    def get_attachmentName(self, obj):
        sub = self._submission(obj)
        return sub.file_name if sub else None


class FacultyAssignmentSerializer(serializers.ModelSerializer):
    """Matches ``types.ts`` ``FacultyAssignment`` (camelCase)."""

    id = serializers.CharField(read_only=True)
    classId = serializers.SerializerMethodField()
    dueDate = serializers.DateTimeField(source="due_date", read_only=True)
    maxMarks = serializers.IntegerField(source="max_marks", read_only=True)
    createdOn = serializers.DateTimeField(source="created_at", read_only=True)
    submissions = serializers.SerializerMethodField()

    class Meta:
        model = Assignment
        fields = [
            "id",
            "classId",
            "title",
            "description",
            "dueDate",
            "maxMarks",
            "createdOn",
            "submissions",
        ]

    def get_classId(self, obj):
        return str(obj.faculty_class_id) if obj.faculty_class_id else ""

    def get_submissions(self, obj):
        # Prefer an annotated count (set by the view to avoid N+1); else count.
        count = getattr(obj, "submission_count", None)
        if count is not None:
            return count
        return obj.submissions.count()


# --- Write input serializer --------------------------------------------------
class SubmitInputSerializer(serializers.Serializer):
    """Validates ``POST /assignments/{id}/submit`` (``{ fileName }``)."""

    fileName = serializers.CharField(max_length=512)


def _now():
    from django.utils import timezone

    return timezone.now()
