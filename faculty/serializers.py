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
class DepartmentRefField(serializers.Field):
    """Department reference that accepts an id / code / name on write and
    renders the linked department's id on read.

    The raw reference is passed straight through to
    :class:`faculty.services.FacultyProfileService`, which resolves it to the
    ``academics.Department`` FK (and returns a 400 if it can't). Read output is
    the department id, matching the previous ``PrimaryKeyRelatedField`` shape so
    the admin list/detail contract is unchanged.
    """

    default_error_messages = {"blank": "department may not be blank."}

    def to_representation(self, value):
        # ``value`` is the related Department instance (select_related loaded).
        return str(value.pk) if value is not None else None

    def to_internal_value(self, data):
        if data is None:
            self.fail("blank")
        text = str(data).strip()
        if not text:
            self.fail("blank")
        return text


class FacultyProfileSerializer(serializers.ModelSerializer):
    """Admin CRUD serializer for FacultyProfile.

    Create accepts a full faculty record in one request: the ``accounts.User``
    fields (``full_name``/``name``, ``email``, ``phone``, optional ``password``)
    alongside the profile fields (``department`` as id/code/name, ``designation``,
    ``qualifications``, ``experience``, ``photo_url``, ``subject_codes``). The
    service layer creates-or-reuses the User (role=faculty) and its
    FacultyProfile. An existing ``user`` id may still be supplied instead of the
    User fields (legacy contract).
    """

    user_name = serializers.CharField(source="user.full_name", read_only=True)
    user_email = serializers.CharField(source="user.email", read_only=True)
    # Contact number lives on ``accounts.User``; read via the model ``phone``
    # property, and synced back to the user on write by the service layer.
    phone = serializers.CharField(required=False, allow_blank=True)
    department = DepartmentRefField(required=False)
    department_code = serializers.CharField(
        source="department.code", read_only=True
    )
    department_name = serializers.CharField(
        source="department.name", read_only=True
    )
    # Write-only User inputs for the combined User + FacultyProfile create. Kept
    # out of the read shape so list/detail responses are unchanged.
    full_name = serializers.CharField(
        required=False, write_only=True, allow_blank=True
    )
    name = serializers.CharField(
        required=False, write_only=True, allow_blank=True
    )
    email = serializers.EmailField(required=False, write_only=True)
    password = serializers.CharField(
        required=False, write_only=True, allow_blank=True,
        style={"input_type": "password"},
    )

    class Meta:
        model = FacultyProfile
        fields = [
            "id",
            "user",
            "user_name",
            "user_email",
            "full_name",
            "name",
            "email",
            "password",
            "phone",
            "department",
            "department_code",
            "department_name",
            "designation",
            "qualifications",
            "experience",
            "photo_url",
            "subject_codes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
        # ``user`` is optional: on create the service builds it from the User
        # fields when no id is supplied.
        extra_kwargs = {"user": {"required": False}}

    def validate_subject_codes(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("subject_codes must be a list.")
        if not all(isinstance(v, str) for v in value):
            raise serializers.ValidationError(
                "subject_codes must be a list of strings."
            )
        return value

    def validate(self, attrs):
        # On create we need either an existing user id or an email to build the
        # faculty User from. (Update may touch profile fields only.)
        if self.instance is None and not attrs.get("user") and not attrs.get("email"):
            raise serializers.ValidationError(
                {"email": "Provide an email (or an existing user id) to create faculty."}
            )
        return attrs


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
            "phone": u.phone,
            "avatarColor": u.avatar_color,
        }


# --- Allocations (HOD): a subject↔faculty view over FacultyClass -------------
class SubjectAllocationSerializer(serializers.ModelSerializer):
    """Maps a :class:`FacultyClass` to ``types.ts`` ``SubjectAllocation``.

    ``facultyId`` is the :class:`FacultyProfile` id — the SAME identifier the
    HOD analytics endpoints use (``GET /hod/faculty`` returns
    ``facultyId = str(profile.id)``; see ``analytics/services.py``). Keeping
    them identical lets the mobile HOD screens cross-reference an allocation's
    faculty against the faculty directory and pass it straight back to reassign.
    """

    id = serializers.CharField(read_only=True)
    subjectId = serializers.CharField(source="subject_id", read_only=True)
    subjectCode = serializers.CharField(source="subject.code", read_only=True)
    subjectName = serializers.CharField(source="subject.name", read_only=True)
    semester = serializers.IntegerField(source="semester.number", read_only=True)
    section = serializers.CharField(source="section.name", read_only=True)
    facultyId = serializers.CharField(source="faculty_id", read_only=True)
    facultyName = serializers.CharField(
        source="faculty.user.full_name", read_only=True
    )

    class Meta:
        model = FacultyClass
        fields = [
            "id",
            "subjectId",
            "subjectCode",
            "subjectName",
            "semester",
            "section",
            "facultyId",
            "facultyName",
        ]


class ReassignAllocationSerializer(serializers.Serializer):
    """Validates ``POST /allocations/{id}/reassign`` (``{ facultyId, facultyName }``).

    ``facultyId`` is the target :class:`FacultyProfile` id (as surfaced by
    ``GET /hod/faculty`` / ``GET /allocations``); an accounts user id is also
    accepted as a fallback. ``facultyName`` is advisory — the name is re-derived
    from the resolved profile.
    """

    facultyId = serializers.CharField()
    facultyName = serializers.CharField(required=False, allow_blank=True)
