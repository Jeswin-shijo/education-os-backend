"""I/O serializers for the academics app.

Two flavours:

* CRUD serializers (``*Serializer``) — used by the admin/HOD management viewsets.
  They accept/return the model fields plus FK ids.
* App-shaped serializers (``SubjectAppSerializer`` / ``ClassSessionAppSerializer``)
  — emit the exact camelCase shapes the mobile app expects (``types.ts``:
  ``Subject`` and ``ClassSession``) for the timetable / subject-detail endpoints.
"""
from rest_framework import serializers

from academics.models import (
    ClassSession,
    Department,
    Program,
    Section,
    Semester,
    Subject,
)


# --- CRUD serializers --------------------------------------------------------
class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ["id", "code", "name", "created_at", "updated_at"]
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
        fields = ["id", "semester", "name", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class SubjectSerializer(serializers.ModelSerializer):
    department_code = serializers.CharField(
        source="department.code", read_only=True
    )

    class Meta:
        model = Subject
        fields = [
            "id",
            "code",
            "name",
            "credits",
            "department",
            "department_code",
            "faculty_name",
            "color",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class ClassSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClassSession
        fields = [
            "id",
            "subject",
            "section",
            "day",
            "start",
            "end",
            "room",
            "type",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


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
