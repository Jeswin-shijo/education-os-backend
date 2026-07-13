"""Attendance endpoint tests: happy paths + permission/validation cases.

The module's routes are not mounted in ``config/urls`` until the integrate step,
so these tests mount the urlconf under a local ``ROOT_URLCONF`` for isolation.
"""
from datetime import date

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import include, path, reverse
from rest_framework.test import APITestCase

from core.permissions import Role

from academics.models import Department, Program, Section, Semester, Subject
from faculty.models import FacultyClass, FacultyProfile, RosterEntry
from students.models import Student

from attendance.models import AttendanceRecord, AttendanceSession
import attendance.urls as attendance_urls

User = get_user_model()

# Local urlconf mounting the attendance routes at the root for tests.
urlpatterns = [
    path("", include((attendance_urls.urlpatterns, "attendance"), namespace="attendance"))
]


@override_settings(ROOT_URLCONF=__name__)
class AttendanceAPITests(APITestCase):
    def setUp(self):
        pwd = "Str0ng-Pass!23"
        self.admin = User.objects.create_user(
            email="admin@example.com", password=pwd, full_name="Admin", role=Role.ADMIN
        )
        self.student_user = User.objects.create_user(
            email="abin@example.com", password=pwd, full_name="Abin", role=Role.STUDENT
        )
        self.faculty_user = User.objects.create_user(
            email="rao@example.com", password=pwd, full_name="Dr. Rao",
            role=Role.FACULTY,
        )
        self.other_faculty_user = User.objects.create_user(
            email="menon@example.com", password=pwd, full_name="Dr. Menon",
            role=Role.FACULTY,
        )

        # Academic structure.
        self.dept = Department.objects.create(code="CSE", name="Computer Science")
        self.program = Program.objects.create(
            code="BTCSE", name="B.Tech CSE", department=self.dept,
            duration_years=4, intake=60,
        )
        self.sem = Semester.objects.create(program=self.program, number=5)
        self.section = Section.objects.create(semester=self.sem, name="A")
        self.ds = Subject.objects.create(
            code="sub-ds", name="Data Structures", credits=4,
            department=self.dept, color="#2563EB",
        )
        self.os = Subject.objects.create(
            code="sub-os", name="Operating Systems", credits=3,
            department=self.dept, color="#F59E0B",
        )

        # Student profile linked to the student user.
        self.student = Student.objects.create(
            user=self.student_user, roll_no="CSE001", full_name="Abin Thomas",
            department=self.dept, program=self.program, semester=self.sem,
            section=self.section, email="abin@example.com",
        )

        # Attendance records: DS 4/5 (one absent), OS 3/3.
        for d, st in [
            (date(2026, 6, 1), "present"),
            (date(2026, 6, 2), "present"),
            (date(2026, 6, 3), "late"),
            (date(2026, 6, 4), "present"),
            (date(2026, 6, 5), "absent"),
        ]:
            AttendanceRecord.objects.create(
                student=self.student, subject=self.ds, date=d, status=st
            )
        for d in [date(2026, 6, 1), date(2026, 6, 2), date(2026, 6, 3)]:
            AttendanceRecord.objects.create(
                student=self.student, subject=self.os, date=d, status="present"
            )

        # Faculty class owned by faculty_user + roster.
        self.profile = FacultyProfile.objects.create(
            user=self.faculty_user, department=self.dept,
            designation="Associate Professor", subject_codes=["sub-ds"],
        )
        self.klass = FacultyClass.objects.create(
            subject=self.ds, semester=self.sem, section=self.section,
            faculty=self.profile, color="#2563EB", student_count=1,
        )
        self.roster = RosterEntry.objects.create(
            faculty_class=self.klass, student_ref=self.student.id,
            roll_no="CSE001", student_name="Abin Thomas", avatar_color="#2563EB",
        )
        # Another faculty's class (for owner-scoping checks).
        self.other_profile = FacultyProfile.objects.create(
            user=self.other_faculty_user, department=self.dept,
            designation="Assistant Professor", subject_codes=["sub-os"],
        )
        self.other_klass = FacultyClass.objects.create(
            subject=self.os, semester=self.sem, section=self.section,
            faculty=self.other_profile, color="#F59E0B", student_count=0,
        )

    # -- student self-scoped reads --------------------------------------
    def test_summary_per_subject(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.get(reverse("attendance:attendance-summary"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        by_subject = {r["subjectId"]: r for r in data}
        ds = by_subject[str(self.ds.id)]
        # present+present+late+present = 4 attended of 5 total → 80%.
        self.assertEqual(ds["attended"], 4)
        self.assertEqual(ds["total"], 5)
        self.assertEqual(ds["percent"], 80)
        self.assertEqual(ds["subjectName"], "Data Structures")
        os_row = by_subject[str(self.os.id)]
        self.assertEqual(os_row["percent"], 100)

    def test_overall_percent(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.get(reverse("attendance:attendance-overall"))
        self.assertEqual(resp.status_code, 200)
        # 7 attended of 8 total → round(87.5) = 88.
        self.assertEqual(resp.json()["data"]["percent"], 88)

    def test_records_filtered_by_subject(self):
        self.client.force_authenticate(self.student_user)
        url = reverse("attendance:attendance-records")
        resp = self.client.get(url, {"subjectId": str(self.ds.id)})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(len(data), 5)
        self.assertTrue(all(r["subjectId"] == str(self.ds.id) for r in data))
        self.assertIn("status", data[0])
        self.assertIn("date", data[0])

    def test_records_all_when_no_filter(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.get(reverse("attendance:attendance-records"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["data"]), 8)

    def test_summary_requires_auth(self):
        self.assertEqual(
            self.client.get(reverse("attendance:attendance-summary")).status_code,
            401,
        )

    def test_summary_404_when_no_student_profile(self):
        # Faculty user has no linked Student profile.
        self.client.force_authenticate(self.faculty_user)
        resp = self.client.get(reverse("attendance:attendance-summary"))
        self.assertEqual(resp.status_code, 404)

    # -- faculty save-session -------------------------------------------
    def test_faculty_saves_session_and_audits(self):
        from core.models import AuditLog

        self.client.force_authenticate(self.faculty_user)
        body = {
            "classId": str(self.klass.id),
            "date": "2026-06-10",
            "entries": [{"studentId": str(self.student.id), "status": "present"}],
        }
        resp = self.client.post(
            reverse("attendance:attendance-save-session"), body, format="json"
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()["data"]
        self.assertEqual(data["classId"], str(self.klass.id))
        self.assertEqual(len(data["entries"]), 1)
        self.assertEqual(data["entries"][0]["studentId"], str(self.student.id))
        self.assertEqual(data["entries"][0]["status"], "present")
        self.assertTrue(
            AttendanceSession.objects.filter(faculty_class=self.klass).exists()
        )
        self.assertTrue(
            AuditLog.objects.filter(entity="AttendanceSession", action="create").exists()
        )

    def test_save_session_upserts_by_class_and_date(self):
        self.client.force_authenticate(self.faculty_user)
        url = reverse("attendance:attendance-save-session")
        body = {
            "classId": str(self.klass.id),
            "date": "2026-06-11",
            "entries": [{"studentId": str(self.student.id), "status": "present"}],
        }
        self.client.post(url, body, format="json")
        body["entries"] = [{"studentId": str(self.student.id), "status": "absent"}]
        resp = self.client.post(url, body, format="json")
        self.assertEqual(resp.status_code, 201)
        # Only one session for that (class, date); entry updated to absent.
        self.assertEqual(
            AttendanceSession.objects.filter(
                faculty_class=self.klass, date=date(2026, 6, 11)
            ).count(),
            1,
        )
        self.assertEqual(resp.json()["data"]["entries"][0]["status"], "absent")

    def test_faculty_cannot_save_for_other_class(self):
        self.client.force_authenticate(self.faculty_user)
        body = {
            "classId": str(self.other_klass.id),
            "date": "2026-06-10",
            "entries": [{"studentId": str(self.student.id), "status": "present"}],
        }
        resp = self.client.post(
            reverse("attendance:attendance-save-session"), body, format="json"
        )
        self.assertEqual(resp.status_code, 403)

    def test_student_cannot_save_session(self):
        self.client.force_authenticate(self.student_user)
        body = {
            "classId": str(self.klass.id),
            "date": "2026-06-10",
            "entries": [{"studentId": str(self.student.id), "status": "present"}],
        }
        resp = self.client.post(
            reverse("attendance:attendance-save-session"), body, format="json"
        )
        self.assertEqual(resp.status_code, 403)

    def test_save_session_validation_error(self):
        self.client.force_authenticate(self.faculty_user)
        body = {"classId": str(self.klass.id), "date": "2026-06-10", "entries": []}
        resp = self.client.post(
            reverse("attendance:attendance-save-session"), body, format="json"
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["status"], "error")

    # -- faculty session list -------------------------------------------
    def test_faculty_lists_own_sessions(self):
        # Seed a session.
        self.client.force_authenticate(self.faculty_user)
        self.client.post(
            reverse("attendance:attendance-save-session"),
            {
                "classId": str(self.klass.id),
                "date": "2026-06-12",
                "entries": [{"studentId": str(self.student.id), "status": "late"}],
            },
            format="json",
        )
        resp = self.client.get(
            reverse("attendance:attendance-faculty-sessions"),
            {"classId": str(self.klass.id)},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["classId"], str(self.klass.id))

    def test_faculty_sessions_owner_scoped(self):
        self.client.force_authenticate(self.faculty_user)
        resp = self.client.get(
            reverse("attendance:attendance-faculty-sessions"),
            {"classId": str(self.other_klass.id)},
        )
        self.assertEqual(resp.status_code, 403)


@override_settings(ROOT_URLCONF=__name__)
class AttendanceAnalyticsTests(APITestCase):
    """The staff/admin ``GET /attendance/analytics`` rollups for the admin graph."""

    def setUp(self):
        from django.core.cache import cache

        # LocMemCache persists across tests in-process; the analytics payload is
        # cached under ``attendance:analytics`` so clear it for deterministic runs.
        cache.clear()

        pwd = "Str0ng-Pass!23"
        self.admin = User.objects.create_user(
            email="admin@example.com", password=pwd, full_name="Admin", role=Role.ADMIN
        )
        self.student_user = User.objects.create_user(
            email="abin@example.com", password=pwd, full_name="Abin", role=Role.STUDENT
        )
        self.rao = User.objects.create_user(
            email="rao@example.com", password=pwd, full_name="Dr. Rao", role=Role.FACULTY
        )
        self.menon = User.objects.create_user(
            email="menon@example.com", password=pwd, full_name="Dr. Menon",
            role=Role.FACULTY,
        )

        self.dept = Department.objects.create(code="CSE", name="Computer Science")
        self.program = Program.objects.create(
            code="BTCSE", name="B.Tech CSE", department=self.dept,
            duration_years=4, intake=60,
        )
        self.sem = Semester.objects.create(program=self.program, number=5)
        self.section = Section.objects.create(semester=self.sem, name="A")
        # Subjects carry semester (→ program) + assigned faculty so the
        # by_program / by_faculty joins have real buckets.
        self.ds = Subject.objects.create(
            code="sub-ds", name="Data Structures", credits=4,
            department=self.dept, semester=self.sem, faculty=self.rao,
        )
        self.os = Subject.objects.create(
            code="sub-os", name="Operating Systems", credits=3,
            department=self.dept, semester=self.sem, faculty=self.menon,
        )
        self.student = Student.objects.create(
            user=self.student_user, roll_no="CSE001", full_name="Abin Thomas",
            department=self.dept, program=self.program, semester=self.sem,
            section=self.section, email="abin@example.com",
        )
        # DS: 4 attended / 5 total → 80%; OS: 3 / 3 → 100%. Dept/program: 7/8 → 88%.
        for d, st in [
            (date(2026, 6, 1), "present"),
            (date(2026, 6, 2), "present"),
            (date(2026, 6, 3), "late"),
            (date(2026, 6, 4), "present"),
            (date(2026, 6, 5), "absent"),
        ]:
            AttendanceRecord.objects.create(
                student=self.student, subject=self.ds, date=d, status=st
            )
        for d in [date(2026, 6, 1), date(2026, 6, 2), date(2026, 6, 3)]:
            AttendanceRecord.objects.create(
                student=self.student, subject=self.os, date=d, status="present"
            )

    def test_analytics_rollups_for_admin(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.get(reverse("attendance:attendance-analytics"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]

        # Overall 7/8 → round(87.5) = 88.
        self.assertEqual(data["overall_percent"], 88)

        by_dept = {r["code"]: r for r in data["by_department"]}
        self.assertEqual(by_dept["CSE"]["name"], "Computer Science")
        self.assertEqual(by_dept["CSE"]["percent"], 88)

        by_prog = {r["code"]: r for r in data["by_program"]}
        self.assertEqual(by_prog["BTCSE"]["name"], "B.Tech CSE")
        self.assertEqual(by_prog["BTCSE"]["percent"], 88)

        by_fac = {r["name"]: r for r in data["by_faculty"]}
        self.assertEqual(by_fac["Dr. Rao"]["id"], str(self.rao.id))
        self.assertEqual(by_fac["Dr. Rao"]["percent"], 80)
        self.assertEqual(by_fac["Dr. Menon"]["percent"], 100)

    def test_analytics_forbidden_for_student(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.get(reverse("attendance:attendance-analytics"))
        self.assertEqual(resp.status_code, 403)

    def test_analytics_requires_auth(self):
        resp = self.client.get(reverse("attendance:attendance-analytics"))
        self.assertEqual(resp.status_code, 401)

    def test_analytics_empty_data_graceful(self):
        AttendanceRecord.objects.all().delete()
        from django.core.cache import cache

        cache.clear()
        self.client.force_authenticate(self.admin)
        resp = self.client.get(reverse("attendance:attendance-analytics"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["overall_percent"], 0)
        self.assertEqual(data["by_department"], [])
        self.assertEqual(data["by_program"], [])
        self.assertEqual(data["by_faculty"], [])
