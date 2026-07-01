"""Accounts models: custom User (email login, RBAC role) and OTP.

User extends the core :class:`~core.models.BaseModel` so it also gets UUID PK,
audit fields, and soft-delete. Because ``User`` itself is the AUTH_USER_MODEL,
its ``created_by``/``updated_by`` self-FKs are inherited from BaseModel and are
nullable — safe for the first (self-registered/superuser) rows.
"""
import secrets
import uuid
from datetime import timedelta

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone

from core.models import BaseModel
from core.permissions import Role


class UserManager(models.Manager):
    """Manager for the custom User model (soft-delete aware via BaseModel)."""

    use_in_migrations = True

    def get_queryset(self):
        # Hide soft-deleted users by default, mirroring SoftDeleteManager.
        return super().get_queryset().filter(is_deleted=False)

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    @staticmethod
    def normalize_email(email):
        try:
            name, domain = email.strip().rsplit("@", 1)
        except ValueError:
            return email.strip()
        return f"{name}@{domain.lower()}"

    def get_by_natural_key(self, username):
        # Required by django.contrib.auth's ModelBackend for password login;
        # USERNAME_FIELD is ``email`` so look users up by it.
        return self.get(**{self.model.USERNAME_FIELD: username})

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("role", Role.STUDENT)
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("role", Role.SUPER_ADMIN)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("full_name", email.split("@")[0])
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


class AllUsersManager(models.Manager):
    """Manager returning every user, including soft-deleted."""


class User(AbstractBaseUser, PermissionsMixin, BaseModel):
    """Custom user: email is the login identifier; RBAC role drives permissions."""

    email = models.EmailField(unique=True, db_index=True)
    full_name = models.CharField(max_length=255)
    role = models.CharField(
        max_length=20,
        choices=Role.CHOICES,
        default=Role.STUDENT,
        db_index=True,
    )
    phone = models.CharField(max_length=20, blank=True, default="")
    avatar_color = models.CharField(max_length=9, blank=True, default="")
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = UserManager()
    all_objects = AllUsersManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        ordering = ["full_name"]
        indexes = [
            models.Index(fields=["role", "is_active"]),
        ]

    def __str__(self):
        return f"{self.full_name} <{self.email}>"

    # Convenience role predicates -----------------------------------------
    @property
    def is_admin_role(self) -> bool:
        return self.role in set(Role.ADMINS)

    @property
    def is_staff_role(self) -> bool:
        return self.role in set(Role.STAFF)

    def save(self, *args, **kwargs):
        if not self.avatar_color:
            self.avatar_color = self._derive_avatar_color()
        super().save(*args, **kwargs)

    def _derive_avatar_color(self) -> str:
        palette = [
            "#2563EB", "#7C3AED", "#DB2777", "#DC2626", "#EA580C",
            "#16A34A", "#0891B2", "#4F46E5", "#CA8A04", "#0D9488",
        ]
        seed = sum(ord(c) for c in (self.email or self.full_name or "u"))
        return palette[seed % len(palette)]


class OTP(BaseModel):
    """One-time passcode for password reset / verification flows."""

    PURPOSE_RESET = "password_reset"
    PURPOSE_VERIFY = "verify_email"
    PURPOSE_LOGIN = "login"
    PURPOSE_CHOICES = [
        (PURPOSE_RESET, "Password reset"),
        (PURPOSE_VERIFY, "Verify email"),
        (PURPOSE_LOGIN, "Login"),
    ]

    DEFAULT_TTL_MINUTES = 10

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="otps",
    )
    code = models.CharField(max_length=6, db_index=True)
    purpose = models.CharField(
        max_length=32, choices=PURPOSE_CHOICES, default=PURPOSE_RESET, db_index=True
    )
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "purpose", "used"]),
        ]

    def __str__(self):
        return f"OTP({self.purpose}) for {self.user_id}"

    @staticmethod
    def generate_code() -> str:
        return f"{secrets.randbelow(1_000_000):06d}"

    @classmethod
    def issue(cls, user, purpose=PURPOSE_RESET, ttl_minutes: int | None = None):
        ttl = ttl_minutes or cls.DEFAULT_TTL_MINUTES
        return cls.objects.create(
            user=user,
            code=cls.generate_code(),
            purpose=purpose,
            expires_at=timezone.now() + timedelta(minutes=ttl),
        )

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_valid(self) -> bool:
        return not self.used and not self.is_expired

    def mark_used(self):
        self.used = True
        self.save(update_fields=["used", "updated_at"])
