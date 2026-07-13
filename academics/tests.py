"""Academics endpoint tests: happy path + permission/validation cases.

The module's routes are not mounted in ``config/urls`` until the integrate step,
so these tests mount the router under a local ``ROOT_URLCONF`` for isolation.
"""
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import include, path, reverse
from rest_framework.test import APITestCase

from core.permissions import Role

from academics.models import (
    ClassSession,
    Department,
    Program,
    Section,
    Semester,
    Subject,
)
from academics.urls import router

User = get_user_model()

# Local urlconf mounting the academics router at the root for tests.
urlpatterns = [path("", include((router.urls, "academics"), namespace="academics"))]


@override_settings(ROOT_URLCONF=__name__)
class AcademicsAPITests(APITestCase):
    def setUp(self):
        pwd = "Str0ng-Pass!23"
        self.admin = User.objects.create_user(
            email="admin@example.com", password=pwd, full_name="Admin", role=Role.ADMIN
        )
        self.student = User.objects.create_user(
            email="abin@example.com", password=pwd, full_name="Abin", role=Role.STUDENT
        )
        self.hod = User.objects.create_user(
            email="hod@example.com", password=pwd, full_name="Hod", role=Role.HOD
        )

        self.dept = Department.objects.create(code="CSE", name="Computer Science")
        self.program = Program.objects.create(
            code="BTCSE", name="B.Tech CSE", department=self.dept,
            duration_years=4, intake=60,
        )
        self.sem = Semester.objects.create(program=self.program, number=5)
        self.section = Section.objects.create(semester=self.sem, name="A")
        self.subject = Subject.objects.create(
            code="sub-ds", name="Data Structures", credits=4,
            department=self.dept, faculty_name="Dr. Rao", color="#2563EB",
        )
        self.session = ClassSession.objects.create(
            subject=self.subject, section=self.section, day=ClassSession.DAY_MON,
            start="09:00", end="10:00", room="B-101", type=ClassSession.TYPE_LECTURE,
        )

    # -- reads open to any authenticated role ----------------------------
    def test_list_departments_authenticated(self):
        self.client.force_authenticate(self.student)
        resp = self.client.get(reverse("academics:department-list"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "success")
        self.assertGreaterEqual(resp.json()["data"]["pagination"]["count"], 1)

    def test_list_requires_auth(self):
        self.assertEqual(
            self.client.get(reverse("academics:department-list")).status_code, 401
        )

    def test_subject_detail_app_shape(self):
        self.client.force_authenticate(self.student)
        resp = self.client.get(
            reverse("academics:subject-detail", args=[self.subject.id])
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        # App-shaped Subject: camelCase `faculty`, no department field.
        self.assertEqual(data["code"], "sub-ds")
        self.assertEqual(data["faculty"], "Dr. Rao")
        self.assertNotIn("department", data)

    # -- timetable custom actions ----------------------------------------
    def test_timetable_week_grouped_by_weekday(self):
        self.client.force_authenticate(self.student)
        resp = self.client.get(reverse("academics:timetable-week"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertIn("Mon", data)
        self.assertIn("Sat", data)
        self.assertEqual(len(data["Mon"]), 1)
        self.assertEqual(data["Mon"][0]["subjectId"], str(self.subject.id))

    def test_timetable_today_returns_list(self):
        self.client.force_authenticate(self.student)
        resp = self.client.get(reverse("academics:timetable-today"))
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json()["data"], list)

    # -- write RBAC ------------------------------------------------------
    def test_student_cannot_create_department(self):
        self.client.force_authenticate(self.student)
        resp = self.client.post(
            reverse("academics:department-list"),
            {"code": "ECE", "name": "Electronics"}, format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_admin_can_create_department_and_it_is_audited(self):
        from core.models import AuditLog

        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            reverse("academics:department-list"),
            {"code": "ECE", "name": "Electronics"}, format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(Department.objects.filter(code="ECE").exists())
        self.assertTrue(
            AuditLog.objects.filter(entity="Department", action="create").exists()
        )

    def test_hod_can_create_subject_but_not_program(self):
        self.client.force_authenticate(self.hod)
        ok = self.client.post(
            reverse("academics:subject-list"),
            {"code": "sub-os", "name": "Operating Systems", "credits": 3,
             "department": str(self.dept.id), "program": str(self.program.id),
             "semester": str(self.sem.id), "academic_session": "2026-2027"},
            format="json",
        )
        self.assertEqual(ok.status_code, 201)
        forbidden = self.client.post(
            reverse("academics:program-list"),
            {"code": "BTECE", "name": "B.Tech ECE", "department": str(self.dept.id),
             "duration_years": 4, "intake": 60}, format="json",
        )
        self.assertEqual(forbidden.status_code, 403)

    def test_create_subject_validation_error(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            reverse("academics:subject-list"),
            {"name": "No Code", "credits": 3, "department": str(self.dept.id)},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["status"], "error")
