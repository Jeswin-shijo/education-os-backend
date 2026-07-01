"""Complaints endpoint tests: happy path + permission/validation cases.

The module's routes are not mounted in ``config/urls`` until the integrate step,
so these tests mount the urlpatterns under a local ``ROOT_URLCONF`` for
isolation.
"""
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import include, path, reverse
from rest_framework.test import APITestCase

from core.models import AuditLog
from core.permissions import Role

from complaints.models import Complaint
from complaints.urls import urlpatterns as complaints_urlpatterns

User = get_user_model()

urlpatterns = [
    path("", include((complaints_urlpatterns, "complaints"), namespace="complaints")),
]


@override_settings(ROOT_URLCONF=__name__)
class ComplaintAPITests(APITestCase):
    def setUp(self):
        pwd = "Str0ng-Pass!23"
        self.admin = User.objects.create_user(
            email="admin@example.com", password=pwd, full_name="Admin",
            role=Role.ADMIN,
        )
        self.principal = User.objects.create_user(
            email="principal@example.com", password=pwd, full_name="Principal",
            role=Role.PRINCIPAL,
        )
        self.faculty = User.objects.create_user(
            email="rao@example.com", password=pwd, full_name="Dr. Rao",
            role=Role.FACULTY,
        )
        self.student = User.objects.create_user(
            email="abin@example.com", password=pwd, full_name="Abin",
            role=Role.STUDENT,
        )
        self.other_student = User.objects.create_user(
            email="bob@example.com", password=pwd, full_name="Bob",
            role=Role.STUDENT,
        )
        self.parent = User.objects.create_user(
            email="parent@example.com", password=pwd, full_name="Parent",
            role=Role.PARENT,
        )

        self.c_mine = Complaint.objects.create(
            user=self.student, category="Hostel",
            subject="Water leak", description="Leak in room 214.",
            status=Complaint.STATUS_OPEN,
        )
        self.c_mine2 = Complaint.objects.create(
            user=self.student, category="Academics",
            subject="Missing marks", description="Internal marks not shown.",
            status=Complaint.STATUS_IN_PROGRESS,
        )
        self.c_other = Complaint.objects.create(
            user=self.other_student, category="Fees",
            subject="Wrong invoice", description="Charged twice.",
            status=Complaint.STATUS_RESOLVED,
        )

    # -- auth ------------------------------------------------------------
    def test_list_requires_auth(self):
        self.assertEqual(
            self.client.get(reverse("complaints:complaints-list")).status_code, 401
        )

    # -- reads / scoping -------------------------------------------------
    def test_student_sees_only_own(self):
        self.client.force_authenticate(self.student)
        resp = self.client.get(reverse("complaints:complaints-list"))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])
        data = resp.json()["data"]
        self.assertEqual(len(data), 2)
        subjects = sorted(row["subject"] for row in data)
        self.assertEqual(subjects, ["Missing marks", "Water leak"])
        # types.ts Complaint shape (camelCase createdOn).
        for key in ("id", "category", "subject", "description", "status", "createdOn"):
            self.assertIn(key, data[0])

    def test_staff_sees_all(self):
        self.client.force_authenticate(self.faculty)
        resp = self.client.get(reverse("complaints:complaints-list"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["data"]), 3)

    def test_student_cannot_retrieve_others_complaint(self):
        self.client.force_authenticate(self.student)
        resp = self.client.get(
            reverse("complaints:complaints-detail", args=[self.c_other.id])
        )
        self.assertEqual(resp.status_code, 404)

    # -- create ----------------------------------------------------------
    def test_student_create_sets_owner_and_audits(self):
        self.client.force_authenticate(self.student)
        resp = self.client.post(
            reverse("complaints:complaints-list"),
            {
                "category": "Transport",
                "subject": "Bus late",
                "description": "Route 3 is consistently late.",
            },
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        body = resp.json()["data"]
        self.assertEqual(body["status"], Complaint.STATUS_OPEN)
        created = Complaint.objects.get(subject="Bus late")
        self.assertEqual(created.user, self.student)
        self.assertTrue(
            AuditLog.objects.filter(entity="Complaint", action="create").exists()
        )

    def test_parent_can_create(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post(
            reverse("complaints:complaints-list"),
            {"category": "Fees", "subject": "Refund", "description": "Refund pending."},
        )
        self.assertEqual(resp.status_code, 201, resp.content)

    def test_create_validation_blank_subject(self):
        self.client.force_authenticate(self.student)
        resp = self.client.post(
            reverse("complaints:complaints-list"),
            {"category": "Hostel", "subject": "   ", "description": "x"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_faculty_cannot_create(self):
        self.client.force_authenticate(self.faculty)
        resp = self.client.post(
            reverse("complaints:complaints-list"),
            {"category": "Hostel", "subject": "x", "description": "y"},
        )
        self.assertEqual(resp.status_code, 403)

    # -- status workflow -------------------------------------------------
    def test_staff_can_patch_status(self):
        self.client.force_authenticate(self.faculty)
        resp = self.client.patch(
            reverse("complaints:complaints-detail", args=[self.c_mine.id]),
            {"status": "in_progress"},
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.c_mine.refresh_from_db()
        self.assertEqual(self.c_mine.status, Complaint.STATUS_IN_PROGRESS)
        self.assertTrue(
            AuditLog.objects.filter(entity="Complaint", action="update").exists()
        )

    def test_status_patch_rejects_invalid_value(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.patch(
            reverse("complaints:complaints-detail", args=[self.c_mine.id]),
            {"status": "closed"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_student_cannot_patch_status(self):
        self.client.force_authenticate(self.student)
        resp = self.client.patch(
            reverse("complaints:complaints-detail", args=[self.c_mine.id]),
            {"status": "resolved"},
        )
        self.assertEqual(resp.status_code, 403)

    # -- monitor ---------------------------------------------------------
    def test_principal_monitor_counts(self):
        self.client.force_authenticate(self.principal)
        resp = self.client.get(reverse("complaints:complaints-monitor"))
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()["data"]
        self.assertEqual(data["total"], 3)
        by_status = {row["status"]: row["count"] for row in data["byStatus"]}
        self.assertEqual(by_status["open"], 1)
        self.assertEqual(by_status["in_progress"], 1)
        self.assertEqual(by_status["resolved"], 1)
        self.assertEqual(len(data["complaints"]), 3)

    def test_admin_monitor_status_filter(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.get(
            reverse("complaints:complaints-monitor"), {"status": "resolved"}
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["total"], 3)
        self.assertEqual(len(data["complaints"]), 1)
        self.assertEqual(data["complaints"][0]["subject"], "Wrong invoice")

    def test_student_cannot_monitor(self):
        self.client.force_authenticate(self.student)
        resp = self.client.get(reverse("complaints:complaints-monitor"))
        self.assertEqual(resp.status_code, 403)

    def test_faculty_cannot_monitor(self):
        self.client.force_authenticate(self.faculty)
        resp = self.client.get(reverse("complaints:complaints-monitor"))
        self.assertEqual(resp.status_code, 403)
