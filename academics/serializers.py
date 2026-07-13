"""I/O serializers for the academics app.

Two flavours:

* CRUD serializers (``*Serializer``) — used by the admin/HOD management viewsets.
  They accept/return the model fields plus FK ids.
* App-shaped serializers (``SubjectAppSerializer`` / ``ClassSessionAppSerializer``)
  — emit the exact camelCase shapes the mobile app expects (``types.ts``:
  ``Subject`` and ``ClassSession``) for the timetable / subject-detail endpoints.
"""
from rest_framework import serializers

from accounts.models import User
from academics.models import (
    ClassSession,
    Department,
    Program,
    Section,
    Semester,
    Subject,
)
from core.permissions import Role
from faculty.models import FacultyProfile


# --- CRUD serializers --------------------------------------------------------
class DepartmentSerializer(serializers.ModelSerializer):
    hod_name = serializers.CharField(source="hod.full_name", read_only=True, default=None)

    class Meta:
        model = Department
        fields = ["id", "code", "name", "hod", "hod_name", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class ProgramSerializer(serializers.ModelSerializer):
    department_code = serializers.CharField(
        source="department.code", read_only=True
    )
    department_name = serializers.CharField(
        source="department.name", read_only=True
    )

    class Meta:
        model = Program
        fields = [
            "id",
            "code",
            "name",
            "department",
            "department_code",
            "department_name",
            "duration_years",
            "intake",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class SemesterSerializer(serializers.ModelSerializer):
    program_code = serializers.CharField(source="program.code", read_only=True)

    class Meta:
        model = Semester
        fields = ["id", "program", "program_code", "number", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class SectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Section
        fields = ["id", "semester", "name", "shift", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class SubjectSerializer(serializers.ModelSerializer):
    department_code = serializers.CharField(
        source="department.code", read_only=True
    )
    program_name = serializers.CharField(
        source="program.name", read_only=True, default=None
    )
    semester_number = serializers.IntegerField(
        source="semester.number", read_only=True, default=None
    )
    program_code = serializers.CharField(
        source="program.code", read_only=True, default=None
    )
    faculty_email = serializers.EmailField(
        source="faculty.email", read_only=True, default=None
    )
    # Multi-faculty relation. Writable list of faculty *User* ids — matching the
    # ``faculty-candidates`` endpoint and the legacy single-faculty ``faculty`` FK
    # (everything else in the system identifies faculty by user id). The write is
    # resolved to ``FacultyProfile`` rows by ``SubjectService``, which also mirrors
    # the first selection onto the legacy ``faculty``/``faculty_name`` fields.
    faculties = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=User.objects.filter(role__in=[Role.FACULTY, Role.HOD]),
        required=False,
    )
    # Derived read-only display names for the assigned faculties.
    faculty_names = serializers.SerializerMethodField()

    class Meta:
        model = Subject
        fields = [
            "id",
            "code",
            "name",
            "credits",
            "department",
            "department_code",
            "program",
            "program_code",
            "program_name",
            "semester",
            "semester_number",
            "academic_session",
            "faculty",
            "faculty_name",
            "faculty_email",
            "faculties",
            "faculty_names",
            "color",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "faculty_name", "created_at", "updated_at"]
        # These are nullable/defaulted on the model but required on write. Set
        # via extra_kwargs (not by redeclaring the fields) so DRF keeps the
        # model-derived validators — notably the UniqueValidator on ``code`` and
        # the non-negative bound on ``credits``.
        extra_kwargs = {
            "credits": {"required": True},
            "program": {"required": True, "allow_null": False},
            "semester": {"required": True, "allow_null": False},
            "academic_session": {"required": True, "allow_blank": False},
        }

    def get_faculty_names(self, obj) -> list[str]:
        return [
            fp.user.full_name
            for fp in obj.faculties.all()
            if fp.user_id is not None
        ]


class ClassSessionSerializer(serializers.ModelSerializer):
    faculty_name = serializers.CharField(source="faculty.full_name", read_only=True, default=None)
    # Computed session length in minutes (end − start on the "HH:MM" strings).
    duration_mins = serializers.SerializerMethodField()

    class Meta:
        model = ClassSession
        fields = [
            "id",
            "subject",
            "section",
            "faculty",
            "faculty_name",
            "day",
            "start",
            "end",
            "duration_mins",
            "room",
            "type",
            "academic_session",
            "shift",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "duration_mins", "created_at", "updated_at"]

    def get_duration_mins(self, obj):
        """Minutes between ``start`` and ``end`` (both "HH:MM"); None if unparseable."""
        start = self._to_minutes(obj.start)
        end = self._to_minutes(obj.end)
        if start is None or end is None:
            return None
        return end - start

    @staticmethod
    def _to_minutes(value):
        try:
            hours, minutes = str(value).strip().split(":")[:2]
            return int(hours) * 60 + int(minutes)
        except (ValueError, AttributeError):
            return None


# --- App-shaped read serializers (mobile contract) ---------------------------
class SubjectAppSerializer(serializers.ModelSerializer):
    """Matches ``types.ts`` ``Subject`` shape (camelCase, ``faculty`` string)."""

    id = serializers.CharField(read_only=True)
    faculty = serializers.CharField(source="faculty_name", read_only=True)

    class Meta:
        model = Subject
        fields = ["id", "code", "name", "credits", "faculty", "color"]


class ClassSessionAppSerializer(serializers.ModelSerializer):
    """Matches ``types.ts`` ``ClassSession`` shape (camelCase, ``subjectId``)."""

    id = serializers.CharField(read_only=True)
    subjectId = serializers.CharField(source="subject_id", read_only=True)

    class Meta:
        model = ClassSession
        fields = ["id", "subjectId", "day", "start", "end", "room", "type"]


# --- Mobile API contract v1 (spec-exact, snake_case) -------------------------
class AcademicRecordSerializer(serializers.Serializer):
    """Spec-exact shape for ``GET /api/v1/academics/{user_id}``.

    ``API_CONTRACT_V1`` §Academics:
    ``{ degree, department, semester, section, mentor, cgpa }``.
    """

    degree = serializers.CharField(allow_blank=True)
    department = serializers.CharField(allow_blank=True)
    semester = serializers.IntegerField()
    section = serializers.CharField(allow_blank=True)
    mentor = serializers.CharField(allow_blank=True)
    cgpa = serializers.FloatField()


class GpaTrendPointSerializer(serializers.Serializer):
    """One ``{ semester, gpa }`` point of the academic-progress GPA trend."""

    semester = serializers.CharField()
    gpa = serializers.FloatField()


class AcademicProgressSerializer(serializers.Serializer):
    """Spec-exact shape for ``GET /api/v1/progress/{user_id}``.

    ``API_CONTRACT_V1`` §Academic Progress:
    ``{ gpa_trend:[{semester,gpa}], semester_gpa, overall_cgpa, ai_insights:[...] }``.
    """

    gpa_trend = GpaTrendPointSerializer(many=True)
    semester_gpa = serializers.FloatField()
    overall_cgpa = serializers.FloatField()
    ai_insights = serializers.ListField(child=serializers.DictField())
