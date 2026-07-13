"""Assignments endpoint tests: happy path + permission/validation cases.

The module's routes are not mounted in ``config/urls`` until the integrate step,
so these tests mount the urlpatterns under a local ``ROOT_URLCONF`` for
isolation.
"""
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import include, path, reverse
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APITestCase

from core.models import AuditLog
from core.permissions import Role

from academics.models import Department, Program, Section, Semester, Subject
from faculty.models import FacultyClass, FacultyProfile
from students.models import Student

from assignments.models import Assignment, Submission
from assignments.urls import urlpatterns as assignments_urlpatterns

User = get_user_model()

urlpatterns = [
    path("", include((assignments_urlpatterns, "assignments"), namespace="assignments")),
]


@override_settings(ROOT_URLCONF=__name__)
class AssignmentAPITests(APITestCase):
    def setUp(self):
        pwd = "Str0ng-Pass!23"
        self.admin = User.objects.create_user(
            email="admin@example.com", password=pwd, full_name="Admin", role=Role.ADMIN
        )
        self.faculty_user = User.objects.create_user(
            email="rao@example.com", password=pwd, full_name="Dr. Rao",
            role=Role.FACULTY,
        )
        self.other_faculty_user = User.objects.create_user(
            email="menon@example.com", password=pwd, full_name="Dr. Menon",
            role=Role.FACULTY,
        )
        self.student_user = User.objects.create_user(
            email="abin@example.com", password=pwd, full_name="Abin", role=Role.STUDENT
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

        self.profile = FacultyProfile.objects.create(
            user=self.faculty_user, department=self.dept,
            designation="Associate Professor", subject_codes=["sub-ds"],
        )
        self.other_profile = FacultyProfile.objects.create(
            user=self.other_faculty_user, department=self.dept,
            designation="Assistant Professor",
        )
        self.klass = FacultyClass.objects.create(
            subject=self.subject, semester=self.sem, section=self.section,
            faculty=self.profile, color="#2563EB", student_count=1, slots=[],
        )
        self.other_klass = FacultyClass.objects.create(
            subject=self.subject, semester=self.sem, section=self.section,
            faculty=self.other_profile, color="#F59E0B", student_count=0, slots=[],
        )

        self.student = Student.objects.create(
            user=self.student_user, roll_no="CSE001", full_name="Abin Thomas",
            program=self.program, department=self.dept, semester=self.sem,
            section=self.section, avatar_color="#2563EB",
        )

        now = timezone.now()
        self.pending = Assignment.objects.create(
            subject=self.subject, faculty_class=self.klass,
            title="DS Lab 1", description="Linked lists",
            due_date=now + timedelta(days=3), max_marks=50,
        )
        self.graded = Assignment.objects.create(
            subject=self.subject, faculty_class=self.klass,
            title="DS Lab 0", description="Arrays",
            due_date=now - timedelta(days=2), max_marks=50,
            status=Assignment.STATUS_GRADED,
        )
        # A prior graded submission by the student for `graded`.
        Submission.objects.create(
            assignment=self.graded, student=self.student,
            file_name="lab0.pdf", submitted_at=now - timedelta(days=3), grade=45,
        )

    # -- reads -----------------------------------------------------------
    def test_list_requires_auth(self):
        self.assertEqual(
            self.client.get(reverse("assignments:assignments-list")).status_code, 401
        )

    def test_student_list_shape_and_per_student_status(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.get(reverse("assignments:assignments-list"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "success")
        data = resp.json()["data"]
        by_title = {a["title"]: a for a in data}
        # Graded assignment reflects the student's graded submission.
        self.assertEqual(by_title["DS Lab 0"]["status"], "graded")
        self.assertEqual(by_title["DS Lab 0"]["grade"], 45)
        self.assertEqual(by_title["DS Lab 0"]["attachmentName"], "lab0.pdf")
        # Un-submitted, future-due assignment is pending for the student.
        self.assertEqual(by_title["DS Lab 1"]["status"], "pending")
        self.assertIn("subjectId", by_title["DS Lab 1"])
        self.assertIn("maxMarks", by_title["DS Lab 1"])

    def test_status_filter(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.get(
            reverse("assignments:assignments-list"), {"status": "graded"}
        )
        self.assertEqual(resp.status_code, 200)
        titles = [a["title"] for a in resp.json()["data"]]
        self.assertEqual(titles, ["DS Lab 0"])

    def test_retrieve_student_shape(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.get(
            reverse("assignments:assignments-detail", args=[self.pending.id])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["status"], "pending")

    # -- submit ----------------------------------------------------------
    def test_student_can_submit_and_it_is_audited(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.post(
            reverse("assignments:assignments-submit", args=[self.pending.id]),
            {"fileName": "ds-lab1.pdf"}, format="json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["status"], "submitted")
        self.assertEqual(data["attachmentName"], "ds-lab1.pdf")
        self.assertTrue(
            Submission.objects.filter(
                assignment=self.pending, student=self.student
            ).exists()
        )
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.status, Assignment.STATUS_SUBMITTED)
        self.assertTrue(
            AuditLog.objects.filter(entity="Submission", action="create").exists()
        )

    def test_resubmit_updates_existing_submission(self):
        self.client.force_authenticate(self.student_user)
        url = reverse("assignments:assignments-submit", args=[self.pending.id])
        self.client.post(url, {"fileName": "v1.pdf"}, format="json")
        self.client.post(url, {"fileName": "v2.pdf"}, format="json")
        subs = Submission.objects.filter(
            assignment=self.pending, student=self.student
        )
        self.assertEqual(subs.count(), 1)
        self.assertEqual(subs.first().file_name, "v2.pdf")

    def test_submit_validation_error(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.post(
            reverse("assignments:assignments-submit", args=[self.pending.id]),
            {}, format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["status"], "error")

    def test_faculty_cannot_submit(self):
        self.client.force_authenticate(self.faculty_user)
        resp = self.client.post(
            reverse("assignments:assignments-submit", args=[self.pending.id]),
            {"fileName": "x.pdf"}, format="json",
        )
        self.assertEqual(resp.status_code, 403)

    # -- faculty create --------------------------------------------------
    def test_faculty_can_create_assignment(self):
        self.client.force_authenticate(self.faculty_user)
        resp = self.client.post(
            reverse("assignments:assignments-list"),
            {
                "subject": str(self.subject.id),
                "faculty_class": str(self.klass.id),
                "title": "DS Lab 2",
                "description": "Trees",
                "due_date": (timezone.now() + timedelta(days=5)).isoformat(),
                "max_marks": 40,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(Assignment.objects.filter(title="DS Lab 2").exists())
        self.assertTrue(
            AuditLog.objects.filter(entity="Assignment", action="create").exists()
        )

    def test_student_cannot_create_assignment(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.post(
            reverse("assignments:assignments-list"),
            {"subject": str(self.subject.id), "title": "X",
             "due_date": timezone.now().isoformat(), "max_marks": 10},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_create_validation_error(self):
        self.client.force_authenticate(self.faculty_user)
        resp = self.client.post(
            reverse("assignments:assignments-list"),
            {"title": "No subject"},  # missing subject + due_date
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["status"], "error")

    # -- faculty-created list --------------------------------------------
    def test_faculty_assignments_scoped_to_own_classes(self):
        self.client.force_authenticate(self.faculty_user)
        resp = self.client.get(reverse("assignments:faculty-assignments"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        # Both seeded assignments belong to this faculty's class.
        titles = {a["title"] for a in data}
        self.assertEqual(titles, {"DS Lab 0", "DS Lab 1"})
        # Submission count is present.
        row = next(a for a in data if a["title"] == "DS Lab 0")
        self.assertEqual(row["submissions"], 1)
        self.assertEqual(row["classId"], str(self.klass.id))

    def test_faculty_assignments_other_faculty_sees_none(self):
        self.client.force_authenticate(self.other_faculty_user)
        resp = self.client.get(reverse("assignments:faculty-assignments"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"], [])

    def test_student_cannot_list_faculty_assignments(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.get(reverse("assignments:faculty-assignments"))
        self.assertEqual(resp.status_code, 403)
