"""Auth endpoints. Thin views delegating to services; the envelope renderer and
exception handler shape all responses. Router-mounted under ``/api/v1/auth/``.
"""
import secrets

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

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


def _client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _token_payload(user, access: str, refresh: str) -> dict:
    """Login/refresh response body: user + access + refresh, plus ``token``
    duplicating ``access`` for the mobile client."""
    return {
        "user": UserSerializer(user).data,
        "access": access,
        "token": access,  # mobile app expects `token`
        "refresh": refresh,
    }


class LoginView(APIView):
    permission_classes = [AllowAny]
    serializer_class = LoginSerializer

    @extend_schema(
        request=LoginSerializer,
        responses=TokenResponseSerializer,
        summary="Log in with email + password",
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        service = AuthService(ip=_client_ip(request))
        try:
            result = service.login(
                serializer.validated_data["email"],
                serializer.validated_data["password"],
            )
        except (InvalidCredentials, InactiveAccount) as exc:
            raise AuthenticationFailed(str(exc))
        payload = _token_payload(result["user"], result["access"], result["refresh"])
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
            {"access": access, "token": access, "refresh": new_refresh},
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
        service = UserService(actor=request.user, ip=_client_ip(request))
        user = service.register(password=password, **data)
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)
