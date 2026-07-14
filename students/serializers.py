"""I/O serializers for the students app.

Two flavours:

* CRUD serializers (``*Serializer``) — used by the admin/staff management
  viewset. They accept/return model fields plus FK ids and nest the child
  collections (addresses/guardians/medical/documents) read-only.
* App-shaped serializer (``StudentAppSerializer``) — emits the exact camelCase
  shape the mobile app expects (``types.ts`` ``Student``) for ``GET/PUT
  /students/me``. It flattens the academic FKs to the display strings/numbers the
  app uses (``program``/``branch``/``semester``/``section``/``year``).
"""
from rest_framework import serializers

from students.models import (
    Guardian,
    Medical,
    Student,
    StudentAddress,
    StudentDocument,
)


# --- Child serializers -------------------------------------------------------
class StudentAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentAddress
        fields = [
            "id",
            "student",
            "line1",
            "line2",
            "city",
            "state",
            "pincode",
            "country",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class GuardianSerializer(serializers.ModelSerializer):
    class Meta:
        model = Guardian
        fields = [
            "id",
            "student",
            "name",
            "relation",
            "phone",
            "email",
            "is_primary",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class MedicalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Medical
        fields = [
            "id",
            "student",
            "blood_group",
            "allergies",
            "conditions",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class StudentDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentDocument
        fields = [
            "id",
            "student",
            "title",
            "kind",
            "file",
            "url",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


# --- CRUD serializer (admin/staff console) -----------------------------------
class StudentSerializer(serializers.ModelSerializer):
    """Full student record with FK ids and nested child collections (read)."""

    department_code = serializers.CharField(
        source="department.code", read_only=True
    )
    program_code = serializers.CharField(source="program.code", read_only=True)
    semester_number = serializers.IntegerField(
        source="semester.number", read_only=True
    )
    section_name = serializers.CharField(source="section.name", read_only=True)

    addresses = StudentAddressSerializer(many=True, read_only=True)
    guardians = GuardianSerializer(many=True, read_only=True)
    documents = StudentDocumentSerializer(many=True, read_only=True)
    medical = MedicalSerializer(read_only=True)
    # Whether the student's login account is enabled. Drives the roster's
    # active/inactive state (a student with no linked account counts as active).
    active = serializers.SerializerMethodField()

    def get_active(self, obj) -> bool:
        return obj.user.is_active if obj.user_id else True

    class Meta:
        model = Student
        fields = [
            "id",
            "user",
            "active",
            "roll_no",
            "admission_no",
            "program",
            "program_code",
            "department",
            "department_code",
            "semester",
            "semester_number",
            "section",
            "section_name",
            "first_name",
            "last_name",
            "full_name",
            "gender",
            "dob",
            "phone",
            "email",
            "cgpa",
            "blood_group",
            "mentor_name",
            "address",
            "avatar_color",
            "status",
            "addresses",
            "guardians",
            "documents",
            "medical",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


# --- App-shaped serializer (mobile contract: types.ts Student) ---------------
class StudentAppSerializer(serializers.ModelSerializer):
    """Matches ``types.ts`` ``Student`` (camelCase, flattened academic fields).

    Read maps the FKs to the display strings/numbers the app expects; write
    (``PUT /students/me``) only touches the profile fields a student may edit —
    the academic structure and roll/admission numbers are staff-managed and stay
    read-only here.
    """

    id = serializers.CharField(read_only=True)
    name = serializers.CharField(source="full_name")
    rollNo = serializers.CharField(source="roll_no", read_only=True)
    admissionNo = serializers.CharField(source="admission_no", read_only=True)
    program = serializers.SerializerMethodField()
    branch = serializers.SerializerMethodField()
    semester = serializers.SerializerMethodField()
    section = serializers.SerializerMethodField()
    year = serializers.SerializerMethodField()
    cgpa = serializers.FloatField(read_only=True)
    avatarColor = serializers.CharField(source="avatar_color", required=False)
    profilePic = serializers.ImageField(source="profile_pic", read_only=True, allow_null=True)
    mentorName = serializers.CharField(source="mentor_name", required=False)
    bloodGroup = serializers.CharField(source="blood_group", required=False)

    class Meta:
        model = Student
        fields = [
            "id",
            "name",
            "rollNo",
            "admissionNo",
            "program",
            "branch",
            "semester",
            "section",
            "year",
            "cgpa",
            "avatarColor",
            "profilePic",
            "email",
            "phone",
            "mentorName",
            "bloodGroup",
            "address",
        ]

    def get_program(self, obj) -> str:
        return obj.program.name if obj.program_id else ""

    def get_branch(self, obj) -> str:
        return obj.department.name if obj.department_id else ""

    def get_semester(self, obj) -> int:
        return obj.semester.number if obj.semester_id else 0

    def get_section(self, obj) -> str:
        return obj.section.name if obj.section_id else ""

    def get_year(self, obj) -> int:
        # Derive academic year from the semester number (2 semesters per year).
        num = obj.semester.number if obj.semester_id else 0
        return (num + 1) // 2 if num else 0


# --- Spec (mobile API contract) profile serializer ---------------------------
class StudentProfileSpecSerializer(serializers.ModelSerializer):
    """``GET /api/v1/students/by-user/{user_id}`` — snake_case profile.

    ``{ name, email, phone, blood_group, mentor, admission_no, roll_no,
    department, program, semester, section }`` (academic FKs flattened to display
    values).
    """

    name = serializers.CharField(source="full_name", read_only=True)
    mentor = serializers.CharField(source="mentor_name", read_only=True)
    department = serializers.SerializerMethodField()
    program = serializers.SerializerMethodField()
    semester = serializers.SerializerMethodField()
    section = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = [
            "name",
            "email",
            "phone",
            "blood_group",
            "mentor",
            "admission_no",
            "roll_no",
            "address",
            "department",
            "program",
            "semester",
            "section",
        ]

    def get_department(self, obj) -> str:
        return obj.department.name if obj.department_id else ""

    def get_program(self, obj) -> str:
        return obj.program.name if obj.program_id else ""

    def get_semester(self, obj) -> int:
        return obj.semester.number if obj.semester_id else 0

    def get_section(self, obj) -> str:
        return obj.section.name if obj.section_id else ""
