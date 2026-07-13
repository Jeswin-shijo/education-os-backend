"""Accounts serializers: request/response shaping for the auth endpoints.

The read/``User`` serializer emits the shape the mobile app expects
(``name``, ``avatarColor`` camelCase) so ``docs/BACKEND_MIGRATION.md`` stays
satisfied inside the envelope's ``data``.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from accounts.repositories import UserRepository
from core.permissions import Role

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """Public user representation matching the mobile app's ``User`` type."""

    name = serializers.CharField(source="full_name", read_only=True)
    avatarColor = serializers.CharField(source="avatar_color", read_only=True)
    profilePic = serializers.ImageField(source="profile_pic", read_only=True, allow_null=True)

    class Meta:
        model = User
        fields = ["id", "name", "email", "role", "avatarColor", "profilePic", "phone", "is_active"]
        read_only_fields = fields


class MeSerializer(UserSerializer):
    """Current-user representation (adds staff flags)."""

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ["is_staff"]
        read_only_fields = fields


class LoginSerializer(serializers.Serializer):
    """Login accepting any one of ``username`` / ``email`` / ``phone`` plus
    ``password`` (per the mobile contract). The resolved value is exposed as
    ``credential`` in ``validated_data``."""

    username = serializers.CharField(required=False, allow_blank=True)
    email = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate(self, attrs):
        credential = (
            attrs.get("email") or attrs.get("username") or attrs.get("phone") or ""
        ).strip()
        if not credential:
            raise serializers.ValidationError(
                "Provide one of username, email, or phone."
            )
        attrs["credential"] = credential
        return attrs


class RefreshSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, style={"input_type": "password"})
    new_password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate_new_password(self, value):
        validate_password(value)
        return value

    def validate(self, attrs):
        if attrs["current_password"] == attrs["new_password"]:
            raise serializers.ValidationError(
                {"new_password": "New password must differ from the current one."}
            )
        return attrs


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(max_length=6, min_length=6)
    new_password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate_new_password(self, value):
        validate_password(value)
        return value


class RegisterSerializer(serializers.Serializer):
    """Admin-only user creation.

    When ``role`` is ``student``, optional student profile fields (``roll_no``,
    ``admission_no``, ``department``, ``program``, ``semester``, ``section``,
    ``gender``, ``dob``, ``blood_group``, ``mentor_name``) may be provided.
    The backend will auto-create the linked :class:`~students.models.Student`
    profile in a single step — no separate call required.
    """

    email = serializers.EmailField()
    full_name = serializers.CharField(max_length=255)
    role = serializers.ChoiceField(choices=Role.CHOICES)
    password = serializers.CharField(
        write_only=True, style={"input_type": "password"}, required=False, allow_blank=True
    )
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    avatar_color = serializers.CharField(max_length=9, required=False, allow_blank=True, default="")
    profile_pic = serializers.ImageField(required=False, allow_null=True, default=None)

    # --- Optional student profile fields (used only when role == "student") ---
    roll_no = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    admission_no = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    department = serializers.UUIDField(required=False, allow_null=True, default=None)
    program = serializers.UUIDField(required=False, allow_null=True, default=None)
    semester = serializers.UUIDField(required=False, allow_null=True, default=None)
    section = serializers.UUIDField(required=False, allow_null=True, default=None)
    gender = serializers.CharField(max_length=16, required=False, allow_blank=True, default="")
    dob = serializers.DateField(required=False, allow_null=True, default=None)
    blood_group = serializers.CharField(max_length=8, required=False, allow_blank=True, default="")
    mentor_name = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")

    # --- Optional faculty profile fields (used only when role == "faculty") ---
    designation = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")

    def validate_email(self, value):
        if UserRepository().email_exists(value):
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_password(self, value):
        if value:
            validate_password(value)
        return value

    def validate(self, attrs):
        role = attrs.get("role")
        if role == Role.STUDENT:
            roll_no = attrs.get("roll_no", "")
            if roll_no:
                from students.models import Student
                if Student.objects.filter(roll_no=roll_no).exists():
                    raise serializers.ValidationError(
                        {"roll_no": "A student with this roll number already exists."}
                    )
        return attrs


class SwitchRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=Role.CHOICES)


class RolesResponseSerializer(serializers.Serializer):
    """Documents ``GET /auth/roles/{user_id}`` -> ``data: { roles: [...] }``."""

    roles = serializers.ListField(child=serializers.CharField(), read_only=True)


class SwitchRoleResponseSerializer(serializers.Serializer):
    """Documents ``POST /auth/switch-role`` -> ``data: { access_token, active_role }``."""

    access_token = serializers.CharField(read_only=True)
    active_role = serializers.CharField(read_only=True)


class TokenResponseSerializer(serializers.Serializer):
    """Documents the login/refresh response body (inside the envelope ``data``).

    Emits the spec-exact ``access_token`` / ``refresh_token`` plus the legacy
    ``access`` / ``token`` / ``refresh`` aliases for back-compat."""

    user = UserSerializer(read_only=True)
    active_role = serializers.CharField(read_only=True)
    access_token = serializers.CharField(read_only=True)
    refresh_token = serializers.CharField(read_only=True)
    access = serializers.CharField(read_only=True)
    token = serializers.CharField(read_only=True, help_text="Alias of access for the mobile client.")
    refresh = serializers.CharField(read_only=True)
