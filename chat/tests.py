"""Chat endpoint tests: happy path + auth/permission + validation.

The module's routes are not mounted in ``config/urls`` until the integrate step,
so these tests mount the router under a local ``ROOT_URLCONF`` for isolation.
"""
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import include, path, reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from core.models import AuditLog
from core.permissions import Role

from chat.models import ChatMessage, ChatThread
from chat.urls import router

User = get_user_model()

# Local urlconf mounting the chat router at the root for tests.
urlpatterns = [path("", include((router.urls, "chat"), namespace="chat"))]


@override_settings(ROOT_URLCONF=__name__)
class ChatAPITests(APITestCase):
    def setUp(self):
        pwd = "Str0ng-Pass!23"
        self.admin = User.objects.create_user(
            email="admin@example.com", password=pwd, full_name="Admin", role=Role.ADMIN
        )
        self.teacher = User.objects.create_user(
            email="rao@example.com", password=pwd, full_name="Dr. Rao",
            role=Role.FACULTY, avatar_color="#2563EB",
        )
        self.parent = User.objects.create_user(
            email="parent@example.com", password=pwd, full_name="Mr. Thomas",
            role=Role.PARENT,
        )
        # A parent NOT party to the thread below.
        self.other_parent = User.objects.create_user(
            email="other@example.com", password=pwd, full_name="Other Parent",
            role=Role.PARENT,
        )

        self.thread = ChatThread.objects.create(
            teacher=self.teacher,
            parent=self.parent,
            teacher_name="Dr. Rao",
            subject_label="Data Structures",
            avatar_color="#2563EB",
            last_message_at=timezone.now(),
            unread_count={str(self.parent.id): 1},
        )
        ChatMessage.objects.create(
            thread=self.thread, sender=self.teacher,
            sender_role=ChatMessage.SENDER_TEACHER,
            text="Please review the syllabus.", at=timezone.now(), read=False,
        )

    # -- auth -------------------------------------------------------------
    def test_list_requires_auth(self):
        self.assertEqual(
            self.client.get(reverse("chat:chat-threads-list")).status_code, 401
        )

    # -- list (participant scoping) --------------------------------------
    def test_parent_sees_own_thread_with_app_shape(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.get(reverse("chat:chat-threads-list"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(len(data), 1)
        row = data[0]
        self.assertEqual(row["id"], str(self.thread.id))
        self.assertEqual(row["teacherName"], "Dr. Rao")
        self.assertEqual(row["teacherSubject"], "Data Structures")
        self.assertEqual(row["avatarColor"], "#2563EB")
        self.assertEqual(row["unread"], 1)  # parent's own counter
        self.assertEqual(len(row["messages"]), 1)
        self.assertEqual(row["messages"][0]["sender"], "teacher")

    def test_teacher_sees_thread_with_zero_unread(self):
        self.client.force_authenticate(self.teacher)
        resp = self.client.get(reverse("chat:chat-threads-list"))
        data = resp.json()["data"]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["unread"], 0)  # teacher has no unread here

    def test_unrelated_parent_sees_no_threads(self):
        self.client.force_authenticate(self.other_parent)
        resp = self.client.get(reverse("chat:chat-threads-list"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"], [])

    # -- retrieve (object-level participant check) -----------------------
    def test_unrelated_parent_cannot_retrieve_thread(self):
        self.client.force_authenticate(self.other_parent)
        resp = self.client.get(
            reverse("chat:chat-threads-detail", args=[self.thread.id])
        )
        self.assertEqual(resp.status_code, 404)  # scoped queryset -> not found

    def test_admin_can_retrieve_any_thread(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.get(
            reverse("chat:chat-threads-detail", args=[self.thread.id])
        )
        self.assertEqual(resp.status_code, 200)

    # -- send message -----------------------------------------------------
    def test_parent_can_send_message_and_it_bumps_teacher_unread(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post(
            reverse("chat:chat-threads-messages", args=[self.thread.id]),
            {"text": "Thank you!"}, format="json",
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()["data"]
        # Thread returned with the new message appended (sender = parent).
        self.assertEqual(len(data["messages"]), 2)
        self.assertEqual(data["messages"][-1]["sender"], "parent")
        self.assertEqual(data["messages"][-1]["text"], "Thank you!")

        self.thread.refresh_from_db()
        self.assertEqual(self.thread.unread_count[str(self.teacher.id)], 1)
        self.assertTrue(
            AuditLog.objects.filter(entity="ChatMessage", action="create").exists()
        )

    def test_send_empty_message_is_rejected(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post(
            reverse("chat:chat-threads-messages", args=[self.thread.id]),
            {"text": "   "}, format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["success"])

    def test_unrelated_parent_cannot_send_message(self):
        self.client.force_authenticate(self.other_parent)
        resp = self.client.post(
            reverse("chat:chat-threads-messages", args=[self.thread.id]),
            {"text": "hi"}, format="json",
        )
        self.assertEqual(resp.status_code, 404)  # not in scoped queryset

    def test_student_role_is_denied_chat(self):
        student = User.objects.create_user(
            email="abin@example.com", password="Str0ng-Pass!23",
            full_name="Abin", role=Role.STUDENT,
        )
        self.client.force_authenticate(student)
        resp = self.client.get(reverse("chat:chat-threads-list"))
        self.assertEqual(resp.status_code, 403)  # role matrix excludes students

    # -- mark read --------------------------------------------------------
    def test_mark_read_zeros_unread_and_flags_messages(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post(
            reverse("chat:chat-threads-read", args=[self.thread.id])
        )
        self.assertEqual(resp.status_code, 204)

        self.thread.refresh_from_db()
        self.assertEqual(self.thread.unread_count[str(self.parent.id)], 0)
        # The teacher's inbound message is now flagged read for the parent.
        self.assertFalse(self.thread.messages.filter(read=False).exists())
