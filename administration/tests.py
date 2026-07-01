"""Administration endpoint tests: happy path + permission + validation cases.

Routes are not mounted in ``config/urls`` until the integrate step, so these
tests mount the app's urlpatterns under a local ``ROOT_URLCONF`` for isolation.
"""
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import include, path, reverse
from rest_framework.test import APITestCase

from core.models import AuditLog
from core.permissions import Role

from administration.urls import urlpatterns as admin_urlpatterns

User = get_user_model()

urlpatterns = [
    path("", include((admin_urlpatterns, "administration"), namespace="administration")),
]

PWD = "Str0ng-Pass!23"


@override_settings(ROOT_URLCONF=__name__)
class AdministrationAPITests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@example.com", password=PWD, full_name="Admin One", role=Role.ADMIN,
        )
        self.admin2 = User.objects.create_user(
            email="admin2@example.com", password=PWD, full_name="Admin Two", role=Role.ADMIN,
        )
        self.faculty = User.objects.create_user(
            email="rao@example.com", password=PWD, full_name="Dr. Rao", role=Role.FACULTY,
        )
        self.student = User.objects.create_user(
            email="abin@example.com", password=PWD, full_name="Abin", role=Role.STUDENT,
        )
        AuditLog.objects.create(actor=self.admin, action="create", entity="Book", entity_id="b1")
        AuditLog.objects.create(actor=self.faculty, action="update", entity="Assignment", entity_id="a1")

    # -- audit logs ------------------------------------------------------
    def test_audit_logs_admin_can_browse(self):
        self.client.force_authenticate(self.admin)
        res = self.client.get(reverse("administration:admin-audit-logs-list"))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["pagination"]["count"], 2)

    def test_audit_logs_filter_by_entity(self):
        self.client.force_authenticate(self.admin)
        url = reverse("administration:admin-audit-logs-list")
        res = self.client.get(url, {"entity": "Book"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["pagination"]["count"], 1)

    def test_audit_logs_non_admin_forbidden(self):
        self.client.force_authenticate(self.faculty)
        res = self.client.get(reverse("administration:admin-audit-logs-list"))
        self.assertEqual(res.status_code, 403)

    def test_audit_logs_unauthenticated(self):
        res = self.client.get(reverse("administration:admin-audit-logs-list"))
        self.assertEqual(res.status_code, 401)

    # -- dashboard -------------------------------------------------------
    def test_dashboard_counts(self):
        self.client.force_authenticate(self.admin)
        res = self.client.get(reverse("administration:admin-dashboard"))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["users"]["total"], 4)
        self.assertEqual(res.data["users"]["admins"], 2)
        self.assertIn("academics", res.data)

    def test_dashboard_forbidden_for_student(self):
        self.client.force_authenticate(self.student)
        res = self.client.get(reverse("administration:admin-dashboard"))
        self.assertEqual(res.status_code, 403)

    # -- users list / create --------------------------------------------
    def test_users_list_and_filter(self):
        self.client.force_authenticate(self.admin)
        url = reverse("administration:admin-users-list")
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["pagination"]["count"], 4)
        res = self.client.get(url, {"role": Role.FACULTY})
        self.assertEqual(res.data["pagination"]["count"], 1)

    def test_users_search(self):
        self.client.force_authenticate(self.admin)
        res = self.client.get(reverse("administration:admin-users-list"), {"search": "Rao"})
        self.assertEqual(res.data["pagination"]["count"], 1)

    def test_create_user(self):
        self.client.force_authenticate(self.admin)
        res = self.client.post(
            reverse("administration:admin-users-list"),
            {"full_name": "New Teacher", "email": "new@example.com", "role": Role.FACULTY},
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["role"], Role.FACULTY)
        self.assertTrue(User.objects.filter(email="new@example.com").exists())
        self.assertTrue(
            AuditLog.objects.filter(entity="User", action="create", entity_id=res.data["id"]).exists()
        )

    def test_create_user_duplicate_email_rejected(self):
        self.client.force_authenticate(self.admin)
        res = self.client.post(
            reverse("administration:admin-users-list"),
            {"full_name": "Dup", "email": "abin@example.com", "role": Role.STUDENT},
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_create_user_forbidden_for_faculty(self):
        self.client.force_authenticate(self.faculty)
        res = self.client.post(
            reverse("administration:admin-users-list"),
            {"full_name": "X", "email": "x@example.com", "role": Role.STUDENT},
            format="json",
        )
        self.assertEqual(res.status_code, 403)

    # -- set role --------------------------------------------------------
    def test_set_role(self):
        self.client.force_authenticate(self.admin)
        url = reverse("administration:admin-users-set-role", args=[self.student.id])
        res = self.client.patch(url, {"role": Role.FACULTY}, format="json")
        self.assertEqual(res.status_code, 200)
        self.student.refresh_from_db()
        self.assertEqual(self.student.role, Role.FACULTY)

    # -- activate / deactivate + last-admin guard ------------------------
    def test_deactivate_user(self):
        self.client.force_authenticate(self.admin)
        url = reverse("administration:admin-users-set-active", args=[self.faculty.id])
        res = self.client.patch(url, {"active": False}, format="json")
        self.assertEqual(res.status_code, 200)
        self.faculty.refresh_from_db()
        self.assertFalse(self.faculty.is_active)

    def test_cannot_deactivate_last_admin(self):
        # Deactivate admin2 first, leaving self.admin the only active admin.
        self.admin2.is_active = False
        self.admin2.save(update_fields=["is_active"])
        self.client.force_authenticate(self.admin)
        url = reverse("administration:admin-users-set-active", args=[self.admin.id])
        res = self.client.patch(url, {"active": False}, format="json")
        self.assertEqual(res.status_code, 400)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_cannot_delete_last_admin(self):
        self.admin2.is_active = False
        self.admin2.save(update_fields=["is_active"])
        self.client.force_authenticate(self.admin)
        url = reverse("administration:admin-users-detail", args=[self.admin.id])
        res = self.client.delete(url)
        self.assertEqual(res.status_code, 400)

    def test_cannot_demote_last_admin_role(self):
        self.admin2.is_active = False
        self.admin2.save(update_fields=["is_active"])
        self.client.force_authenticate(self.admin)
        url = reverse("administration:admin-users-set-role", args=[self.admin.id])
        res = self.client.patch(url, {"role": Role.FACULTY}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_delete_admin_when_another_active_admin_exists(self):
        self.client.force_authenticate(self.admin)
        url = reverse("administration:admin-users-detail", args=[self.admin2.id])
        res = self.client.delete(url)
        self.assertEqual(res.status_code, 204)
        self.assertFalse(User.objects.filter(id=self.admin2.id).exists())

    # -- roles / permissions --------------------------------------------
    def test_roles_endpoint(self):
        self.client.force_authenticate(self.admin)
        res = self.client.get(reverse("administration:admin-roles"))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data), len(Role.CHOICES))

    def test_permissions_endpoint(self):
        self.client.force_authenticate(self.admin)
        res = self.client.get(reverse("administration:admin-permissions"))
        self.assertEqual(res.status_code, 200)
        self.assertIn("matrix", res.data)
        self.assertIn("attendance", res.data["matrix"])

    def test_permissions_forbidden_for_student(self):
        self.client.force_authenticate(self.student)
        res = self.client.get(reverse("administration:admin-permissions"))
        self.assertEqual(res.status_code, 403)
