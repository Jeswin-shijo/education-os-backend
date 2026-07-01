"""AI endpoint tests: happy path + auth + validation + ownership.

The module's routes are not mounted in ``config/urls`` until the integrate step,
so these tests mount the app's urlpatterns under a local ``ROOT_URLCONF``.
"""
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import include, path, reverse
from rest_framework.test import APITestCase

from core.permissions import Role

from ai import llm
from ai.models import AIMessage, AIThread
from ai.urls import urlpatterns as ai_urlpatterns

User = get_user_model()

urlpatterns = [path("", include((ai_urlpatterns, "ai"), namespace="ai"))]


@override_settings(ROOT_URLCONF=__name__)
class AIAPITests(APITestCase):
    def setUp(self):
        pwd = "Str0ng-Pass!23"
        self.student = User.objects.create_user(
            email="abin@example.com", password=pwd, full_name="Abin",
            role=Role.STUDENT,
        )
        self.other = User.objects.create_user(
            email="riya@example.com", password=pwd, full_name="Riya",
            role=Role.STUDENT,
        )

    # -- auth ------------------------------------------------------------
    def test_threads_requires_auth(self):
        self.assertEqual(self.client.get(reverse("ai:threads")).status_code, 401)

    def test_respond_requires_auth(self):
        resp = self.client.post(
            reverse("ai:respond", args=["mentor"]), {"prompt": "hi"}, format="json"
        )
        self.assertEqual(resp.status_code, 401)

    # -- respond (stateless) ---------------------------------------------
    def test_respond_returns_text_no_persistence(self):
        self.client.force_authenticate(self.student)
        resp = self.client.post(
            reverse("ai:respond", args=["doubt"]),
            {"prompt": "Explain deadlock"}, format="json",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertIn("Explain deadlock", body["data"]["text"])
        # respond does not create a thread.
        self.assertEqual(AIThread.objects.count(), 0)

    def test_respond_rejects_unknown_feature(self):
        self.client.force_authenticate(self.student)
        resp = self.client.post(
            reverse("ai:respond", args=["bogus"]), {"prompt": "hi"}, format="json"
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["success"])

    def test_respond_uses_pluggable_provider(self):
        self.client.force_authenticate(self.student)
        llm.set_llm_provider(lambda feature, prompt, history=None: f"REAL:{feature}")
        try:
            resp = self.client.post(
                reverse("ai:respond", args=["career"]),
                {"prompt": "roadmap"}, format="json",
            )
        finally:
            llm.set_llm_provider(None)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["text"], "REAL:career")

    def test_provider_error_degrades_to_canned(self):
        def boom(feature, prompt, history=None):
            raise RuntimeError("provider down")

        self.client.force_authenticate(self.student)
        llm.set_llm_provider(boom)
        try:
            resp = self.client.post(
                reverse("ai:respond", args=["notes"]),
                {"prompt": "Normalization"}, format="json",
            )
        finally:
            llm.set_llm_provider(None)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Notes", resp.json()["data"]["text"])

    # -- threads by feature (find-or-create) -----------------------------
    def test_get_thread_by_feature_creates_once(self):
        self.client.force_authenticate(self.student)
        url = reverse("ai:thread-by-feature", args=["mentor"])
        r1 = self.client.get(url)
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r1.json()["data"]["feature"], "mentor")
        self.assertEqual(r1.json()["data"]["title"], "AI Mentor")
        r2 = self.client.get(url)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r1.json()["data"]["id"], r2.json()["data"]["id"])
        self.assertEqual(
            AIThread.objects.filter(user=self.student, feature="mentor").count(), 1
        )

    # -- send message (persisting) ---------------------------------------
    def test_send_message_appends_user_and_assistant(self):
        self.client.force_authenticate(self.student)
        resp = self.client.post(
            reverse("ai:thread-messages", args=["chat"]),
            {"text": "When is my next exam?"}, format="json",
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()["data"]
        self.assertEqual(len(data["messages"]), 2)
        self.assertEqual(data["messages"][0]["role"], "user")
        self.assertEqual(data["messages"][0]["text"], "When is my next exam?")
        self.assertEqual(data["messages"][1]["role"], "assistant")
        thread = AIThread.objects.get(user=self.student, feature="chat")
        self.assertEqual(thread.messages.count(), 2)

    def test_send_message_is_audited(self):
        from core.models import AuditLog

        self.client.force_authenticate(self.student)
        self.client.post(
            reverse("ai:thread-messages", args=["mentor"]),
            {"text": "plan my week"}, format="json",
        )
        self.assertTrue(
            AuditLog.objects.filter(entity="AIMessage", action="create").exists()
        )

    # -- threads list is own-scoped --------------------------------------
    def test_threads_list_is_owner_scoped(self):
        # student creates a thread; other user must not see it.
        self.client.force_authenticate(self.student)
        self.client.post(
            reverse("ai:thread-messages", args=["doubt"]),
            {"text": "bfs vs dfs"}, format="json",
        )
        listing = self.client.get(reverse("ai:threads")).json()["data"]
        self.assertEqual(len(listing), 1)

        self.client.force_authenticate(self.other)
        other_listing = self.client.get(reverse("ai:threads")).json()["data"]
        self.assertEqual(len(other_listing), 0)

    # -- suggestions (static) --------------------------------------------
    def test_suggestions_returns_chips(self):
        self.client.force_authenticate(self.student)
        resp = self.client.get(reverse("ai:suggestions", args=["mentor"]))
        self.assertEqual(resp.status_code, 200)
        chips = resp.json()["data"]
        self.assertIsInstance(chips, list)
        self.assertIn("How do I improve my CGPA?", chips)

    def test_suggestions_unknown_feature_400(self):
        self.client.force_authenticate(self.student)
        resp = self.client.get(reverse("ai:suggestions", args=["nope"]))
        self.assertEqual(resp.status_code, 400)
