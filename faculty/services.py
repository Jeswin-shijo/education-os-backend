"""Business-logic layer for the faculty app.

Each service extends :class:`core.services.BaseService` so writes auto-stamp
``created_by``/``updated_by``, emit an :class:`~core.models.AuditLog` row, and
invalidate cached faculty views. Faculty profile/class reads are cached under
the ``faculty`` prefix; any write busts that prefix.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError

from academics.models import Department
from core.cache import invalidate_prefix
from core.models import AuditLog
from core.permissions import Role
from core.services import BaseService

from faculty.models import FacultyClass, FacultyProfile, RosterEntry
from faculty.repositories import (
    FacultyClassRepository,
    FacultyProfileRepository,
    RosterEntryRepository,
)

User = get_user_model()

# Cache-key prefix owned by this app.
FACULTY_PREFIX = "faculty"

# Fallback password for faculty created without one (they reset it on first use).
DEFAULT_FACULTY_PASSWORD = "Campus@123"

# Profile-only model fields the create/update payload may carry (everything else
# in the payload shapes the linked User or resolves the department FK).
_PROFILE_FIELDS = (
    "designation",
    "qualifications",
    "experience",
    "photo_url",
    "subject_codes",
)


class FacultyProfileService(BaseService):
    model = FacultyProfile
    repository_class = FacultyProfileRepository
    entity_name = "FacultyProfile"

    # Faculty CREATE is a two-model write: build/reuse the ``accounts.User``
    # (role=faculty) from the request's user fields, resolve the department
    # reference (id/code/name) to the academics FK, then create-or-get the
    # FacultyProfile. ``phone`` lives on the User, so it is synced there.
    def create(self, **data):
        photo = data.pop("profile_pic", None)
        user_fields = self._pop_user_fields(data)
        department_ref = data.pop("department", None)

        user = self._resolve_or_create_user(user_fields)
        self._apply_profile_pic(user, photo)
        department = self._resolve_department(department_ref)

        profile_fields = {k: data[k] for k in _PROFILE_FIELDS if k in data}
        actor = self._actor_or_none()

        existing = FacultyProfile.objects.filter(user=user).first()
        if existing is not None:
            # "Get" branch: refresh the supplied profile fields on the existing
            # profile so a re-create acts as an idempotent upsert.
            update_data = {"department": department, **profile_fields}
            if actor is not None:
                update_data.setdefault("updated_by", actor)
            instance = self.repository.update(existing, **update_data)
            self.audit(
                AuditLog.ACTION_UPDATE,
                entity_id=instance.pk,
                changes=self._serialize(update_data),
            )
        else:
            create_data = {"user": user, "department": department, **profile_fields}
            if actor is not None:
                create_data.setdefault("created_by", actor)
                create_data.setdefault("updated_by", actor)
            instance = self.repository.create(**create_data)
            self.audit(
                AuditLog.ACTION_CREATE,
                entity_id=instance.pk,
                changes=self._serialize(create_data),
            )

        self._sync_user_phone(instance, user_fields.get("phone"))
        self.invalidate_cache(instance)
        return instance

    def update(self, instance, **data):
        photo = data.pop("profile_pic", None)
        user_fields = self._pop_user_fields(data)
        # A department reference (id/code/name) may be updated too.
        if "department" in data:
            data["department"] = self._resolve_department(data["department"])
        instance = super().update(instance, **data)
        self._sync_user_phone(instance, user_fields.get("phone"))
        self._sync_user_fields(instance, user_fields)
        self._apply_profile_pic(getattr(instance, "user", None), photo)
        return instance

    # -- helpers ---------------------------------------------------------
    @staticmethod
    def _pop_user_fields(data: dict) -> dict:
        """Strip the User-shaping keys out of ``data`` (the rest is profile data)."""
        full_name = data.pop("full_name", None)
        name_alt = data.pop("name", None)
        return {
            "user": data.pop("user", None),
            "email": (data.pop("email", None) or "").strip() or None,
            "full_name": ((full_name or name_alt) or "").strip() or None,
            "password": data.pop("password", None) or None,
            "phone": data.pop("phone", None),
        }

    @staticmethod
    def _resolve_or_create_user(fields: dict):
        """Return the faculty User: the supplied user, an existing user with the
        given email (both forced to role=faculty), or a freshly created one."""
        user = fields.get("user")
        email = fields.get("email")
        full_name = fields.get("full_name")
        phone = fields.get("phone")

        if user is None and email:
            user = User.objects.filter(email__iexact=email).first()

        if user is not None:
            update_fields = []
            if user.role != Role.FACULTY:
                user.role = Role.FACULTY
                update_fields.append("role")
            if full_name and user.full_name != full_name:
                user.full_name = full_name
                update_fields.append("full_name")
            if not user.is_active:
                user.is_active = True
                update_fields.append("is_active")
            if update_fields:
                update_fields.append("updated_at")
                user.save(update_fields=update_fields)
            return user

        if not email:
            raise ValidationError(
                {"email": "An email is required to create a faculty member."}
            )
        return User.objects.create_user(
            email=email,
            password=fields.get("password") or DEFAULT_FACULTY_PASSWORD,
            full_name=full_name or email.split("@")[0],
            role=Role.FACULTY,
            phone=phone or "",
            is_active=True,
        )

    @staticmethod
    def _resolve_department(ref):
        """Resolve a department reference (Department, id, code, or name) to the
        FK instance; raise a 400 if it can't be resolved."""
        if isinstance(ref, Department):
            return ref
        text = "" if ref is None else str(ref).strip()
        if not text:
            raise ValidationError({"department": "A department is required."})

        # Try id (UUID) first, then code, then name — all case-insensitive.
        dept = None
        try:
            dept = Department.objects.filter(pk=text).first()
        except (ValueError, DjangoValidationError):
            dept = None
        if dept is None:
            dept = Department.objects.filter(code__iexact=text).first()
        if dept is None:
            dept = Department.objects.filter(name__iexact=text).first()
        if dept is None:
            raise ValidationError(
                {
                    "department": (
                        f"No department matches '{text}' "
                        "(tried id, code, and name)."
                    )
                }
            )
        return dept

    @staticmethod
    def _sync_user_phone(instance, phone) -> None:
        if phone is None:
            return
        user = instance.user
        if user is not None and user.phone != phone:
            user.phone = phone
            user.save(update_fields=["phone", "updated_at"])

    @staticmethod
    def _apply_profile_pic(user, photo) -> None:
        """Save an uploaded profile picture onto the faculty's User (→ object
        storage when USE_S3). No-op when no file was supplied."""
        if user is None or photo is None:
            return
        user.profile_pic = photo
        user.save(update_fields=["profile_pic", "updated_at"])

    @staticmethod
    def _sync_user_fields(instance, fields: dict) -> None:
        """Persist name/email/password onto the linked user when supplied on update."""
        user = instance.user
        if user is None:
            return
        update_fields = []
        full_name = fields.get("full_name")
        if full_name and user.full_name != full_name:
            user.full_name = full_name
            update_fields.append("full_name")
        email = fields.get("email")
        if email and user.email != email:
            user.email = email
            update_fields.append("email")
        password = fields.get("password")
        if password:
            user.set_password(password)
            update_fields.append("password")
        if update_fields:
            update_fields.append("updated_at")
            user.save(update_fields=update_fields)

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(FACULTY_PREFIX)


class FacultyClassService(BaseService):
    model = FacultyClass
    repository_class = FacultyClassRepository
    entity_name = "FacultyClass"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(FACULTY_PREFIX)


class RosterEntryService(BaseService):
    model = RosterEntry
    repository_class = RosterEntryRepository
    entity_name = "RosterEntry"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(FACULTY_PREFIX)
