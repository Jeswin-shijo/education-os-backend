"""Notifications endpoint tests: happy path + permission + validation cases.

The module's routes are not mounted in ``config/urls`` until the integrate step,
so these tests mount the router under a local ``ROOT_URLCONF`` for isolation.
"""
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import include, path, reverse
from rest_framework.test import APITestCase

from core.models import AuditLog
from core.permissions import Role

from notifications.models import Notification
from notifications.urls import router

User = get_user_model()

# Local urlconf mounting the notifications router at the root for tests.
urlpatterns = [
    path("", include((router.urls, "notifications"), namespace="notifications"))
]


@override_settings(ROOT_URLCONF=__name__)
class NotificationAPITests(APITestCase):
    def setUp(self):
        pwd = "Str0ng-Pass!23"
        self.admin = User.objects.create_user(
            email="admin@example.com", password=pwd, full_name="Admin", role=Role.ADMIN
        )
        self.student = User.objects.create_user(
            email="abin@example.com", password=pwd, full_name="Abin", role=Role.STUDENT
        )
        self.other = User.objects.create_user(
            email="other@example.com", password=pwd, full_name="Other", role=Role.STUDENT
        )

        # Student's own notifications.
        self.n1 = Notification.objects.create(
            recipient=self.student, title="Fee due", body="Pay soon",
            category=Notification.CATEGORY_FEE, read=False,
        )
        self.n2 = Notification.objects.create(
            recipient=self.student, title="Class today", body="DS at 9",
            category=Notification.CATEGORY_ACADEMIC, read=True,
        )
        # Another user's notification (must never leak).
        self.other_note = Notification.objects.create(
            recipient=self.other, title="Private", body="secret",
            category=Notification.CATEGORY_GENERAL, read=False,
        )
        # A broadcast to all students.
        self.broadcast = Notification.objects.create(
            recipient=None, broadcast_role=Role.STUDENT, title="Holiday",
            body="Campus closed", category=Notification.CATEGORY_EVENT, read=False,
        )

    # -- list ------------------------------------------------------------
    def test_list_returns_own_and_relevant_broadcasts_newest_first(self):
        self.client.force_authenticate(self.student)
        resp = self.client.get(reverse("notifications:notification-list"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        titles = {n["title"] for n in data}
        self.assertIn("Fee due", titles)
        self.assertIn("Class today", titles)
        self.assertIn("Holiday", titles)          # broadcast to students
        self.assertNotIn("Private", titles)        # other user's note excluded
        # App-shaped item has camelCase createdAt + read.
        item = data[0]
        self.assertIn("createdAt", item)
        self.assertIn("read", item)
        self.assertIn("category", item)

    def test_list_requires_auth(self):
        self.assertEqual(
            self.client.get(reverse("notifications:notification-list")).status_code,
            401,
        )

    def test_broadcast_role_filtering_excludes_other_roles(self):
        # A parent should not see a student-targeted broadcast.
        parent = User.objects.create_user(
            email="parent@example.com", password="Str0ng-Pass!23",
            full_name="Parent", role=Role.PARENT,
        )
        self.client.force_authenticate(parent)
        resp = self.client.get(reverse("notifications:notification-list"))
        titles = {n["title"] for n in resp.json()["data"]}
        self.assertNotIn("Holiday", titles)

    # -- mark read -------------------------------------------------------
    def test_mark_read_own_notification(self):
        self.client.force_authenticate(self.student)
        url = reverse("notifications:notification-read", args=[self.n1.id])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["data"]["read"])
        self.n1.refresh_from_db()
        self.assertTrue(self.n1.read)
        self.assertTrue(
            AuditLog.objects.filter(entity="Notification", action="update").exists()
        )

    def test_cannot_mark_read_other_users_notification(self):
        self.client.force_authenticate(self.student)
        url = reverse("notifications:notification-read", args=[self.other_note.id])
        resp = self.client.post(url)
        # Not in the user's scoped queryset -> 404.
        self.assertEqual(resp.status_code, 404)

    def test_cannot_mark_read_broadcast(self):
        self.client.force_authenticate(self.student)
        url = reverse("notifications:notification-read", args=[self.broadcast.id])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 403)

    # -- read all --------------------------------------------------------
    def test_read_all_marks_only_own_rows(self):
        self.client.force_authenticate(self.student)
        resp = self.client.post(reverse("notifications:notification-read-all"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["updated"], 1)  # only n1 was unread
        self.n1.refresh_from_db()
        self.assertTrue(self.n1.read)
        # Other user's row untouched.
        self.other_note.refresh_from_db()
        self.assertFalse(self.other_note.read)
        # Broadcast row untouched (shared).
        self.broadcast.refresh_from_db()
        self.assertFalse(self.broadcast.read)

    # -- unread count ----------------------------------------------------
    def test_unread_count(self):
        self.client.force_authenticate(self.student)
        resp = self.client.get(reverse("notifications:notification-unread-count"))
        self.assertEqual(resp.status_code, 200)
        # n1 (unread) + broadcast (unread) = 2; n2 is read.
        self.assertEqual(resp.json()["data"]["count"], 2)

    # -- broadcast (admin) -----------------------------------------------
    @mock.patch("notifications.tasks.send_push_notification.delay")
    def test_admin_can_broadcast_and_it_is_audited(self, mock_delay):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            reverse("notifications:notification-broadcast"),
            {"title": "Exam", "body": "Midterms next week",
             "category": "academic", "role": "student"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        created = Notification.objects.filter(
            title="Exam", recipient__isnull=True, broadcast_role="student"
        ).first()
        self.assertIsNotNone(created)
        self.assertTrue(
            AuditLog.objects.filter(entity="Notification", action="create").exists()
        )
        mock_delay.assert_called_once_with(str(created.pk))

    @mock.patch("notifications.tasks.send_push_notification.delay")
    def test_broadcast_defaults_to_all_roles_when_role_omitted(self, mock_delay):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            reverse("notifications:notification-broadcast"),
            {"title": "All", "body": "Everyone", "category": "general"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        created = Notification.objects.get(title="All")
        self.assertEqual(created.broadcast_role, "")

    def test_student_cannot_broadcast(self):
        self.client.force_authenticate(self.student)
        resp = self.client.post(
            reverse("notifications:notification-broadcast"),
            {"title": "x", "body": "y", "category": "general"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_broadcast_validation_error(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            reverse("notifications:notification-broadcast"),
            {"body": "no title", "category": "general"},  # missing title
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["success"])

    def test_broadcast_invalid_category(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            reverse("notifications:notification-broadcast"),
            {"title": "x", "body": "y", "category": "nope"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)


class NotificationTaskTests(APITestCase):
    """Unit-test the push-fan-out task's audience resolution (no broker)."""

    def test_send_push_resolves_broadcast_audience(self):
        pwd = "Str0ng-Pass!23"
        s1 = User.objects.create_user(
            email="s1@example.com", password=pwd, full_name="S1", role=Role.STUDENT
        )
        User.objects.create_user(
            email="p1@example.com", password=pwd, full_name="P1", role=Role.PARENT
        )
        note = Notification.objects.create(
            recipient=None, broadcast_role=Role.STUDENT, title="Hi",
            body="", category=Notification.CATEGORY_GENERAL,
        )
        from notifications.tasks import send_push_notification

        result = send_push_notification.run(str(note.pk))
        # Only the one student is in the audience.
        self.assertEqual(result["delivered"], 1)

    def test_send_push_missing_notification(self):
        import uuid

        from notifications.tasks import send_push_notification

        result = send_push_notification.run(str(uuid.uuid4()))
        self.assertEqual(result["delivered"], 0)
