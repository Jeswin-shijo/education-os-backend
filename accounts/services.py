"""Auth + user business logic.

Owns authentication, JWT issuance, logout (refresh blacklist), OTP issue/verify,
password reset, and admin registration. Writes AuditLog rows through the core
service base and enqueues email via Celery tasks.
"""
from __future__ import annotations

from typing import Optional

from django.contrib.auth import authenticate, get_user_model
from django.utils import timezone
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import AuditLog
from core.services import BaseService
from accounts.models import OTP
from accounts.repositories import UserRepository
from accounts.tasks import send_otp_email, send_welcome_email

User = get_user_model()


class InvalidCredentials(Exception):
    """Raised on failed authentication."""


class InactiveAccount(Exception):
    """Raised when a valid credential belongs to a disabled account."""


class InvalidOTP(Exception):
    """Raised when an OTP is missing, expired, or already used."""


class TokenIssuer:
    """Builds SimpleJWT token pairs with ``user`` + ``role`` claims baked in."""

    @staticmethod
    def for_user(user) -> RefreshToken:
        refresh = RefreshToken.for_user(user)
        refresh["role"] = user.role
        refresh["email"] = user.email
        refresh["full_name"] = user.full_name
        return refresh

    @classmethod
    def pair(cls, user) -> dict:
        refresh = cls.for_user(user)
        return {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }


class AuthService(BaseService):
    """Authentication + token lifecycle."""

    model = User
    entity_name = "User"

    def __init__(self, actor=None, ip=None):
        super().__init__(actor=actor, ip=ip)
        self.users = UserRepository()

    # -- login ------------------------------------------------------------
    def authenticate(self, email: str, password: str):
        user = authenticate(username=email, password=password)
        if user is None:
            # Distinguish inactive from wrong credentials where possible.
            existing = self.users.get_by_email(email)
            if existing is not None and not existing.is_active:
                raise InactiveAccount("This account is disabled.")
            raise InvalidCredentials("Invalid email or password.")
        if not user.is_active:
            raise InactiveAccount("This account is disabled.")
        return user

    def login(self, email: str, password: str) -> dict:
        user = self.authenticate(email, password)
        tokens = TokenIssuer.pair(user)
        self.actor = user  # so the audit row is attributed to the logging-in user
        self.audit(AuditLog.ACTION_LOGIN, entity_id=user.pk)
        return {"user": user, **tokens}

    # -- logout -----------------------------------------------------------
    def logout(self, refresh_token: str) -> None:
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError as exc:  # already blacklisted / invalid
            raise InvalidCredentials("Invalid or expired refresh token.") from exc
        self.audit(AuditLog.ACTION_LOGOUT, entity_id=getattr(self.actor, "pk", None))

    # -- password ---------------------------------------------------------
    def change_password(self, user, current_password: str, new_password: str) -> None:
        if not user.check_password(current_password):
            raise InvalidCredentials("Current password is incorrect.")
        user.set_password(new_password)
        user.save(update_fields=["password", "updated_at"])
        self.actor = user
        self.audit(AuditLog.ACTION_UPDATE, entity_id=user.pk, changes={"password": "changed"})

    # -- OTP / reset ------------------------------------------------------
    def request_password_reset(self, email: str) -> Optional[OTP]:
        """Issue an OTP for password reset. Silent no-op on unknown email
        (to avoid account enumeration) but always audited."""
        user = self.users.get_by_email(email)
        if user is None or not user.is_active:
            return None
        otp = OTP.issue(user, purpose=OTP.PURPOSE_RESET)
        send_otp_email.delay(user.email, otp.code, OTP.PURPOSE_RESET)
        self.actor = user
        self.audit(AuditLog.ACTION_UPDATE, entity_id=user.pk, changes={"otp": "issued"})
        return otp

    def verify_otp(self, email: str, code: str, purpose: str = OTP.PURPOSE_RESET) -> OTP:
        user = self.users.get_by_email(email)
        if user is None:
            raise InvalidOTP("Invalid code.")
        otp = (
            OTP.objects.filter(user=user, code=code, purpose=purpose, used=False)
            .order_by("-created_at")
            .first()
        )
        if otp is None or not otp.is_valid:
            raise InvalidOTP("Invalid or expired code.")
        return otp

    def reset_password(self, email: str, code: str, new_password: str) -> None:
        otp = self.verify_otp(email, code, purpose=OTP.PURPOSE_RESET)
        user = otp.user
        user.set_password(new_password)
        user.save(update_fields=["password", "updated_at"])
        otp.mark_used()
        self.actor = user
        self.audit(AuditLog.ACTION_UPDATE, entity_id=user.pk, changes={"password": "reset"})


class UserService(BaseService):
    """User CRUD (admin registration)."""

    model = User
    entity_name = "User"

    def __init__(self, actor=None, ip=None):
        super().__init__(actor=actor, ip=ip)
        self.users = UserRepository()

    def register(
        self,
        email: str,
        full_name: str,
        role: str,
        password: str,
        phone: str = "",
        **extra,
    ):
        actor = self._actor_or_none()
        user = User.objects.create_user(
            email=email,
            password=password,
            full_name=full_name,
            role=role,
            phone=phone,
            **extra,
        )
        if actor is not None:
            user.created_by = actor
            user.updated_by = actor
            user.save(update_fields=["created_by", "updated_by", "updated_at"])
        self.audit(
            AuditLog.ACTION_CREATE,
            entity_id=user.pk,
            changes={"email": email, "role": role},
        )
        send_welcome_email.delay(user.email, user.full_name)
        return user
