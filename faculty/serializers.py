"""I/O serializers for the faculty app.

Two flavours:

* CRUD serializers (``FacultyProfileSerializer``) — used by the admin management
  viewset; accept/return model fields plus FK ids.
* App-shaped serializers (``FacultyClassAppSerializer``, ``RosterStudentSerializer``,
  ``FacultyProfileMeSerializer``) — emit the exact camelCase shapes the mobile
  app expects (``types.ts``: ``FacultyClass``, ``RosterStudent`` and
  ``facultyService.FacultyProfile``) for the self-scoped read endpoints.
"""
from rest_framework import serializers

from faculty.models import FacultyClass, FacultyProfile, RosterEntry


# --- CRUD serializers --------------------------------------------------------
class FacultyProfileSerializer(serializers.ModelSerializer):
    """Admin CRUD serializer for FacultyProfile."""

    user_name = serializers.CharField(source="user.full_name", read_only=True)
    user_email = serializers.CharField(source="user.email", read_only=True)
    department_code = serializers.CharField(
        source="department.code", read_only=True
    )
    department_name = serializers.CharField(
        source="department.name", read_only=True
    )

    class Meta:
        model = FacultyProfile
        fields = [
            "id",
            "user",
            "user_name",
            "user_email",
            "department",
            "department_code",
            "department_name",
            "designation",
            "subject_codes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_subject_codes(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("subject_codes must be a list.")
        if not all(isinstance(v, str) for v in value):
            raise serializers.ValidationError(
                "subject_codes must be a list of strings."
            )
        return value


# --- App-shaped read serializers (mobile contract) ---------------------------
class FacultyClassSlotSerializer(serializers.Serializer):
    """Matches ``types.ts`` ``FacultyClassSlot``."""

    day = serializers.CharField()
    start = serializers.CharField()
    end = serializers.CharField()
    room = serializers.CharField(allow_blank=True, required=False)


class FacultyClassAppSerializer(serializers.ModelSerializer):
    """Matches ``types.ts`` ``FacultyClass`` (camelCase, denormalized subject)."""

    id = serializers.CharField(read_only=True)
    subjectId = serializers.CharField(source="subject_id", read_only=True)
    subjectCode = serializers.CharField(source="subject.code", read_only=True)
    subjectName = serializers.CharField(source="subject.name", read_only=True)
    semester = serializers.IntegerField(source="semester.number", read_only=True)
    section = serializers.CharField(source="section.name", read_only=True)
    studentCount = serializers.IntegerField(source="student_count", read_only=True)
    slots = serializers.JSONField(read_only=True)

    class Meta:
        model = FacultyClass
        fields = [
            "id",
            "subjectId",
            "subjectCode",
            "subjectName",
            "semester",
            "section",
            "studentCount",
            "color",
            "slots",
        ]


class RosterStudentSerializer(serializers.ModelSerializer):
    """Matches ``types.ts`` ``RosterStudent`` (camelCase)."""

    id = serializers.SerializerMethodField()
    rollNo = serializers.CharField(source="roll_no", read_only=True)
    name = serializers.CharField(source="student_name", read_only=True)
    avatarColor = serializers.CharField(source="avatar_color", read_only=True)

    class Meta:
        model = RosterEntry
        fields = ["id", "name", "rollNo", "avatarColor"]

    def get_id(self, obj):
        # Prefer the future students.Student ref; fall back to the entry id.
        return str(obj.student_ref or obj.id)


class FacultyProfileMeSerializer(serializers.ModelSerializer):
    """Matches ``facultyService.FacultyProfile``: faculty user + department +
    designation + the faculty's classes (app-shaped)."""

    faculty = serializers.SerializerMethodField()
    department = serializers.CharField(source="department.name", read_only=True)
    classes = FacultyClassAppSerializer(many=True, read_only=True)

    class Meta:
        model = FacultyProfile
        fields = ["faculty", "department", "designation", "classes"]

    def get_faculty(self, obj):
        u = obj.user
        return {
            "id": str(u.id),
            "name": u.full_name,
            "email": u.email,
            "role": u.role,
            "avatarColor": u.avatar_color,
        }
