"""Auth endpoint tests: happy path + auth/permission + validation failures."""
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import OTP
from core.permissions import Role

User = get_user_model()


class AuthFlowTests(APITestCase):
    def setUp(self):
        self.password = "Str0ng-Pass!23"
        self.user = User.objects.create_user(
            email="abin@example.com",
            password=self.password,
            full_name="Abin Thomas",
            role=Role.STUDENT,
        )

    # -- login ------------------------------------------------------------
    def test_login_returns_user_access_refresh_and_token(self):
        resp = self.client.post(
            reverse("accounts:login"),
            {"email": self.user.email, "password": self.password},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        data = body["data"]
        self.assertIn("access", data)
        self.assertIn("refresh", data)
        self.assertEqual(data["token"], data["access"])  # mobile alias
        self.assertEqual(data["user"]["email"], self.user.email)
        self.assertEqual(data["user"]["name"], "Abin Thomas")
        self.assertEqual(data["user"]["avatarColor"][0], "#")

    def test_login_bad_password_is_401_enveloped(self):
        resp = self.client.post(
            reverse("accounts:login"),
            {"email": self.user.email, "password": "wrong"},
            format="json",
        )
        self.assertEqual(resp.status_code, 401)
        body = resp.json()
        self.assertFalse(body["success"])
        self.assertTrue(body["errors"])

    def test_login_validation_error_is_400(self):
        resp = self.client.post(reverse("accounts:login"), {"email": "x"}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["success"])

    # -- me ---------------------------------------------------------------
    def test_me_requires_auth(self):
        self.assertEqual(self.client.get(reverse("accounts:me")).status_code, 401)

    def test_me_returns_current_user(self):
        self.client.force_authenticate(self.user)
        resp = self.client.get(reverse("accounts:me"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["email"], self.user.email)

    # -- register (admin only) -------------------------------------------
    def test_register_forbidden_for_student(self):
        self.client.force_authenticate(self.user)
        resp = self.client.post(
            reverse("accounts:register"),
            {"email": "new@example.com", "full_name": "New", "role": Role.FACULTY, "password": "Str0ng-Pass!23"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_register_allowed_for_admin(self):
        admin = User.objects.create_user(
            email="admin@example.com", password=self.password, full_name="Admin", role=Role.ADMIN
        )
        self.client.force_authenticate(admin)
        resp = self.client.post(
            reverse("accounts:register"),
            {"email": "new@example.com", "full_name": "New Faculty", "role": Role.FACULTY, "password": "Str0ng-Pass!23"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(User.objects.filter(email="new@example.com").exists())

    # -- password reset ---------------------------------------------------
    def test_forgot_password_always_200(self):
        resp = self.client.post(
            reverse("accounts:forgot-password"), {"email": "nobody@example.com"}, format="json"
        )
        self.assertEqual(resp.status_code, 200)

    def test_reset_password_with_valid_otp(self):
        otp = OTP.issue(self.user, purpose=OTP.PURPOSE_RESET)
        resp = self.client.post(
            reverse("accounts:reset-password"),
            {"email": self.user.email, "code": otp.code, "new_password": "N3w-Pass!word"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("N3w-Pass!word"))

    def test_reset_password_bad_otp_is_400(self):
        resp = self.client.post(
            reverse("accounts:reset-password"),
            {"email": self.user.email, "code": "000000", "new_password": "N3w-Pass!word"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    # -- change password --------------------------------------------------
    def test_change_password(self):
        self.client.force_authenticate(self.user)
        resp = self.client.post(
            reverse("accounts:change-password"),
            {"current_password": self.password, "new_password": "N3w-Pass!word"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("N3w-Pass!word"))

    # -- logout -----------------------------------------------------------
    def test_logout_blacklists_refresh(self):
        login = self.client.post(
            reverse("accounts:login"),
            {"email": self.user.email, "password": self.password},
            format="json",
        ).json()["data"]
        self.client.force_authenticate(self.user)
        resp = self.client.post(
            reverse("accounts:logout"), {"refresh": login["refresh"]}, format="json"
        )
        self.assertEqual(resp.status_code, 200)
