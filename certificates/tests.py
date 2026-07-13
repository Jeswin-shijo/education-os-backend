"""Certificate endpoint tests: happy path + permission/validation cases.

The module's routes are not mounted in ``config/urls`` until the integrate step,
so these tests mount the urlconf under a local ``ROOT_URLCONF`` for isolation.

URL names (namespace ``certificates``):

* ``certificate-mine``   → ``GET /certificates`` (app-facing, requesting student)
* ``certificate-list``   → admin table + issue (``/certificates-admin/``)
* ``certificate-detail`` → admin retrieve/update/delete (``/certificates-admin/:id/``)
"""
from datetime import date

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import include, path, reverse
from rest_framework.test import APITestCase

from core.permissions import Role

from academics.models import Department, Program, Section, Semester
from certificates.models import Certificate
from certificates.urls import urlpatterns as certificates_urlpatterns
from students.models import Student

User = get_user_model()

urlpatterns = [
    path("", include((certificates_urlpatterns, "certificates"), namespace="certificates"))
]


@override_settings(ROOT_URLCONF=__name__)
class CertificateAPITests(APITestCase):
    def setUp(self):
        pwd = "Str0ng-Pass!23"
        self.admin = User.objects.create_user(
            email="admin@example.com", password=pwd, full_name="Admin", role=Role.ADMIN
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
            user=self.student_user, roll_no="CSE-001", program=self.program,
            department=self.dept, semester=self.sem, section=self.section,
            full_name="Abin Thomas", email="abin@example.com",
        )
        self.other_student = Student.objects.create(
            user=self.other_student_user, roll_no="CSE-002",
            program=self.program, department=self.dept, semester=self.sem,
            section=self.section, full_name="Neha", email="neha@example.com",
        )

        self.cert = Certificate.objects.create(
            student=self.student, title="Python Bootcamp", issuer="Coursera",
            issued_on=date(2026, 3, 1), kind=Certificate.KIND_COURSE,
            url="https://example.com/cert.pdf",
        )
        # A certificate belonging to another student, to prove scoping.
        Certificate.objects.create(
            student=self.other_student, title="Hackathon Winner",
            issuer="TechFest", issued_on=date(2026, 2, 1),
            kind=Certificate.KIND_ACHIEVEMENT,
        )

    # -- GET /certificates (requesting student's own certs) --------------
    def test_student_sees_only_own_certificates(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.get(reverse("certificates:certificate-mine"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "success")
        data = resp.json()["data"]
        self.assertEqual(len(data), 1)
        row = data[0]
        self.assertEqual(
            set(row.keys()),
            {"id", "title", "issuer", "issuedOn", "kind", "url", "fileUrl"},
        )
        self.assertEqual(row["title"], "Python Bootcamp")
        self.assertEqual(row["issuedOn"], "2026-03-01")
        self.assertEqual(row["kind"], "course")

    def test_certificates_requires_auth(self):
        self.assertEqual(
            self.client.get(reverse("certificates:certificate-mine")).status_code,
            401,
        )

    def test_certificates_404_when_no_student_profile(self):
        staff = User.objects.create_user(
            email="fac@example.com", password="Str0ng-Pass!23",
            full_name="Fac", role=Role.FACULTY,
        )
        self.client.force_authenticate(staff)
        resp = self.client.get(reverse("certificates:certificate-mine"))
        self.assertEqual(resp.status_code, 404)

    # -- Admin issue/CRUD (RBAC + audit) ---------------------------------
    def test_admin_can_issue_certificate_and_it_is_audited(self):
        from core.models import AuditLog

        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            reverse("certificates:certificate-list"),
            {
                "student": str(self.student.id),
                "title": "Data Structures",
                "issuer": "NPTEL",
                "issued_on": "2026-04-10",
                "kind": "course",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(Certificate.objects.filter(title="Data Structures").exists())
        self.assertTrue(
            AuditLog.objects.filter(entity="Certificate", action="create").exists()
        )

    def test_admin_can_list_full_table(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.get(reverse("certificates:certificate-list"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(len(data), 2)

    def test_admin_can_filter_by_student(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.get(
            reverse("certificates:certificate-list"),
            {"student": str(self.student.id)},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["title"], "Python Bootcamp")

    def test_admin_can_delete_certificate(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.delete(
            reverse("certificates:certificate-detail", args=[self.cert.id])
        )
        self.assertEqual(resp.status_code, 204)
        # Soft-deleted: hidden from default manager, still in all_objects.
        self.assertFalse(Certificate.objects.filter(id=self.cert.id).exists())
        self.assertTrue(Certificate.all_objects.filter(id=self.cert.id).exists())

    def test_create_validation_error(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            reverse("certificates:certificate-list"),
            {"issuer": "Nobody"},  # missing required student + title
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["status"], "error")

    def test_student_cannot_use_admin_table(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.get(reverse("certificates:certificate-list"))
        self.assertEqual(resp.status_code, 403)

    def test_student_cannot_issue_certificate(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.post(
            reverse("certificates:certificate-list"),
            {"student": str(self.student.id), "title": "Nope"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)
