"""Placement endpoint tests: happy path + permission + validation cases.

The module's routes are not mounted in ``config/urls`` until the integrate step,
so these tests mount the urlconf under a local ``ROOT_URLCONF`` for isolation.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import include, path, reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from core.permissions import Role

from academics.models import Department, Program, Section, Semester
from placement.models import PlacementApplication, PlacementOpening
from placement.urls import urlpatterns as placement_urlpatterns
from students.models import Student

User = get_user_model()

urlpatterns = [
    path("", include((placement_urlpatterns, "placement"), namespace="placement"))
]


@override_settings(ROOT_URLCONF=__name__)
class PlacementAPITests(APITestCase):
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
        self.student_user = User.objects.create_user(
            email="abin@example.com", password=pwd, full_name="Abin Thomas",
            role=Role.STUDENT,
        )
        self.other_student_user = User.objects.create_user(
            email="neha@example.com", password=pwd, full_name="Neha",
            role=Role.STUDENT,
        )

        self.dept = Department.objects.create(code="CSE", name="Computer Science")
        self.program = Program.objects.create(
            code="BTCSE", name="B.Tech CSE", department=self.dept,
            duration_years=4, intake=60,
        )
        self.sem = Semester.objects.create(program=self.program, number=5)
        self.section = Section.objects.create(semester=self.sem, name="A")
        self.student = Student.objects.create(
            user=self.student_user, roll_no="CSE-001", program=self.program,
            department=self.dept, semester=self.sem, section=self.section,
            full_name="Abin Thomas", email="abin@example.com",
        )
        self.other_student = Student.objects.create(
            user=self.other_student_user, roll_no="CSE-002",
            program=self.program, department=self.dept, semester=self.sem,
            section=self.section, full_name="Neha", email="neha@example.com",
        )

        today = timezone.localdate()
        self.opening = PlacementOpening.objects.create(
            company="Acme Corp", role="SDE-1", ctc=Decimal("1200000.00"),
            location="Bangalore", eligibility="CGPA >= 7",
            last_date=today + timedelta(days=30), logo_color="#FF0000",
            is_active=True,
        )
        self.inactive = PlacementOpening.objects.create(
            company="Old Co", role="Intern", ctc=Decimal("300000.00"),
            location="Remote", last_date=today - timedelta(days=5),
            is_active=False,
        )

    # -- GET /placements (app-shaped, active only) -----------------------
    def test_student_sees_active_openings(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.get(reverse("placement:opening-app-list"))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])
        data = resp.json()["data"]
        self.assertEqual(len(data), 1)  # inactive hidden
        row = data[0]
        self.assertEqual(
            set(row.keys()),
            {"id", "company", "role", "ctc", "location", "eligibility",
             "lastDate", "logoColor", "applied"},
        )
        self.assertEqual(row["company"], "Acme Corp")
        self.assertEqual(row["logoColor"], "#FF0000")
        self.assertFalse(row["applied"])

    def test_openings_requires_auth(self):
        self.assertEqual(
            self.client.get(reverse("placement:opening-app-list")).status_code, 401
        )

    def test_admin_can_include_inactive_with_all_flag(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.get(reverse("placement:opening-app-list"), {"all": "1"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["data"]), 2)

    # -- POST /placements/{id}/apply -------------------------------------
    def test_student_can_apply_and_flag_flips(self):
        from core.models import AuditLog

        self.client.force_authenticate(self.student_user)
        resp = self.client.post(
            reverse("placement:apply", args=[self.opening.id])
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertTrue(data["applied"])
        self.assertTrue(
            PlacementApplication.objects.filter(
                opening=self.opening, student=self.student
            ).exists()
        )
        self.assertTrue(
            AuditLog.objects.filter(
                entity="PlacementApplication", action="create"
            ).exists()
        )

    def test_apply_is_idempotent(self):
        self.client.force_authenticate(self.student_user)
        url = reverse("placement:apply", args=[self.opening.id])
        self.client.post(url)
        self.client.post(url)
        self.assertEqual(
            PlacementApplication.objects.filter(
                opening=self.opening, student=self.student
            ).count(),
            1,
        )

    def test_apply_404_without_student_profile(self):
        self.client.force_authenticate(self.admin)  # no Student profile
        resp = self.client.post(
            reverse("placement:apply", args=[self.opening.id])
        )
        self.assertEqual(resp.status_code, 404)

    # -- GET /placements/applications (own) ------------------------------
    def test_student_sees_only_own_applications(self):
        PlacementApplication.objects.create(
            opening=self.opening, student=self.student,
        )
        PlacementApplication.objects.create(
            opening=self.opening, student=self.other_student,
        )
        self.client.force_authenticate(self.student_user)
        resp = self.client.get(reverse("placement:my-applications"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(len(data), 1)
        row = data[0]
        self.assertEqual(
            set(row.keys()),
            {"id", "openingId", "company", "role", "ctc", "logoColor",
             "status", "appliedOn"},
        )
        self.assertEqual(row["company"], "Acme Corp")
        self.assertEqual(row["status"], "applied")

    # -- GET /placements/stats (admin/principal) -------------------------
    def test_admin_sees_stats(self):
        PlacementApplication.objects.create(
            opening=self.opening, student=self.student,
            status=PlacementApplication.STATUS_SELECTED,
        )
        self.client.force_authenticate(self.admin)
        resp = self.client.get(reverse("placement:stats"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["placed"], 1)
        self.assertEqual(data["activeOpenings"], 1)
        self.assertEqual(data["highestCtcLpa"], 12.0)
        self.assertIn("Acme Corp", data["topRecruiters"])

    def test_principal_can_see_stats(self):
        self.client.force_authenticate(self.principal)
        self.assertEqual(
            self.client.get(reverse("placement:stats")).status_code, 200
        )

    def test_student_cannot_see_stats(self):
        self.client.force_authenticate(self.student_user)
        self.assertEqual(
            self.client.get(reverse("placement:stats")).status_code, 403
        )

    # -- Admin opening CRUD (RBAC + audit) -------------------------------
    def test_admin_can_create_opening_and_it_is_audited(self):
        from core.models import AuditLog

        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            reverse("placement:opening-list"),
            {
                "company": "Globex", "role": "Analyst",
                "ctc": "800000.00", "location": "Pune",
                "eligibility": "Any", "last_date": "2026-12-31",
                "logo_color": "#00FF00", "is_active": True,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(PlacementOpening.objects.filter(company="Globex").exists())
        self.assertTrue(
            AuditLog.objects.filter(
                entity="PlacementOpening", action="create"
            ).exists()
        )

    def test_student_cannot_create_opening(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.post(
            reverse("placement:opening-list"),
            {"company": "Nope", "role": "x", "last_date": "2026-12-31"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_create_opening_validation_error(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            reverse("placement:opening-list"),
            {"company": "Missing dates"},  # no role / last_date
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["success"])

    def test_student_cannot_list_admin_applications(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.get(reverse("placement:application-list"))
        self.assertEqual(resp.status_code, 403)
