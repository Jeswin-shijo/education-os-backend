"""Events endpoint tests: happy path + permission + validation + toggle cases.

The module's routes are not mounted in ``config/urls`` until the integrate step,
so these tests mount the urlconf under a local ``ROOT_URLCONF`` for isolation.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import include, path, reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from core.permissions import Role

from events.models import Event, EventRegistration
from events.urls import urlpatterns as events_urlpatterns

User = get_user_model()

urlpatterns = [path("", include((events_urlpatterns, "events"), namespace="events"))]


@override_settings(ROOT_URLCONF=__name__)
class EventsAPITests(APITestCase):
    def setUp(self):
        pwd = "Str0ng-Pass!23"
        self.admin = User.objects.create_user(
            email="admin@example.com", password=pwd, full_name="Admin", role=Role.ADMIN
        )
        self.student_user = User.objects.create_user(
            email="abin@example.com", password=pwd, full_name="Abin Thomas",
            role=Role.STUDENT,
        )
        self.other_student = User.objects.create_user(
            email="neha@example.com", password=pwd, full_name="Neha", role=Role.STUDENT
        )

        today = timezone.localdate()
        self.event = Event.objects.create(
            title="Hackathon 2026", date=today + timedelta(days=7),
            time="10:00 AM", venue="Main Auditorium", category=Event.CATEGORY_TECH,
            description="24-hour hackathon.",
        )
        Event.objects.create(
            title="Cultural Fest", date=today + timedelta(days=14),
            time="6:00 PM", venue="Open Grounds", category=Event.CATEGORY_CULTURAL,
        )

    # -- GET /events (app-shaped, all roles) ------------------------------
    def test_student_can_list_events(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.get(reverse("events:event-list"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "success")
        data = resp.json()["data"]
        self.assertEqual(len(data), 2)
        self.assertEqual(
            set(data[0].keys()),
            {"id", "title", "date", "time", "venue", "category", "registered"},
        )
        # Ordered by date: Hackathon first.
        self.assertEqual(data[0]["title"], "Hackathon 2026")
        self.assertFalse(data[0]["registered"])

    def test_events_requires_auth(self):
        self.assertEqual(
            self.client.get(reverse("events:event-list")).status_code, 401
        )

    # -- POST /events/{id}/register (toggle) ------------------------------
    def test_register_toggles_on_and_off(self):
        self.client.force_authenticate(self.student_user)
        url = reverse("events:event-register", args=[self.event.id])

        # First call registers.
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["data"]["registered"])
        self.assertEqual(
            EventRegistration.objects.filter(
                event=self.event, user=self.student_user
            ).count(),
            1,
        )

        # Second call unregisters (soft-delete).
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["data"]["registered"])
        self.assertEqual(
            EventRegistration.objects.filter(
                event=self.event, user=self.student_user
            ).count(),
            0,
        )

    def test_register_reuses_soft_deleted_row(self):
        self.client.force_authenticate(self.student_user)
        url = reverse("events:event-register", args=[self.event.id])
        self.client.post(url)   # register
        self.client.post(url)   # unregister
        self.client.post(url)   # register again -> reuse stale row

        self.assertEqual(
            EventRegistration.all_objects.filter(
                event=self.event, user=self.student_user
            ).count(),
            1,
        )
        self.assertEqual(
            EventRegistration.objects.filter(
                event=self.event, user=self.student_user
            ).count(),
            1,
        )

    def test_registration_is_per_user(self):
        self.client.force_authenticate(self.student_user)
        self.client.post(reverse("events:event-register", args=[self.event.id]))

        # Other student's list should show not-registered.
        self.client.force_authenticate(self.other_student)
        resp = self.client.get(reverse("events:event-list"))
        row = next(r for r in resp.json()["data"] if r["id"] == str(self.event.id))
        self.assertFalse(row["registered"])

    def test_register_is_audited(self):
        from core.models import AuditLog

        self.client.force_authenticate(self.student_user)
        self.client.post(reverse("events:event-register", args=[self.event.id]))
        self.assertTrue(
            AuditLog.objects.filter(
                entity="EventRegistration", action="create"
            ).exists()
        )

    # -- Admin event CRUD (RBAC + audit) ----------------------------------
    def test_admin_can_create_event_and_it_is_audited(self):
        from core.models import AuditLog

        self.client.force_authenticate(self.admin)
        # Admin CRUD lives under the router basename "event".
        resp = self.client.post(
            "/events-admin/",
            {
                "title": "Sports Day", "date": str(timezone.localdate()),
                "time": "9:00 AM", "venue": "Stadium", "category": "sports",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(Event.objects.filter(title="Sports Day").exists())
        self.assertTrue(
            AuditLog.objects.filter(entity="Event", action="create").exists()
        )

    def test_student_cannot_create_event(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.post(
            "/events-admin/",
            {"title": "Nope", "date": str(timezone.localdate()), "category": "tech"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_create_event_validation_error(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            "/events-admin/",
            {"title": "Missing Date", "category": "tech"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["status"], "error")

    def test_admin_can_update_and_delete_event(self):
        self.client.force_authenticate(self.admin)
        detail = f"/events-admin/{self.event.id}/"
        resp = self.client.patch(detail, {"venue": "New Hall"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.event.refresh_from_db()
        self.assertEqual(self.event.venue, "New Hall")

        resp = self.client.delete(detail)
        self.assertEqual(resp.status_code, 204)
        # Soft-deleted: hidden from default manager, present in all_objects.
        self.assertFalse(Event.objects.filter(id=self.event.id).exists())
        self.assertTrue(Event.all_objects.filter(id=self.event.id).exists())
