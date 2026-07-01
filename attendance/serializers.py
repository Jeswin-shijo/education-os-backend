"""I/O serializers for the attendance app.

Two flavours:

* CRUD serializer (``AttendanceRecordSerializer``) — the admin management viewset.
* App-shaped serializers — emit the exact camelCase shapes the mobile app expects
  (``types.ts``: ``AttendanceRecord``, ``AttendanceSummary``, ``AttendanceSession``
  with ``entries: ClassAttendanceEntry[]``) for the self-scoped + faculty reads,
  plus a ``SaveSessionSerializer`` validating the faculty save-session body.
"""
from rest_framework import serializers

from attendance.models import (
    AttendanceEntry,
    AttendanceRecord,
    AttendanceSession,
    AttendanceStatus,
)


# --- CRUD serializer ---------------------------------------------------------
class AttendanceRecordSerializer(serializers.ModelSerializer):
    """Admin CRUD serializer for AttendanceRecord."""

    subject_code = serializers.CharField(source="subject.code", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)

    class Meta:
        model = AttendanceRecord
        fields = [
            "id",
            "student",
            "subject",
            "subject_code",
            "subject_name",
            "date",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


# --- App-shaped read serializers (mobile contract) ---------------------------
class AttendanceRecordAppSerializer(serializers.ModelSerializer):
    """Matches ``types.ts`` ``AttendanceRecord`` (camelCase)."""

    id = serializers.CharField(read_only=True)
    subjectId = serializers.CharField(source="subject_id", read_only=True)
    date = serializers.DateField(read_only=True)

    class Meta:
        model = AttendanceRecord
        fields = ["id", "subjectId", "date", "status"]


class AttendanceSummarySerializer(serializers.Serializer):
    """Matches ``types.ts`` ``AttendanceSummary`` (per-subject rollup)."""

    subjectId = serializers.CharField()
    subjectName = serializers.CharField()
    attended = serializers.IntegerField()
    total = serializers.IntegerField()
    percent = serializers.IntegerField()


class ClassAttendanceEntrySerializer(serializers.Serializer):
    """Matches ``types.ts`` ``ClassAttendanceEntry`` (``{studentId, status}``)."""

    studentId = serializers.CharField()
    status = serializers.ChoiceField(choices=AttendanceStatus.CHOICES)


class AttendanceSessionAppSerializer(serializers.ModelSerializer):
    """Matches ``types.ts`` ``AttendanceSession`` (camelCase + entries)."""

    id = serializers.CharField(read_only=True)
    classId = serializers.CharField(source="faculty_class_id", read_only=True)
    date = serializers.DateField(read_only=True)
    entries = serializers.SerializerMethodField()

    class Meta:
        model = AttendanceSession
        fields = ["id", "classId", "date", "entries"]

    def get_entries(self, obj):
        return [
            {
                "studentId": str(e.student_ref or e.id),
                "status": e.status,
            }
            for e in obj.entries.all()
        ]


# --- Write serializer (faculty save-session) ---------------------------------
class SaveSessionSerializer(serializers.Serializer):
    """Validates the ``POST /attendance`` body (``facultyAttendanceService
    .SaveSessionInput``): ``{ classId, date, entries: ClassAttendanceEntry[] }``.
    """

    classId = serializers.CharField()
    date = serializers.DateField()
    entries = ClassAttendanceEntrySerializer(many=True)

    def validate_entries(self, value):
        if not value:
            raise serializers.ValidationError("entries must not be empty.")
        return value
