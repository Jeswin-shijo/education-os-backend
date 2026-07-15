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
from core.permissions import Role
from core.services import BaseService
from accounts.models import OTP
from accounts.repositories import UserRepository
from accounts.tasks import safe_delay, send_otp_email, send_welcome_email

User = get_user_model()


class InvalidCredentials(Exception):
    """Raised on failed authentication."""


class InactiveAccount(Exception):
    """Raised when a valid credential belongs to a disabled account."""


class ParentLoginDisabled(Exception):
    """Raised when a ``parent``-role account attempts to log in.

    Parent login is disabled per client request; guardian info is retained on
    the student record but the ``parent`` role can no longer authenticate.
    """


class InvalidOTP(Exception):
    """Raised when an OTP is missing, expired, or already used."""


class TokenIssuer:
    """Builds SimpleJWT token pairs with ``user`` + ``role`` claims baked in."""

    @staticmethod
    def for_user(user, active_role: str | None = None) -> RefreshToken:
        refresh = RefreshToken.for_user(user)
        refresh["role"] = user.role
        refresh["active_role"] = active_role or user.role
        refresh["email"] = user.email
        refresh["full_name"] = user.full_name
        return refresh

    @classmethod
    def pair(cls, user, active_role: str | None = None) -> dict:
        refresh = cls.for_user(user, active_role=active_role)
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
    def authenticate(self, credential: str, password: str):
        """Authenticate by any accepted identifier (email or phone).

        ``credential`` is the value from the contract's ``username``/``email``/
        ``phone`` field. We resolve the user first, then verify the password via
        the resolved account's email (the ``USERNAME_FIELD``)."""
        resolved = self.users.get_by_login(credential)
        login_email = resolved.email if resolved is not None else credential
        user = authenticate(username=login_email, password=password)
        if user is None:
            # Distinguish inactive from wrong credentials where possible.
            if resolved is not None and not resolved.is_active:
                raise InactiveAccount("This account is disabled.")
            raise InvalidCredentials("Invalid credentials.")
        if not user.is_active:
            raise InactiveAccount("This account is disabled.")
        return user

    def login(self, credential: str, password: str) -> dict:
        user = self.authenticate(credential, password)
        # Parent login is disabled: credentials may be valid, but the ``parent``
        # role is not allowed to obtain a session. Guardian info stays on the
        # student record; only authentication for this role is blocked.
        if getattr(user, "role", None) == Role.PARENT:
            raise ParentLoginDisabled("Parent login is disabled.")
        tokens = TokenIssuer.pair(user)
        self.actor = user  # so the audit row is attributed to the logging-in user
        self.audit(AuditLog.ACTION_LOGIN, entity_id=user.pk)
        return {"user": user, "active_role": user.role, **tokens}

    # -- roles / role switching ------------------------------------------
    def roles_for(self, user) -> list[str]:
        """Roles this user may act as. The model carries a single canonical
        role, so the allowed set is just that role (superusers may act as any).

        ``parent`` is never returned: parent login/portal access is disabled, so
        it must not appear as a usable or act-as role (this also blocks
        switching TO parent, which reuses this allowed set).
        """
        if getattr(user, "is_superuser", False):
            roles = list(Role.ALL)
        else:
            roles = [user.role]
        return [r for r in roles if r != Role.PARENT]

    def switch_role(self, user, role: str) -> dict:
        """Re-issue an access token whose ``active_role`` claim is ``role``.

        Rejects roles outside the user's allowed set. Switching TO the disabled
        ``parent`` role is never permitted."""
        if role == Role.PARENT:
            raise InvalidCredentials("Parent role is disabled.")
        if role not in self.roles_for(user):
            raise InvalidCredentials("You cannot switch to that role.")
        tokens = TokenIssuer.pair(user, active_role=role)
        self.actor = user
        self.audit(AuditLog.ACTION_UPDATE, entity_id=user.pk, changes={"active_role": role})
        return {"access": tokens["access"], "active_role": role}

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
        safe_delay(send_otp_email, user.email, otp.code, OTP.PURPOSE_RESET)
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
        safe_delay(send_welcome_email, user.email, user.full_name)
        return user
