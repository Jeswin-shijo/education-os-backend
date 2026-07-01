"""Hostel endpoint tests: happy path + permission/validation cases.

The module's routes are not mounted in ``config/urls`` until the integrate step,
so these tests mount the router under a local ``ROOT_URLCONF`` for isolation.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from django.urls import include, path, reverse
from rest_framework.test import APITestCase

from core.permissions import Role

from hostel.models import HostelAllocation, HostelBlock, HostelRoom
from hostel.urls import router
from students.models import Student

User = get_user_model()

urlpatterns = [path("", include((router.urls, "hostel"), namespace="hostel"))]


@override_settings(ROOT_URLCONF=__name__)
class HostelAPITests(APITestCase):
    def setUp(self):
        cache.clear()
        pwd = "Str0ng-Pass!23"
        self.admin = User.objects.create_user(
            email="admin@example.com", password=pwd, full_name="Admin",
            role=Role.ADMIN,
        )
        self.faculty = User.objects.create_user(
            email="fac@example.com", password=pwd, full_name="Fac",
            role=Role.FACULTY,
        )
        self.student_user = User.objects.create_user(
            email="abin@example.com", password=pwd, full_name="Abin Thomas",
            role=Role.STUDENT,
        )
        self.other_student_user = User.objects.create_user(
            email="neha@example.com", password=pwd, full_name="Neha",
            role=Role.STUDENT,
        )

        self.student = Student.objects.create(
            user=self.student_user, roll_no="CSE-001", full_name="Abin Thomas",
        )

        self.block = HostelBlock.objects.create(
            name="Block A", warden="Mr. Warden", warden_phone="9998887776",
        )
        self.room = HostelRoom.objects.create(
            block=self.block, room_no="A-101", capacity=2,
        )
        self.allocation = HostelAllocation.objects.create(
            student=self.student, room=self.room, bed="1",
            mess_plan="Veg", fees=Decimal("25000.00"),
        )

    # -- GET /hostel/info (app-shaped HostelInfo) -------------------------
    def test_student_info_app_shape(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.get(reverse("hostel:hostel-allocation-info"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["block"], "Block A")
        self.assertEqual(data["roomNo"], "A-101")
        self.assertEqual(data["bed"], "1")
        self.assertEqual(data["warden"], "Mr. Warden")
        self.assertEqual(data["wardenPhone"], "9998887776")
        self.assertEqual(data["messPlan"], "Veg")
        self.assertEqual(data["fees"], 25000.0)

    def test_info_404_when_no_allocation(self):
        self.client.force_authenticate(self.other_student_user)
        resp = self.client.get(reverse("hostel:hostel-allocation-info"))
        self.assertEqual(resp.status_code, 404)

    def test_info_requires_auth(self):
        self.assertEqual(
            self.client.get(reverse("hostel:hostel-allocation-info")).status_code,
            401,
        )

    # -- read RBAC (everyone reads) --------------------------------------
    def test_any_role_can_list_blocks(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.get(reverse("hostel:hostel-block-list"))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])
        self.assertGreaterEqual(
            resp.json()["meta"]["pagination"]["count"], 1
        )

    def test_room_filter_by_block(self):
        self.client.force_authenticate(self.faculty)
        resp = self.client.get(
            reverse("hostel:hostel-room-list"), {"block": str(self.block.id)}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["meta"]["pagination"]["count"], 1)

    # -- write RBAC + audit ----------------------------------------------
    def test_admin_can_create_block_and_it_is_audited(self):
        from core.models import AuditLog

        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            reverse("hostel:hostel-block-list"),
            {"name": "Block B", "warden": "Ms. W", "warden_phone": "111"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(HostelBlock.objects.filter(name="Block B").exists())
        self.assertTrue(
            AuditLog.objects.filter(entity="HostelBlock", action="create").exists()
        )

    def test_faculty_cannot_create_block(self):
        self.client.force_authenticate(self.faculty)
        resp = self.client.post(
            reverse("hostel:hostel-block-list"),
            {"name": "Block C"}, format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_student_cannot_create_allocation(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.post(
            reverse("hostel:hostel-allocation-list"),
            {"student": str(self.student.id), "room": str(self.room.id)},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_create_room_validation_error(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            reverse("hostel:hostel-room-list"),
            {"room_no": "X-1"},  # missing required block
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["success"])

    # -- cache invalidation on write -------------------------------------
    def test_info_cache_invalidated_on_allocation_update(self):
        self.client.force_authenticate(self.student_user)
        first = self.client.get(reverse("hostel:hostel-allocation-info"))
        self.assertEqual(first.json()["data"]["messPlan"], "Veg")

        # Admin updates the mess plan through the service (invalidates cache).
        self.client.force_authenticate(self.admin)
        upd = self.client.patch(
            reverse(
                "hostel:hostel-allocation-detail",
                args=[str(self.allocation.id)],
            ),
            {"mess_plan": "Non-Veg"},
            format="json",
        )
        self.assertEqual(upd.status_code, 200)

        self.client.force_authenticate(self.student_user)
        again = self.client.get(reverse("hostel:hostel-allocation-info"))
        self.assertEqual(again.json()["data"]["messPlan"], "Non-Veg")
