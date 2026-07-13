"""Fees endpoint tests: happy path + permission/validation cases.

The module's routes are not mounted in ``config/urls`` until the integrate step,
so these tests mount the router under a local ``ROOT_URLCONF`` for isolation.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import include, path, reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from core.models import AuditLog
from core.permissions import Role

from academics.models import Department, Program, Section, Semester
from students.models import Guardian, Student

from fees.models import FeeInvoice, Payment

User = get_user_model()

# Mount the full fees URL surface (router + the mobile-contract spec routes) so
# both the management endpoints and the {user_id}-parameterized spec endpoints
# resolve under the ``fees`` namespace.
urlpatterns = [path("", include("fees.urls"))]


@override_settings(ROOT_URLCONF=__name__)
class FeesAPITests(APITestCase):
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
        self.parent_user = User.objects.create_user(
            email="parent@example.com", password=pwd, full_name="Parent",
            role=Role.PARENT,
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
            department=self.dept, full_name="Neha",
        )
        # Link the parent to the student via a guardian contact email.
        Guardian.objects.create(
            student=self.student, name="Parent", relation="Father",
            email="parent@example.com", is_primary=True,
        )

        due = timezone.now().date() + timedelta(days=10)
        self.inv1 = FeeInvoice.objects.create(
            student=self.student, title="Tuition Term 1", term="2026-T1",
            amount=Decimal("50000.00"), due_date=due, status=FeeInvoice.STATUS_DUE,
        )
        self.inv2 = FeeInvoice.objects.create(
            student=self.student, title="Hostel Term 1", term="2026-T1",
            amount=Decimal("20000.00"), due_date=due, status=FeeInvoice.STATUS_DUE,
        )
        # Another student's invoice — must never leak to the first student.
        self.other_inv = FeeInvoice.objects.create(
            student=self.other_student, title="Tuition", term="2026-T1",
            amount=Decimal("9999.00"), due_date=due, status=FeeInvoice.STATUS_DUE,
        )

    # -- list (scoped) ---------------------------------------------------
    def test_student_lists_only_own_fees(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.get(reverse("fees:fee-list"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["pagination"]["count"], 2)
        titles = {row["title"] for row in resp.json()["data"]["results"]}
        self.assertNotIn("Tuition", titles - {"Tuition Term 1"})

    def test_list_requires_auth(self):
        self.assertEqual(self.client.get(reverse("fees:fee-list")).status_code, 401)

    def test_app_shape_camelcase(self):
        self.client.force_authenticate(self.student_user)
        row = self.client.get(reverse("fees:fee-list")).json()["data"]["results"][0]
        for key in ("id", "studentName", "student_name", "title", "term", "amount", "dueDate", "status"):
            self.assertIn(key, row)
        self.assertEqual(row["studentName"], "Abin Thomas")
        self.assertEqual(row["student_name"], "Abin Thomas")

    # -- total-due (scoped) ----------------------------------------------
    def test_total_due_scoped_to_student(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.get(reverse("fees:fee-total-due"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Decimal(str(resp.json()["data"]["total"])), Decimal("70000.00"))

    # -- pay -------------------------------------------------------------
    def test_parent_can_pay_child_invoice(self):
        self.client.force_authenticate(self.parent_user)
        resp = self.client.post(reverse("fees:fee-pay", args=[self.inv1.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["status"], "paid")
        self.inv1.refresh_from_db()
        self.assertEqual(self.inv1.status, FeeInvoice.STATUS_PAID)
        self.assertIsNotNone(self.inv1.paid_on)
        self.assertEqual(Payment.objects.filter(invoice=self.inv1).count(), 1)
        self.assertTrue(
            AuditLog.objects.filter(entity="FeeInvoice", action="create").exists()
        )

    def test_student_cannot_pay(self):
        # Students have read-only access; pay is parents/admins only.
        self.client.force_authenticate(self.student_user)
        resp = self.client.post(reverse("fees:fee-pay", args=[self.inv1.id]))
        self.assertEqual(resp.status_code, 403)

    def test_parent_cannot_pay_unrelated_invoice(self):
        self.client.force_authenticate(self.parent_user)
        resp = self.client.post(reverse("fees:fee-pay", args=[self.other_inv.id]))
        self.assertIn(resp.status_code, (403, 404))
        self.other_inv.refresh_from_db()
        self.assertEqual(self.other_inv.status, FeeInvoice.STATUS_DUE)

    # -- create RBAC + validation ----------------------------------------
    def test_admin_can_create_invoice(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            reverse("fees:fee-list"),
            {
                "student": str(self.student.id), "title": "Exam Fee",
                "term": "2026-T1", "amount": "1500.00",
                "dueDate": "2026-12-01",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(FeeInvoice.objects.filter(title="Exam Fee").exists())

    def test_student_cannot_create_invoice(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.post(
            reverse("fees:fee-list"),
            {"student": str(self.student.id), "title": "X", "amount": "1"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_create_validation_error(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            reverse("fees:fee-list"), {"title": "No amount"}, format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["status"], "error")

    # -- mobile API contract v1 endpoints --------------------------------
    def test_fees_by_user_spec_shape(self):
        """GET /fees/{user_id} → spec summary with snake_case invoice rows."""
        self.client.force_authenticate(self.student_user)
        resp = self.client.get(
            reverse("fees:fee-detail-spec", args=[self.student_user.id])
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(Decimal(str(data["total_due"])), Decimal("70000.00"))
        self.assertEqual(Decimal(str(data["paid_amount"])), Decimal("0"))
        self.assertEqual(Decimal(str(data["pending_amount"])), Decimal("70000.00"))
        self.assertEqual(len(data["invoices"]), 2)
        for key in ("id", "title", "term", "amount", "due_date", "status", "paid_on"):
            self.assertIn(key, data["invoices"][0])

    def test_fees_by_user_denies_other_user(self):
        """A student may not read another user's fees."""
        self.client.force_authenticate(self.student_user)
        resp = self.client.get(
            reverse("fees:fee-detail-spec", args=[self.other_student_user.id])
        )
        self.assertEqual(resp.status_code, 403)

    def test_fees_by_user_staff_any(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.get(
            reverse("fees:fee-detail-spec", args=[self.other_student_user.id])
        )
        self.assertEqual(resp.status_code, 200)

    def test_payment_and_receipt_flow(self):
        """POST /fees/payment → {payment_id, receipt_no}; receipt is fetchable."""
        self.client.force_authenticate(self.parent_user)
        resp = self.client.post(
            reverse("fees:fee-payment"),
            {"fee_id": str(self.inv1.id)},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        body = resp.json()["data"]
        self.assertIn("payment_id", body)
        self.assertTrue(body["receipt_no"].startswith("RCPT-"))
        self.inv1.refresh_from_db()
        self.assertEqual(self.inv1.status, FeeInvoice.STATUS_PAID)

        # The receipt is retrievable and carries spec fields.
        receipt = self.client.get(
            reverse("fees:fee-receipt", args=[body["payment_id"]])
        )
        self.assertEqual(receipt.status_code, 200)
        rdata = receipt.json()["data"]
        self.assertEqual(rdata["receipt_no"], body["receipt_no"])
        self.assertEqual(rdata["fee_id"], str(self.inv1.id))
        self.assertEqual(rdata["roll_no"], "CSE-001")

    def test_payment_denies_unrelated_invoice(self):
        self.client.force_authenticate(self.parent_user)
        resp = self.client.post(
            reverse("fees:fee-payment"),
            {"fee_id": str(self.other_inv.id)},
            format="json",
        )
        self.assertIn(resp.status_code, (403, 404))
        self.other_inv.refresh_from_db()
        self.assertEqual(self.other_inv.status, FeeInvoice.STATUS_DUE)
