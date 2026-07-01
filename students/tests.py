"""Students endpoint tests: happy path + permission/validation cases.

The module's routes are not mounted in ``config/urls`` until the integrate step,
so these tests mount the router under a local ``ROOT_URLCONF`` for isolation.
"""
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import include, path, reverse
from rest_framework.test import APITestCase

from core.permissions import Role

from academics.models import Department, Program, Section, Semester
from students.models import Student
from students.urls import router

User = get_user_model()

urlpatterns = [path("", include((router.urls, "students"), namespace="students"))]


@override_settings(ROOT_URLCONF=__name__)
class StudentsAPITests(APITestCase):
    def setUp(self):
        pwd = "Str0ng-Pass!23"
        self.admin = User.objects.create_user(
            email="admin@example.com", password=pwd, full_name="Admin", role=Role.ADMIN
        )
        self.faculty = User.objects.create_user(
            email="fac@example.com", password=pwd, full_name="Fac", role=Role.FACULTY
        )
        self.student_user = User.objects.create_user(
            email="abin@example.com", password=pwd, full_name="Abin Thomas",
            role=Role.STUDENT,
        )
        self.other_student_user = User.objects.create_user(
            email="neha@example.com", password=pwd, full_name="Neha", role=Role.STUDENT
        )

        self.dept = Department.objects.create(code="CSE", name="Computer Science")
        self.program = Program.objects.create(
            code="BTCSE", name="B.Tech CSE", department=self.dept,
            duration_years=4, intake=60,
        )
        self.sem = Semester.objects.create(program=self.program, number=5)
        self.section = Section.objects.create(semester=self.sem, name="A")

        self.student = Student.objects.create(
            user=self.student_user, roll_no="CSE-001", admission_no="ADM-001",
            program=self.program, department=self.dept, semester=self.sem,
            section=self.section, first_name="Abin", last_name="Thomas",
            full_name="Abin Thomas", email="abin@example.com", phone="9999999999",
            cgpa="8.75", blood_group="O+", mentor_name="Dr. Rao",
        )

    # -- roster reads (staff only) ---------------------------------------
    def test_staff_can_list_roster(self):
        self.client.force_authenticate(self.faculty)
        resp = self.client.get(reverse("students:student-list"))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])
        self.assertGreaterEqual(resp.json()["meta"]["pagination"]["count"], 1)

    def test_student_cannot_list_roster(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.get(reverse("students:student-list"))
        self.assertEqual(resp.status_code, 403)

    def test_list_requires_auth(self):
        self.assertEqual(
            self.client.get(reverse("students:student-list")).status_code, 401
        )

    def test_roster_search_by_roll(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.get(reverse("students:student-list"), {"search": "CSE-001"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["meta"]["pagination"]["count"], 1)

    def test_roster_filter_by_department(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.get(
            reverse("students:student-list"), {"department": str(self.dept.id)}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["meta"]["pagination"]["count"], 1)

    # -- /students/me (app-shaped) ---------------------------------------
    def test_student_me_app_shape(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.get(reverse("students:student-me"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["name"], "Abin Thomas")
        self.assertEqual(data["rollNo"], "CSE-001")
        self.assertEqual(data["branch"], "Computer Science")
        self.assertEqual(data["semester"], 5)
        self.assertEqual(data["section"], "A")
        self.assertEqual(data["year"], 3)  # sem 5 -> year 3
        self.assertEqual(data["cgpa"], 8.75)
        self.assertEqual(data["mentorName"], "Dr. Rao")

    def test_student_me_update(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.put(
            reverse("students:student-me"),
            {"phone": "8888888888", "bloodGroup": "A+"}, format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.student.refresh_from_db()
        self.assertEqual(self.student.phone, "8888888888")
        self.assertEqual(self.student.blood_group, "A+")

    def test_me_404_when_no_profile(self):
        self.client.force_authenticate(self.other_student_user)
        resp = self.client.get(reverse("students:student-me"))
        self.assertEqual(resp.status_code, 404)

    # -- write RBAC + audit ----------------------------------------------
    def test_admin_can_create_student_and_it_is_audited(self):
        from core.models import AuditLog

        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            reverse("students:student-list"),
            {
                "roll_no": "CSE-002", "admission_no": "ADM-002",
                "full_name": "New Student", "department": str(self.dept.id),
                "program": str(self.program.id), "semester": str(self.sem.id),
                "section": str(self.section.id), "email": "new@example.com",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(Student.objects.filter(roll_no="CSE-002").exists())
        self.assertTrue(
            AuditLog.objects.filter(entity="Student", action="create").exists()
        )

    def test_faculty_cannot_create_student(self):
        self.client.force_authenticate(self.faculty)
        resp = self.client.post(
            reverse("students:student-list"),
            {"roll_no": "CSE-003", "full_name": "X"}, format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_create_student_validation_error(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            reverse("students:student-list"),
            {"full_name": "No Roll"}, format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["success"])
