"""Leave endpoint tests: apply + own list + approve/reject workflow, with
permission/validation and object-scoping cases.

The module's routes are not mounted in ``config/urls`` until the integrate step,
so these tests mount the urlpatterns under a local ``ROOT_URLCONF``.
"""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import include, path
from rest_framework.test import APITestCase

from core.models import AuditLog
from core.permissions import Role

from academics.models import Department, Program, Section, Semester
from faculty.models import FacultyProfile
from guardians.models import ParentLink
from students.models import Student

from leave.models import LeaveRequest
from leave.urls import urlpatterns as leave_urlpatterns

User = get_user_model()

urlpatterns = [
    path("", include((leave_urlpatterns, "leave"), namespace="leave")),
]

PWD = "Str0ng-Pass!23"


@override_settings(ROOT_URLCONF=__name__)
class LeaveAPITests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@example.com", password=PWD, full_name="Admin", role=Role.ADMIN
        )
        self.student_user = User.objects.create_user(
            email="abin@example.com", password=PWD, full_name="Abin", role=Role.STUDENT
        )
        self.other_student_user = User.objects.create_user(
            email="neha@example.com", password=PWD, full_name="Neha", role=Role.STUDENT
        )
        self.parent_user = User.objects.create_user(
            email="dad@example.com", password=PWD, full_name="Dad", role=Role.PARENT
        )
        self.faculty_user = User.objects.create_user(
            email="rao@example.com", password=PWD, full_name="Dr. Rao", role=Role.FACULTY
        )
        self.other_faculty_user = User.objects.create_user(
            email="menon@example.com", password=PWD, full_name="Dr. Menon",
            role=Role.FACULTY,
        )

        self.dept = Department.objects.create(code="CSE", name="Computer Science")
        self.other_dept = Department.objects.create(code="ECE", name="Electronics")
        self.program = Program.objects.create(
            code="BTCSE", name="B.Tech CSE", department=self.dept,
            duration_years=4, intake=60,
        )
        self.sem = Semester.objects.create(program=self.program, number=5)
        self.section = Section.objects.create(semester=self.sem, name="A")

        self.student = Student.objects.create(
            user=self.student_user, roll_no="CSE-001", full_name="Abin",
            department=self.dept, program=self.program, semester=self.sem,
            section=self.section,
        )
        self.other_student = Student.objects.create(
            user=self.other_student_user, roll_no="ECE-001", full_name="Neha",
            department=self.other_dept,
        )

        ParentLink.objects.create(
            parent=self.parent_user, student=self.student,
            relation=ParentLink.RELATION_FATHER,
        )
        FacultyProfile.objects.create(
            user=self.faculty_user, department=self.dept, designation="Prof",
        )
        FacultyProfile.objects.create(
            user=self.other_faculty_user, department=self.other_dept,
            designation="Prof",
        )

        self.today = date(2026, 7, 1)

    # -- helpers ---------------------------------------------------------
    def _apply_body(self, **over):
        body = {
            "type": "casual",
            "from": self.today.isoformat(),
            "to": (self.today + timedelta(days=2)).isoformat(),
            "reason": "Family function",
        }
        body.update(over)
        return body

    def _make_leave(self, user, status=LeaveRequest.STATUS_PENDING):
        return LeaveRequest.objects.create(
            user=user, type=LeaveRequest.TYPE_CASUAL,
            start_date=self.today, end_date=self.today + timedelta(days=1),
            reason="x", status=status,
        )

    # -- apply -----------------------------------------------------------
    def test_student_apply_creates_pending(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.post("/leaves/", self._apply_body(), format="json")
        self.assertEqual(resp.status_code, 201, resp.data)
        data = resp.json()["data"]
        self.assertEqual(data["status"], "pending")
        self.assertEqual(data["from"], self.today.isoformat())
        self.assertEqual(data["type"], "casual")
        leave = LeaveRequest.objects.get(id=data["id"])
        self.assertEqual(leave.user, self.student_user)
        self.assertTrue(
            AuditLog.objects.filter(
                entity="LeaveRequest", action=AuditLog.ACTION_CREATE
            ).exists()
        )

    def test_apply_rejects_reversed_dates(self):
        self.client.force_authenticate(self.student_user)
        body = self._apply_body(
            **{"from": self.today.isoformat(),
               "to": (self.today - timedelta(days=1)).isoformat()}
        )
        resp = self.client.post("/leaves/", body, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_principal_cannot_apply(self):
        principal = User.objects.create_user(
            email="p@example.com", password=PWD, full_name="P", role=Role.PRINCIPAL
        )
        self.client.force_authenticate(principal)
        resp = self.client.post("/leaves/", self._apply_body(), format="json")
        self.assertEqual(resp.status_code, 403)

    # -- list scoping ----------------------------------------------------
    def test_student_lists_only_own(self):
        self._make_leave(self.student_user)
        self._make_leave(self.other_student_user)
        self.client.force_authenticate(self.student_user)
        resp = self.client.get("/leaves/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["data"]), 1)

    def test_parent_sees_child_requests(self):
        self._make_leave(self.student_user)
        self._make_leave(self.other_student_user)
        self.client.force_authenticate(self.parent_user)
        resp = self.client.get("/leaves/")
        self.assertEqual(resp.status_code, 200)
        # Only the linked child's request.
        self.assertEqual(len(resp.json()["data"]), 1)

    def test_faculty_sees_department_requests(self):
        self._make_leave(self.student_user)       # CSE
        self._make_leave(self.other_student_user)  # ECE
        self.client.force_authenticate(self.faculty_user)
        resp = self.client.get("/leaves/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["data"]), 1)

    # -- approve / reject scoping ---------------------------------------
    def test_parent_approves_child(self):
        leave = self._make_leave(self.student_user)
        self.client.force_authenticate(self.parent_user)
        resp = self.client.post(f"/leaves/{leave.id}/approve/")
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.json()["data"]["status"], "approved")
        leave.refresh_from_db()
        self.assertEqual(leave.decided_by, self.parent_user)

    def test_parent_cannot_approve_unlinked_student(self):
        leave = self._make_leave(self.other_student_user)
        self.client.force_authenticate(self.parent_user)
        resp = self.client.post(f"/leaves/{leave.id}/approve/")
        # Not in visible queryset -> 404 (object hidden from this approver).
        self.assertIn(resp.status_code, (403, 404))

    def test_faculty_approves_department_student(self):
        leave = self._make_leave(self.student_user)
        self.client.force_authenticate(self.faculty_user)
        resp = self.client.post(f"/leaves/{leave.id}/approve/")
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.json()["data"]["status"], "approved")

    def test_faculty_cannot_approve_other_department(self):
        leave = self._make_leave(self.other_student_user)
        self.client.force_authenticate(self.faculty_user)
        resp = self.client.post(f"/leaves/{leave.id}/approve/")
        self.assertIn(resp.status_code, (403, 404))

    def test_admin_rejects_any(self):
        leave = self._make_leave(self.other_student_user)
        self.client.force_authenticate(self.admin)
        resp = self.client.post(f"/leaves/{leave.id}/reject/")
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.json()["data"]["status"], "rejected")

    def test_cannot_decide_already_decided(self):
        leave = self._make_leave(
            self.student_user, status=LeaveRequest.STATUS_APPROVED
        )
        self.client.force_authenticate(self.admin)
        resp = self.client.post(f"/leaves/{leave.id}/approve/")
        self.assertEqual(resp.status_code, 400)

    def test_cannot_approve_own_request(self):
        leave = self._make_leave(self.faculty_user)
        self.client.force_authenticate(self.faculty_user)
        resp = self.client.post(f"/leaves/{leave.id}/approve/")
        self.assertEqual(resp.status_code, 403)

    def test_unauthenticated_denied(self):
        resp = self.client.get("/leaves/")
        self.assertEqual(resp.status_code, 401)
