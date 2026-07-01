"""Tests for the analytics app — HOD + Principal read-only aggregations.

Covers, per endpoint: the happy path (correct shape + computed values),
auth (401 for anonymous) and RBAC (403 for the wrong role). Seeds a small
department with faculty/classes/students/attendance/marks/fees/placements/
complaints so the rollups have real numbers to assert on.

Analytics performs no writes, so there are no write/validation-failure cases.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from academics.models import Department, Program, Section, Semester, Subject
from accounts.models import User
from attendance.models import AttendanceRecord, AttendanceSession
from complaints.models import Complaint
from core.permissions import Role
from exams.models import ExamResult, MarkEntry, MarksSheet
from faculty.models import FacultyClass, FacultyProfile
from fees.models import FeeInvoice
from placement.models import PlacementApplication, PlacementOpening
from students.models import Student


class AnalyticsTestBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(code="CSE", name="Computer Science")
        cls.other_dept = Department.objects.create(code="ECE", name="Electronics")
        cls.program = Program.objects.create(
            code="BTECH-CSE", name="B.Tech CSE", department=cls.dept
        )
        cls.sem = Semester.objects.create(program=cls.program, number=5)
        cls.section = Section.objects.create(semester=cls.sem, name="A")
        cls.subject = Subject.objects.create(
            code="sub-ds", name="Data Structures", credits=4, department=cls.dept
        )

        # Users by role.
        cls.hod_user = User.objects.create_user(
            email="hod@x.io", password="pw", full_name="Dr HOD", role=Role.HOD
        )
        cls.principal_user = User.objects.create_user(
            email="principal@x.io", password="pw", full_name="Principal", role=Role.PRINCIPAL
        )
        cls.admin_user = User.objects.create_user(
            email="admin@x.io", password="pw", full_name="Admin", role=Role.ADMIN
        )
        cls.faculty_user = User.objects.create_user(
            email="fac@x.io", password="pw", full_name="Prof One", role=Role.FACULTY
        )
        cls.student_user = User.objects.create_user(
            email="stud@x.io", password="pw", full_name="Stud", role=Role.STUDENT
        )

        # HOD belongs to CSE via a faculty profile (department resolution).
        cls.hod_profile = FacultyProfile.objects.create(
            user=cls.hod_user, department=cls.dept, designation="HOD"
        )
        cls.fac_profile = FacultyProfile.objects.create(
            user=cls.faculty_user,
            department=cls.dept,
            designation="Assistant Professor",
        )

        cls.fclass = FacultyClass.objects.create(
            subject=cls.subject,
            semester=cls.sem,
            section=cls.section,
            faculty=cls.fac_profile,
            student_count=2,
        )

        # Two active CSE students.
        cls.s1 = Student.objects.create(
            roll_no="CSE001", full_name="Alice", department=cls.dept,
            program=cls.program, semester=cls.sem, section=cls.section,
            cgpa=Decimal("9.0"),
        )
        cls.s2 = Student.objects.create(
            roll_no="CSE002", full_name="Bob", department=cls.dept,
            program=cls.program, semester=cls.sem, section=cls.section,
            cgpa=Decimal("6.0"),
        )
        # One ECE student (should be excluded from HOD's CSE scope).
        cls.s3 = Student.objects.create(
            roll_no="ECE001", full_name="Carol", department=cls.other_dept,
            cgpa=Decimal("7.5"),
        )

        # Exam results (student marks %).
        ExamResult.objects.create(
            student=cls.s1, subject=cls.subject, exam="Internal 1",
            marks=Decimal("90"), max_marks=Decimal("100"),
        )
        ExamResult.objects.create(
            student=cls.s2, subject=cls.subject, exam="Internal 1",
            marks=Decimal("30"), max_marks=Decimal("100"),
        )

        # Attendance records.
        today = date.today()
        AttendanceRecord.objects.create(
            student=cls.s1, subject=cls.subject, date=today, status="present"
        )
        AttendanceRecord.objects.create(
            student=cls.s1, subject=cls.subject, date=today - timedelta(days=1),
            status="present",
        )
        AttendanceRecord.objects.create(
            student=cls.s2, subject=cls.subject, date=today, status="absent"
        )

        # A marks sheet + entries under the class (for faculty perf).
        sheet = MarksSheet.objects.create(
            faculty_class=cls.fclass, exam="Internal 1",
            max_marks=Decimal("100"), entered_on=timezone.now(),
        )
        MarkEntry.objects.create(sheet=sheet, student=cls.s1, marks=Decimal("90"))
        MarkEntry.objects.create(sheet=sheet, student=cls.s2, marks=Decimal("30"))
        AttendanceSession.objects.create(faculty_class=cls.fclass, date=today)

        # Fees.
        FeeInvoice.objects.create(
            student=cls.s1, title="Tuition", term="2026-1",
            amount=Decimal("50000"), status=FeeInvoice.STATUS_PAID,
        )
        FeeInvoice.objects.create(
            student=cls.s2, title="Tuition", term="2026-1",
            amount=Decimal("50000"), status=FeeInvoice.STATUS_DUE,
        )

        # Placement.
        opening = PlacementOpening.objects.create(
            company="Acme", role="SDE", ctc=Decimal("1200000"),
            last_date=today + timedelta(days=30),
        )
        PlacementApplication.objects.create(
            opening=opening, student=cls.s1,
            status=PlacementApplication.STATUS_SELECTED,
        )

        # Complaints.
        Complaint.objects.create(
            user=cls.student_user, category="Hostel", subject="Wifi",
            description="slow", status=Complaint.STATUS_OPEN,
        )
        Complaint.objects.create(
            user=cls.student_user, category="Fees", subject="Refund",
            description="pending", status=Complaint.STATUS_RESOLVED,
        )


class HodAnalyticsTests(AnalyticsTestBase):
    def test_dashboard_happy_path(self):
        self.client.force_authenticate(self.hod_user)
        res = self.client.get(reverse("analytics:hod-dashboard"))
        self.assertEqual(res.status_code, 200)
        data = res.json()["data"]
        self.assertEqual(data["department"], "Computer Science")
        self.assertEqual(data["studentCount"], 2)  # CSE only, ECE excluded
        self.assertEqual(data["facultyCount"], 2)  # hod + faculty profiles
        self.assertEqual(data["classCount"], 1)
        # Marks: 90% and 30% -> pass mark 40 -> 1 of 2 pass = 50%.
        self.assertEqual(data["passRatePercent"], 50.0)

    def test_faculty_performance(self):
        self.client.force_authenticate(self.hod_user)
        res = self.client.get(reverse("analytics:hod-faculty"))
        self.assertEqual(res.status_code, 200)
        rows = res.json()["data"]
        self.assertEqual(len(rows), 2)
        fac = next(r for r in rows if r["name"] == "Prof One")
        self.assertEqual(fac["classCount"], 1)
        self.assertEqual(fac["avgMarksPercent"], 60.0)  # (90+30)/2
        self.assertEqual(fac["sessionsMarked"], 1)

    def test_faculty_detail_and_404(self):
        self.client.force_authenticate(self.hod_user)
        ok = self.client.get(
            reverse("analytics:hod-faculty-detail", args=[self.fac_profile.id])
        )
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()["data"]["name"], "Prof One")
        missing = self.client.get(
            reverse(
                "analytics:hod-faculty-detail",
                args=["00000000-0000-0000-0000-000000000000"],
            )
        )
        self.assertEqual(missing.status_code, 404)

    def test_students_grade_bands(self):
        self.client.force_authenticate(self.hod_user)
        res = self.client.get(reverse("analytics:hod-students"))
        self.assertEqual(res.status_code, 200)
        data = res.json()["data"]
        bands = {b["band"]: b["count"] for b in data["gradeBands"]}
        self.assertEqual(bands["90-100"], 1)  # Alice 90%
        self.assertEqual(bands["<60"], 1)  # Bob 30%
        self.assertEqual(data["topPerformers"][0]["name"], "Alice")

    def test_attendance_analytics(self):
        self.client.force_authenticate(self.hod_user)
        res = self.client.get(reverse("analytics:hod-attendance"))
        self.assertEqual(res.status_code, 200)
        data = res.json()["data"]
        # 3 records, 2 attended -> 66.7%.
        self.assertEqual(data["overallPercent"], 66.7)
        self.assertTrue(any(s["rollNo"] == "CSE002" for s in data["lowStudents"]))

    def test_requires_auth(self):
        res = self.client.get(reverse("analytics:hod-dashboard"))
        self.assertEqual(res.status_code, 401)

    def test_student_forbidden(self):
        self.client.force_authenticate(self.student_user)
        res = self.client.get(reverse("analytics:hod-dashboard"))
        self.assertEqual(res.status_code, 403)

    def test_principal_forbidden_on_hod(self):
        self.client.force_authenticate(self.principal_user)
        res = self.client.get(reverse("analytics:hod-dashboard"))
        self.assertEqual(res.status_code, 403)


class PrincipalAnalyticsTests(AnalyticsTestBase):
    def test_dashboard_happy_path(self):
        self.client.force_authenticate(self.principal_user)
        res = self.client.get(reverse("analytics:principal-dashboard"))
        self.assertEqual(res.status_code, 200)
        data = res.json()["data"]
        self.assertEqual(data["totalStudents"], 3)
        self.assertEqual(data["departmentCount"], 2)
        # Fees: 50000 collected / 100000 target -> 50%.
        self.assertEqual(data["feeCollectedPercent"], 50.0)

    def test_admin_allowed(self):
        self.client.force_authenticate(self.admin_user)
        res = self.client.get(reverse("analytics:principal-dashboard"))
        self.assertEqual(res.status_code, 200)

    def test_students_analytics(self):
        self.client.force_authenticate(self.principal_user)
        res = self.client.get(reverse("analytics:principal-students"))
        self.assertEqual(res.status_code, 200)
        data = res.json()["data"]
        self.assertEqual(data["totalStudents"], 3)
        codes = {r["code"] for r in data["byDepartment"]}
        self.assertIn("CSE", codes)
        self.assertIn("ECE", codes)

    def test_faculty_analytics(self):
        self.client.force_authenticate(self.principal_user)
        res = self.client.get(reverse("analytics:principal-faculty"))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["data"]["totalFaculty"], 2)

    def test_fee_analytics(self):
        self.client.force_authenticate(self.principal_user)
        res = self.client.get(reverse("analytics:principal-fees"))
        self.assertEqual(res.status_code, 200)
        data = res.json()["data"]
        self.assertEqual(data["totalCollected"], 50000.0)
        self.assertEqual(data["totalTarget"], 100000.0)
        self.assertEqual(data["collectionPercent"], 50.0)

    def test_placement_analytics(self):
        self.client.force_authenticate(self.principal_user)
        res = self.client.get(reverse("analytics:principal-placements"))
        self.assertEqual(res.status_code, 200)
        data = res.json()["data"]
        self.assertEqual(data["summary"]["placed"], 1)
        self.assertEqual(data["openings"], 1)
        self.assertEqual(data["summary"]["highestCtcLpa"], 12.0)

    def test_complaint_monitoring(self):
        self.client.force_authenticate(self.principal_user)
        res = self.client.get(reverse("analytics:principal-complaints"))
        self.assertEqual(res.status_code, 200)
        data = res.json()["data"]
        self.assertEqual(data["total"], 2)
        self.assertEqual(len(data["recent"]), 2)

    def test_insights(self):
        self.client.force_authenticate(self.principal_user)
        res = self.client.get(reverse("analytics:principal-insights"))
        self.assertEqual(res.status_code, 200)
        cards = res.json()["data"]
        self.assertTrue(len(cards) >= 1)
        self.assertTrue(all("tone" in c for c in cards))

    def test_requires_auth(self):
        res = self.client.get(reverse("analytics:principal-dashboard"))
        self.assertEqual(res.status_code, 401)

    def test_hod_forbidden_on_principal(self):
        self.client.force_authenticate(self.hod_user)
        res = self.client.get(reverse("analytics:principal-dashboard"))
        self.assertEqual(res.status_code, 403)
