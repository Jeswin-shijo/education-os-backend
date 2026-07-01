"""Exams endpoint tests: happy paths + permission/validation cases.

The module's routes are not mounted in ``config/urls`` until the integrate step,
so these tests mount the app's urlpatterns under a local ``ROOT_URLCONF``.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import include, path, reverse
from django.utils import timezone
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
from faculty.models import FacultyClass, FacultyProfile
from students.models import Student

from exams import urls as exams_urls
from exams.models import Exam, ExamResult, MarkEntry, MarksSheet

User = get_user_model()

# Local urlconf mounting the exams urlpatterns at the root for tests.
urlpatterns = [
    path("", include((exams_urls.urlpatterns, "exams"), namespace="exams"))
]


@override_settings(ROOT_URLCONF=__name__)
class ExamsAPITests(APITestCase):
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
        self.subject_ds = Subject.objects.create(
            code="sub-ds", name="Data Structures", credits=4,
            department=self.dept, color="#2563EB",
        )
        self.subject_os = Subject.objects.create(
            code="sub-os", name="Operating Systems", credits=3,
            department=self.dept, color="#F59E0B",
        )
        # Wire subjects into the student's section timetable so exam scoping works.
        ClassSession.objects.create(
            subject=self.subject_ds, section=self.section, day="Mon",
            start="09:00", end="10:00", room="B-101",
        )
        ClassSession.objects.create(
            subject=self.subject_os, section=self.section, day="Tue",
            start="10:00", end="11:00", room="B-102",
        )

        self.student = Student.objects.create(
            user=self.student_user, roll_no="CSE001", full_name="Abin Thomas",
            program=self.program, department=self.dept, semester=self.sem,
            section=self.section, cgpa=Decimal("8.5"),
        )
        self.student2 = Student.objects.create(
            roll_no="CSE002", full_name="Neha Nair",
            program=self.program, department=self.dept, semester=self.sem,
            section=self.section,
        )

        self.profile = FacultyProfile.objects.create(
            user=self.faculty_user, department=self.dept,
            designation="Associate Professor", subject_codes=["sub-ds"],
        )
        self.other_profile = FacultyProfile.objects.create(
            user=self.other_faculty_user, department=self.dept,
        )
        self.klass = FacultyClass.objects.create(
            subject=self.subject_ds, semester=self.sem, section=self.section,
            faculty=self.profile, student_count=2,
        )
        self.other_klass = FacultyClass.objects.create(
            subject=self.subject_os, semester=self.sem, section=self.section,
            faculty=self.other_profile,
        )

        today = timezone.localdate()
        self.past_exam = Exam.objects.create(
            subject=self.subject_ds, name="Internal 1", date=today - timedelta(days=5),
            time="10:00", room="B-101", duration_mins=90, type=Exam.TYPE_INTERNAL,
        )
        self.upcoming_exam = Exam.objects.create(
            subject=self.subject_ds, name="Semester", date=today + timedelta(days=10),
            time="10:00", room="B-101", duration_mins=180, type=Exam.TYPE_SEMESTER,
        )

        # Results for the logged-in student (credit-weighted GPA target).
        ExamResult.objects.create(
            student=self.student, subject=self.subject_ds, exam="Internal 1",
            marks=Decimal("36"), max_marks=Decimal("40"), grade="A",
            grade_point=Decimal("9"), credits=Decimal("4"),
        )
        ExamResult.objects.create(
            student=self.student, subject=self.subject_os, exam="Internal 1",
            marks=Decimal("24"), max_marks=Decimal("40"), grade="B",
            grade_point=Decimal("7"), credits=Decimal("3"),
        )
        # A result for another student, which must never leak to the student.
        ExamResult.objects.create(
            student=self.student2, subject=self.subject_ds, exam="Internal 1",
            marks=Decimal("10"), max_marks=Decimal("40"), grade="F",
            grade_point=Decimal("0"), credits=Decimal("4"),
        )

    # -- exams -----------------------------------------------------------
    def test_exams_list_shape_and_auth(self):
        self.assertEqual(self.client.get(reverse("exams:exams-list")).status_code, 401)
        self.client.force_authenticate(self.student_user)
        resp = self.client.get(reverse("exams:exams-list"))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])
        data = resp.json()["data"]
        self.assertEqual(data[0]["subjectId"], str(self.subject_ds.id))
        self.assertIn("durationMins", data[0])

    def test_exams_upcoming_only_future(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.get(reverse("exams:exams-upcoming"))
        self.assertEqual(resp.status_code, 200)
        names = [e["name"] for e in resp.json()["data"]]
        self.assertIn("Semester", names)
        self.assertNotIn("Internal 1", names)

    def test_student_cannot_create_exam(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.post(
            reverse("exams:exams-list"),
            {"subject": str(self.subject_ds.id), "name": "Quiz 1",
             "date": "2026-09-01", "type": "Quiz"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_admin_can_create_exam_and_it_is_audited(self):
        from core.models import AuditLog

        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            reverse("exams:exams-list"),
            {"subject": str(self.subject_ds.id), "name": "Quiz 1",
             "date": "2026-09-01", "time": "09:00", "room": "B-101",
             "duration_mins": 30, "type": "Quiz"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(AuditLog.objects.filter(entity="Exam", action="create").exists())

    # -- results + gpa ---------------------------------------------------
    def test_results_are_self_scoped(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.get(reverse("exams:results-list"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        # Only the student's own two results, not student2's.
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["subjectName"] in {"Data Structures", "Operating Systems"}, True)

    def test_gpa_credit_weighted(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.get(reverse("exams:results-gpa"))
        self.assertEqual(resp.status_code, 200)
        # (9*4 + 7*3) / (4+3) = 57/7 = 8.14
        self.assertAlmostEqual(resp.json()["data"]["gpa"], 8.14, places=2)

    def test_gpa_requires_student_param_for_staff(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.get(reverse("exams:results-gpa"))
        self.assertEqual(resp.status_code, 400)
        ok = self.client.get(
            reverse("exams:results-gpa"), {"student": str(self.student.id)}
        )
        self.assertEqual(ok.status_code, 200)
        self.assertAlmostEqual(ok.json()["data"]["gpa"], 8.14, places=2)

    # -- faculty marks entry ---------------------------------------------
    def test_faculty_can_save_marks_and_upsert(self):
        self.client.force_authenticate(self.faculty_user)
        payload = {
            "classId": str(self.klass.id),
            "exam": "Internal 2",
            "maxMarks": "40",
            "entries": [
                {"studentId": str(self.student.id), "marks": "35"},
                {"studentId": str(self.student2.id), "marks": "28"},
            ],
        }
        resp = self.client.post(reverse("exams:marks-save"), payload, format="json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["classId"], str(self.klass.id))
        self.assertEqual(data["exam"], "Internal 2")
        self.assertEqual(len(data["entries"]), 2)
        self.assertEqual(MarksSheet.objects.filter(faculty_class=self.klass).count(), 1)

        # Re-save (upsert) with one entry -> replaces the sheet's entries.
        payload["entries"] = [{"studentId": str(self.student.id), "marks": "38"}]
        resp2 = self.client.post(reverse("exams:marks-save"), payload, format="json")
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(MarksSheet.objects.filter(faculty_class=self.klass).count(), 1)
        self.assertEqual(
            MarkEntry.objects.filter(sheet__faculty_class=self.klass).count(), 1
        )

    def test_faculty_cannot_save_marks_for_other_class(self):
        self.client.force_authenticate(self.faculty_user)
        payload = {
            "classId": str(self.other_klass.id),
            "exam": "Internal 2",
            "maxMarks": "40",
            "entries": [{"studentId": str(self.student.id), "marks": "35"}],
        }
        resp = self.client.post(reverse("exams:marks-save"), payload, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_save_marks_validation_error(self):
        self.client.force_authenticate(self.faculty_user)
        resp = self.client.post(
            reverse("exams:marks-save"),
            {"classId": str(self.klass.id), "exam": "Internal 2", "maxMarks": "40",
             "entries": []},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["success"])

    def test_student_cannot_post_marks(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.post(
            reverse("exams:marks-save"),
            {"classId": str(self.klass.id), "exam": "X", "maxMarks": "40",
             "entries": [{"studentId": str(self.student.id), "marks": "1"}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_faculty_marks_list_scoped_to_own_classes(self):
        # Seed a sheet on each class.
        s1 = MarksSheet.objects.create(
            faculty_class=self.klass, exam="Internal 1", max_marks=Decimal("40"),
            entered_on=timezone.now(),
        )
        MarksSheet.objects.create(
            faculty_class=self.other_klass, exam="Internal 1",
            max_marks=Decimal("40"), entered_on=timezone.now(),
        )
        self.client.force_authenticate(self.faculty_user)
        resp = self.client.get(reverse("exams:faculty-marks"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], str(s1.id))
