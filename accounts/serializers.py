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

    class Meta:
        model = User
        fields = ["id", "name", "email", "role", "avatarColor", "phone", "is_active"]
        read_only_fields = fields


class MeSerializer(UserSerializer):
    """Current-user representation (adds staff flags)."""

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ["is_staff"]
        read_only_fields = fields


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})


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
    """Admin-only user creation."""

    email = serializers.EmailField()
    full_name = serializers.CharField(max_length=255)
    role = serializers.ChoiceField(choices=Role.CHOICES)
    password = serializers.CharField(
        write_only=True, style={"input_type": "password"}, required=False, allow_blank=True
    )
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    avatar_color = serializers.CharField(max_length=9, required=False, allow_blank=True, default="")

    def validate_email(self, value):
        if UserRepository().email_exists(value):
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_password(self, value):
        if value:
            validate_password(value)
        return value


class TokenResponseSerializer(serializers.Serializer):
    """Documents the login/refresh response body (inside the envelope ``data``)."""

    user = UserSerializer(read_only=True)
    access = serializers.CharField(read_only=True)
    token = serializers.CharField(read_only=True, help_text="Alias of access for the mobile client.")
    refresh = serializers.CharField(read_only=True)
