"""Auth URLs. ``config/urls.py`` mounts this at ``/api/v1/auth/``, so patterns
here are relative to that prefix (e.g. ``login`` -> ``/api/v1/auth/login``)."""
from django.urls import path

from accounts.views import (
    ChangePasswordView,
    ForgotPasswordView,
    LoginView,
    LogoutView,
    MeView,
    RefreshView,
    RegisterView,
    ResetPasswordView,
)

app_name = "accounts"

urlpatterns = [
    path("login", LoginView.as_view(), name="login"),
    path("refresh", RefreshView.as_view(), name="refresh"),
    path("logout", LogoutView.as_view(), name="logout"),
    path("me", MeView.as_view(), name="me"),
    path("change-password", ChangePasswordView.as_view(), name="change-password"),
    path("forgot-password", ForgotPasswordView.as_view(), name="forgot-password"),
    path("reset-password", ResetPasswordView.as_view(), name="reset-password"),
    path("register", RegisterView.as_view(), name="register"),
]
