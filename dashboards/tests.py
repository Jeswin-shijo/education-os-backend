"""Dashboards endpoint tests: happy path + shape + auth/permission cases.

The module's routes are not mounted in ``config/urls`` until the integrate step,
so (like the other module tests) these mount the routers under a local
``ROOT_URLCONF`` for isolation. Each test seeds only the source-app rows the
aggregation needs, then asserts the app-shaped dashboard payload.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import include, path, reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from core.cache import invalidate_prefix
from core.permissions import Role

from academics.models import (
    ClassSession,
    Department,
    Program,
    Section,
    Semester,
    Subject,
)
from assignments.models import Assignment
from attendance.models import AttendanceRecord, AttendanceStatus
from chat.models import ChatThread
from exams.models import Exam, ExamResult
from faculty.models import FacultyClass, FacultyProfile
from fees.models import FeeInvoice
from guardians.models import ParentLink
from leave.models import LeaveRequest
from quizzes.models import Quiz
from students.models import Student

from dashboards.services import DASHBOARDS_PREFIX
from dashboards.urls import router

User = get_user_model()

# Local urlconf mounting the dashboards router at the root for tests.
urlpatterns = [
    path("", include((router.urls, "dashboards"), namespace="dashboards"))
]

_TODAY_CODE = {
    0: ClassSession.DAY_MON,
    1: ClassSession.DAY_TUE,
    2: ClassSession.DAY_WED,
    3: ClassSession.DAY_THU,
    4: ClassSession.DAY_FRI,
    5: ClassSession.DAY_SAT,
}.get(date.today().weekday())


@override_settings(ROOT_URLCONF=__name__)
class DashboardsAPITests(APITestCase):
    def setUp(self):
        invalidate_prefix(DASHBOARDS_PREFIX)
        pwd = "Str0ng-Pass!23"
        self.admin = User.objects.create_user(
            email="admin@example.com", password=pwd, full_name="Admin", role=Role.ADMIN
        )
        self.student_user = User.objects.create_user(
            email="abin@example.com", password=pwd, full_name="Abin Thomas",
            role=Role.STUDENT, avatar_color="#2563EB",
        )
        self.parent_user = User.objects.create_user(
            email="parent@example.com", password=pwd, full_name="Mr. Thomas",
            role=Role.PARENT,
        )
        self.faculty_user = User.objects.create_user(
            email="rao@example.com", password=pwd, full_name="Dr. Rao",
            role=Role.FACULTY, avatar_color="#13327F",
        )

        # Academic structure.
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

        # Student profile.
        self.student = Student.objects.create(
            user=self.student_user, roll_no="CSE001", full_name="Abin Thomas",
            program=self.program, department=self.dept, semester=self.sem,
            section=self.section, cgpa=Decimal("8.50"), email="abin@example.com",
        )

        # Attendance: 3 present + 1 absent -> 75%.
        for i, status in enumerate(
            [AttendanceStatus.PRESENT, AttendanceStatus.PRESENT,
             AttendanceStatus.PRESENT, AttendanceStatus.ABSENT]
        ):
            AttendanceRecord.objects.create(
                student=self.student, subject=self.subject,
                date=date.today() - timedelta(days=i), status=status,
            )

        # One graded result (feeds GPA + is not the dashboard cgpa's only source).
        ExamResult.objects.create(
            student=self.student, subject=self.subject, exam="Internal 1",
            marks=Decimal("80"), max_marks=Decimal("100"), grade="A",
            grade_point=Decimal("9.0"), credits=Decimal("4"),
        )

        # Upcoming exam (feeds nextExam).
        self.exam = Exam.objects.create(
            subject=self.subject, name="Semester Exam",
            date=date.today() + timedelta(days=5), time="10:00",
            room="B-101", duration_mins=180, type=Exam.TYPE_SEMESTER,
        )

        # Due fee 5000 (unpaid).
        FeeInvoice.objects.create(
            student=self.student, title="Tuition", term="2026-1",
            amount=Decimal("5000.00"), due_date=date.today() + timedelta(days=10),
            status=FeeInvoice.STATUS_DUE,
        )

        # Pending assignment for the section (no submission -> pending).
        Assignment.objects.create(
            subject=self.subject, title="DS Lab 1", description="",
            due_date=timezone.now() + timedelta(days=2), max_marks=20,
        )

        # Faculty profile + class + slot for today.
        self.profile = FacultyProfile.objects.create(
            user=self.faculty_user, department=self.dept,
            designation="Associate Professor", subject_codes=["sub-ds"],
        )
        slots = []
        if _TODAY_CODE:
            slots = [{"day": _TODAY_CODE, "start": "09:00", "end": "10:00", "room": "B-101"}]
        self.klass = FacultyClass.objects.create(
            subject=self.subject, semester=self.sem, section=self.section,
            faculty=self.profile, color="#2563EB", student_count=30, slots=slots,
        )
        Quiz.objects.create(subject=self.subject, title="Quiz 1", faculty_class=self.klass)

        # Parent link (primary) to the student.
        ParentLink.objects.create(
            parent=self.parent_user, student=self.student,
            relation=ParentLink.RELATION_FATHER, is_primary=True,
        )
        # Child's pending leave -> pendingApprovals = 1.
        LeaveRequest.objects.create(
            user=self.student_user, type=LeaveRequest.TYPE_CASUAL,
            start_date=date.today(), end_date=date.today() + timedelta(days=1),
            reason="Trip", status=LeaveRequest.STATUS_PENDING,
        )
        # Chat thread with 2 unread for the parent.
        ChatThread.objects.create(
            teacher=self.faculty_user, parent=self.parent_user,
            teacher_name="Dr. Rao", subject_label="Data Structures",
            avatar_color="#13327F", last_message_at=timezone.now(),
            unread_count={str(self.parent_user.id): 2},
        )

    # -- student dashboard ----------------------------------------------------
    def test_student_dashboard_shape(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.get(reverse("dashboards:student-dashboard-dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "success")
        data = resp.json()["data"]
        self.assertEqual(data["student"]["name"], "Abin Thomas")
        self.assertEqual(data["attendancePct"], 75)
        self.assertEqual(data["cgpa"], 9.0)  # credit-weighted GPA of results
        self.assertEqual(data["pendingAssignments"], 1)
        self.assertEqual(Decimal(data["dueFees"]), Decimal("5000.00"))
        self.assertEqual(data["nextExam"]["name"], "Semester Exam")
        self.assertIn("todayClasses", data)
        self.assertIn("unread", data)

    def test_student_dashboard_requires_auth(self):
        self.assertEqual(
            self.client.get(
                reverse("dashboards:student-dashboard-dashboard")
            ).status_code,
            401,
        )

    def test_parent_cannot_read_student_dashboard(self):
        self.client.force_authenticate(self.parent_user)
        self.assertEqual(
            self.client.get(
                reverse("dashboards:student-dashboard-dashboard")
            ).status_code,
            403,
        )

    def test_student_dashboard_404_without_profile(self):
        stray = User.objects.create_user(
            email="stray@example.com", password="Str0ng-Pass!23",
            full_name="Stray", role=Role.STUDENT,
        )
        self.client.force_authenticate(stray)
        self.assertEqual(
            self.client.get(
                reverse("dashboards:student-dashboard-dashboard")
            ).status_code,
            404,
        )

    # -- parent dashboard -----------------------------------------------------
    def test_parent_dashboard_shape(self):
        self.client.force_authenticate(self.parent_user)
        resp = self.client.get(reverse("dashboards:parent-dashboard-dashboard"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["child"]["name"], "Abin Thomas")
        self.assertEqual(data["attendancePct"], 75)
        self.assertEqual(data["pendingApprovals"], 1)
        self.assertEqual(data["unreadChats"], 2)
        self.assertEqual(Decimal(data["dueFees"]), Decimal("5000.00"))
        self.assertEqual(data["nextExam"]["name"], "Semester Exam")

    def test_student_cannot_read_parent_dashboard(self):
        self.client.force_authenticate(self.student_user)
        self.assertEqual(
            self.client.get(
                reverse("dashboards:parent-dashboard-dashboard")
            ).status_code,
            403,
        )

    def test_parent_dashboard_404_without_child(self):
        lonely = User.objects.create_user(
            email="lonely@example.com", password="Str0ng-Pass!23",
            full_name="Lonely", role=Role.PARENT,
        )
        self.client.force_authenticate(lonely)
        self.assertEqual(
            self.client.get(
                reverse("dashboards:parent-dashboard-dashboard")
            ).status_code,
            404,
        )

    # -- faculty dashboard ----------------------------------------------------
    def test_faculty_dashboard_shape(self):
        self.client.force_authenticate(self.faculty_user)
        resp = self.client.get(reverse("dashboards:faculty-dashboard-dashboard"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["faculty"]["name"], "Dr. Rao")
        self.assertEqual(data["classCount"], 1)
        self.assertEqual(data["studentCount"], 30)
        self.assertEqual(data["quizCount"], 1)
        self.assertEqual(data["pendingAssignments"], 0)  # no faculty_class assignment
        if _TODAY_CODE:
            self.assertEqual(len(data["todayClasses"]), 1)
            self.assertEqual(
                data["todayClasses"][0]["class"]["subjectCode"], "sub-ds"
            )

    def test_student_cannot_read_faculty_dashboard(self):
        self.client.force_authenticate(self.student_user)
        self.assertEqual(
            self.client.get(
                reverse("dashboards:faculty-dashboard-dashboard")
            ).status_code,
            403,
        )

    def test_faculty_dashboard_404_without_profile(self):
        self.client.force_authenticate(self.admin)  # admin allowed by RBAC, no profile
        self.assertEqual(
            self.client.get(
                reverse("dashboards:faculty-dashboard-dashboard")
            ).status_code,
            404,
        )

    # -- caching --------------------------------------------------------------
    def test_student_dashboard_is_cached(self):
        from dashboards.services import student_dashboard_key
        from django.core.cache import cache

        self.client.force_authenticate(self.student_user)
        self.client.get(reverse("dashboards:student-dashboard-dashboard"))
        self.assertIsNotNone(cache.get(student_dashboard_key(self.student.pk)))
