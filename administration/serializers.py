"""Serializers for the admin-console endpoints.

Read serializers shape JSON for the console; write serializers validate input.
User output reuses the mobile-app shape (``name``/``avatarColor`` camelCase) plus
the management flags ``is_active``/``is_staff``.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from accounts.repositories import UserRepository
from core.models import AuditLog
from core.permissions import Role

User = get_user_model()


# --- Audit log ---------------------------------------------------------------
class AuditLogSerializer(serializers.ModelSerializer):
    """One audit-trail row for ``GET /admin/audit-logs``."""

    actorName = serializers.CharField(source="actor.full_name", read_only=True, default=None)
    actorEmail = serializers.EmailField(source="actor.email", read_only=True, default=None)

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "action",
            "entity",
            "entity_id",
            "changes",
            "actor",
            "actorName",
            "actorEmail",
            "ip",
            "at",
        ]
        read_only_fields = fields


# --- Users -------------------------------------------------------------------
class AdminUserSerializer(serializers.ModelSerializer):
    """Managed-user representation for the admin directory."""

    name = serializers.CharField(source="full_name", read_only=True)
    avatarColor = serializers.CharField(source="avatar_color", read_only=True)
    active = serializers.BooleanField(source="is_active", read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "name",
            "email",
            "role",
            "phone",
            "avatarColor",
            "is_active",
            "active",
            "is_staff",
            "created_at",
        ]
        read_only_fields = fields


class AdminUserCreateSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=255)
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=Role.CHOICES)
    password = serializers.CharField(
        write_only=True, required=False, allow_blank=True, style={"input_type": "password"}
    )
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    avatar_color = serializers.CharField(max_length=9, required=False, allow_blank=True, default="")
    is_active = serializers.BooleanField(required=False, default=True)

    def validate_email(self, value):
        if UserRepository().email_exists(value):
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_password(self, value):
        if value:
            validate_password(value)
        return value


class AdminUserUpdateSerializer(serializers.Serializer):
    """PATCH body: any subset of editable fields (role/active/profile)."""

    full_name = serializers.CharField(max_length=255, required=False)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    avatar_color = serializers.CharField(max_length=9, required=False, allow_blank=True)
    role = serializers.ChoiceField(choices=Role.CHOICES, required=False)
    is_active = serializers.BooleanField(required=False)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Provide at least one field to update.")
        return attrs


class SetRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=Role.CHOICES)


class SetActiveSerializer(serializers.Serializer):
    active = serializers.BooleanField()


# --- Roles & permissions -----------------------------------------------------
class RoleSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()
