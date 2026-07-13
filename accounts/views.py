"""Auth endpoints. Thin views delegating to services; the envelope renderer and
exception handler shape all responses. Router-mounted under ``/api/v1/auth/``.
"""
from __future__ import annotations

import secrets

from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import (
    AuthenticationFailed,
    NotFound,
    PermissionDenied,
    ValidationError,
)
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from core.throttles import LoginRateThrottle, PasswordResetRateThrottle

from accounts.permissions import CanRegisterUser
from accounts.serializers import (
    ChangePasswordSerializer,
    ForgotPasswordSerializer,
    LoginSerializer,
    LogoutSerializer,
    MeSerializer,
    RefreshSerializer,
    RegisterSerializer,
    ResetPasswordSerializer,
    RolesResponseSerializer,
    SwitchRoleResponseSerializer,
    SwitchRoleSerializer,
    TokenResponseSerializer,
    UserSerializer,
)
from accounts.services import (
    AuthService,
    InactiveAccount,
    InvalidCredentials,
    InvalidOTP,
    TokenIssuer,
    UserService,
)
from core.permissions import Role

User = get_user_model()


def _client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _resolve_user_or_403(request, user_id):
    """Resolve an accounts user by id, enforcing self-or-staff access.

    Student/parent may only target their own ``user_id``; any staff-side role
    may target anyone. Returns the target :class:`User` or raises 404/403."""
    target = User.objects.filter(pk=user_id).first()
    if target is None:
        raise NotFound("User not found.")
    actor = request.user
    if getattr(actor, "role", None) in set(Role.STAFF):
        return target
    if str(actor.pk) != str(user_id):
        raise PermissionDenied("You can only access your own resource.")
    return target


def _token_payload(user, access: str, refresh: str, active_role: str | None = None) -> dict:
    """Login/refresh response body. Emits the spec-exact ``access_token`` /
    ``refresh_token`` (+ ``active_role``) plus legacy ``access`` / ``token`` /
    ``refresh`` aliases for back-compat."""
    payload = {
        "user": UserSerializer(user).data,
        "access_token": access,
        "refresh_token": refresh,
        "access": access,
        "token": access,  # legacy alias the mobile app also accepts
        "refresh": refresh,
    }
    payload["active_role"] = active_role if active_role is not None else user.role
    return payload


class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]
    serializer_class = LoginSerializer

    @extend_schema(
        request=LoginSerializer,
        responses=TokenResponseSerializer,
        summary="Log in with username / email / phone + password",
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        service = AuthService(ip=_client_ip(request))
        try:
            result = service.login(
                serializer.validated_data["credential"],
                serializer.validated_data["password"],
            )
        except (InvalidCredentials, InactiveAccount) as exc:
            raise AuthenticationFailed(str(exc))
        payload = _token_payload(
            result["user"],
            result["access"],
            result["refresh"],
            active_role=result["active_role"],
        )
        return Response(payload, status=status.HTTP_200_OK)


class RefreshView(APIView):
    permission_classes = [AllowAny]
    serializer_class = RefreshSerializer

    @extend_schema(request=RefreshSerializer, responses=TokenResponseSerializer, summary="Refresh access token")
    def post(self, request):
        serializer = RefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            refresh = RefreshToken(serializer.validated_data["refresh"])
            access = str(refresh.access_token)
            # Return a possibly-rotated refresh token (SIMPLE_JWT rotation).
            new_refresh = str(refresh)
        except TokenError as exc:
            raise AuthenticationFailed("Invalid or expired refresh token.") from exc
        return Response(
            {
                "access_token": access,
                "refresh_token": new_refresh,
                "access": access,
                "token": access,
                "refresh": new_refresh,
            },
            status=status.HTTP_200_OK,
        )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LogoutSerializer

    @extend_schema(request=LogoutSerializer, responses=None, summary="Log out (blacklist refresh token)")
    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        service = AuthService(actor=request.user, ip=_client_ip(request))
        try:
            service.logout(serializer.validated_data["refresh"])
        except InvalidCredentials as exc:
            raise ValidationError({"refresh": str(exc)})
        return Response({"detail": "Logged out."}, status=status.HTTP_200_OK)


class MeView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = MeSerializer

    @extend_schema(responses=MeSerializer, summary="Get the current user")
    def get(self, request):
        return Response(MeSerializer(request.user).data, status=status.HTTP_200_OK)


class RolesView(APIView):
    """``GET /api/v1/auth/roles/{user_id}`` -> ``data: { roles: [...] }``.

    ``{user_id}`` is the accounts user id; self-or-staff access is enforced."""

    permission_classes = [IsAuthenticated]
    serializer_class = RolesResponseSerializer

    @extend_schema(responses=RolesResponseSerializer, summary="List the roles a user may act as")
    def get(self, request, user_id):
        target = _resolve_user_or_403(request, user_id)
        service = AuthService(actor=request.user, ip=_client_ip(request))
        return Response({"roles": service.roles_for(target)}, status=status.HTTP_200_OK)


class SwitchRoleView(APIView):
    """``POST /api/v1/auth/switch-role`` — re-issue an access token whose
    ``active_role`` claim is the requested role.

    Returns ``data: { access_token, active_role }``."""

    permission_classes = [IsAuthenticated]
    serializer_class = SwitchRoleSerializer

    @extend_schema(
        request=SwitchRoleSerializer,
        responses=SwitchRoleResponseSerializer,
        summary="Switch the active role for the current user",
    )
    def post(self, request):
        serializer = SwitchRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        service = AuthService(actor=request.user, ip=_client_ip(request))
        try:
            result = service.switch_role(request.user, serializer.validated_data["role"])
        except InvalidCredentials as exc:
            raise PermissionDenied(str(exc))
        return Response(
            {"access_token": result["access"], "active_role": result["active_role"]},
            status=status.HTTP_200_OK,
        )


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ChangePasswordSerializer

    @extend_schema(request=ChangePasswordSerializer, responses=None, summary="Change own password")
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        service = AuthService(actor=request.user, ip=_client_ip(request))
        try:
            service.change_password(
                request.user,
                serializer.validated_data["current_password"],
                serializer.validated_data["new_password"],
            )
        except InvalidCredentials as exc:
            raise ValidationError({"current_password": str(exc)})
        return Response({"detail": "Password changed."}, status=status.HTTP_200_OK)


class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetRateThrottle]
    serializer_class = ForgotPasswordSerializer

    @extend_schema(request=ForgotPasswordSerializer, responses=None, summary="Request a password-reset code")
    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        service = AuthService(ip=_client_ip(request))
        service.request_password_reset(serializer.validated_data["email"])
        # Always 200 (no account enumeration).
        return Response(
            {"detail": "If that email exists, a reset code has been sent."},
            status=status.HTTP_200_OK,
        )


class ResetPasswordView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetRateThrottle]
    serializer_class = ResetPasswordSerializer

    @extend_schema(request=ResetPasswordSerializer, responses=None, summary="Reset password with a code")
    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        service = AuthService(ip=_client_ip(request))
        try:
            service.reset_password(
                serializer.validated_data["email"],
                serializer.validated_data["code"],
                serializer.validated_data["new_password"],
            )
        except InvalidOTP as exc:
            raise ValidationError({"code": str(exc)})
        return Response({"detail": "Password has been reset."}, status=status.HTTP_200_OK)


class RegisterView(APIView):
    permission_classes = [IsAuthenticated, CanRegisterUser]
    serializer_class = RegisterSerializer

    @extend_schema(request=RegisterSerializer, responses=UserSerializer, summary="Register a user (admin only)")
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        password = data.pop("password", None) or secrets.token_urlsafe(16)

        # Extract student profile fields before passing to user service.
        student_fields = {}
        for key in (
            "roll_no", "admission_no", "department", "program",
            "semester", "section", "gender", "dob", "blood_group", "mentor_name",
        ):
            value = data.pop(key, None)
            if value:
                student_fields[key] = value

        # Extract faculty profile fields.
        faculty_fields = {}
        for key in ("designation",):
            value = data.pop(key, None)
            if value:
                faculty_fields[key] = value
        # Department is shared between student and faculty — keep in both.
        if "department" not in student_fields:
            dept = data.pop("department", None)
            if dept:
                student_fields["department"] = dept
                faculty_fields["department"] = dept
        else:
            faculty_fields["department"] = student_fields.get("department")

        # Handle profile_pic separately (file upload).
        profile_pic = data.pop("profile_pic", None)

        service = UserService(actor=request.user, ip=_client_ip(request))
        user = service.register(password=password, **data)

        # Save profile pic on user if provided.
        if profile_pic:
            user.profile_pic = profile_pic
            user.save(update_fields=["profile_pic", "updated_at"])

        # Auto-create student profile if role is student and profile fields given.
        student_profile = None
        if user.role == Role.STUDENT:
            from students.models import Student
            profile_data = {
                "user": user,
                "full_name": user.full_name,
                "email": user.email,
                "phone": user.phone,
                "roll_no": student_fields.get("roll_no", ""),
                "admission_no": student_fields.get("admission_no", ""),
                "gender": student_fields.get("gender", ""),
                "dob": student_fields.get("dob"),
                "blood_group": student_fields.get("blood_group", ""),
                "mentor_name": student_fields.get("mentor_name", ""),
                "avatar_color": user.avatar_color,
                "profile_pic": profile_pic,
            }
            # Link FK fields (UUIDs → _id columns).
            for fk in ("department", "program", "semester", "section"):
                fk_val = student_fields.get(fk)
                if fk_val:
                    profile_data[f"{fk}_id"] = fk_val

            # Only create if at least roll_no is provided (minimal requirement).
            if profile_data.get("roll_no"):
                student_profile = Student.objects.create(**profile_data)

        response_data = UserSerializer(user).data
        if student_profile:
            response_data["student_id"] = str(student_profile.id)
            response_data["roll_no"] = student_profile.roll_no

        # Auto-create faculty profile if role is faculty and department given.
        faculty_profile = None
        if user.role == Role.FACULTY or user.role == Role.HOD:
            dept_id = faculty_fields.get("department")
            if dept_id:
                from faculty.models import FacultyProfile
                faculty_profile = FacultyProfile.objects.create(
                    user=user,
                    department_id=dept_id,
                    designation=faculty_fields.get("designation", ""),
                )

        if faculty_profile:
            response_data["faculty_id"] = str(faculty_profile.id)
            response_data["designation"] = faculty_profile.designation

        return Response(response_data, status=status.HTTP_201_CREATED)

