"""Quizzes endpoint tests: happy path + permission/validation cases.

The module's routes are not mounted in ``config/urls`` until the integrate step,
so these tests mount the router under a local ``ROOT_URLCONF`` for isolation.
"""
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import include, path, reverse
from rest_framework.test import APITestCase

from core.permissions import Role

from academics.models import Department, Subject
from quizzes.models import Quiz, QuizQuestion
from quizzes.urls import router

User = get_user_model()

# Local urlconf mounting the quizzes router at the root for tests.
urlpatterns = [path("", include((router.urls, "quizzes"), namespace="quizzes"))]


@override_settings(ROOT_URLCONF=__name__)
class QuizAPITests(APITestCase):
    def setUp(self):
        pwd = "Str0ng-Pass!23"
        self.admin = User.objects.create_user(
            email="admin@example.com", password=pwd, full_name="Admin", role=Role.ADMIN
        )
        self.faculty = User.objects.create_user(
            email="rao@example.com", password=pwd, full_name="Dr. Rao",
            role=Role.FACULTY,
        )
        self.other_faculty = User.objects.create_user(
            email="menon@example.com", password=pwd, full_name="Dr. Menon",
            role=Role.FACULTY,
        )
        self.student = User.objects.create_user(
            email="abin@example.com", password=pwd, full_name="Abin",
            role=Role.STUDENT,
        )

        self.dept = Department.objects.create(code="CSE", name="Computer Science")
        self.subject = Subject.objects.create(
            code="sub-ds", name="Data Structures", credits=4,
            department=self.dept, faculty_name="Dr. Rao", color="#2563EB",
        )

        self.quiz = Quiz.objects.create(
            subject=self.subject, title="DS Quiz 1", created_by=self.faculty,
        )
        QuizQuestion.objects.create(
            quiz=self.quiz, text="Big-O of binary search?",
            options=["O(1)", "O(n)", "O(log n)"], answer_index=2, order=0,
        )

    # -- reads (all roles) ------------------------------------------------
    def test_list_requires_auth(self):
        self.assertEqual(
            self.client.get(reverse("quizzes:quizzes-list")).status_code, 401
        )

    def test_student_can_list_quizzes(self):
        self.client.force_authenticate(self.student)
        resp = self.client.get(reverse("quizzes:quizzes-list"))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])
        data = resp.json()["data"]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["subjectId"], str(self.subject.id))
        self.assertEqual(data[0]["title"], "DS Quiz 1")
        self.assertEqual(data[0]["questions"][0]["q"], "Big-O of binary search?")
        self.assertEqual(data[0]["questions"][0]["answerIndex"], 2)

    def test_retrieve_quiz_shape(self):
        self.client.force_authenticate(self.student)
        resp = self.client.get(
            reverse("quizzes:quizzes-detail", args=[self.quiz.id])
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["id"], str(self.quiz.id))
        self.assertEqual(len(data["questions"]), 1)

    # -- create (faculty) -------------------------------------------------
    def test_faculty_can_create_quiz_with_questions_and_it_is_audited(self):
        from core.models import AuditLog

        self.client.force_authenticate(self.faculty)
        payload = {
            "subjectId": str(self.subject.id),
            "title": "DS Quiz 2",
            "questions": [
                {"q": "What is a stack?", "options": ["LIFO", "FIFO"], "answerIndex": 0},
                {"q": "What is a queue?", "options": ["LIFO", "FIFO"], "answerIndex": 1},
            ],
        }
        resp = self.client.post(
            reverse("quizzes:quizzes-list"), payload, format="json"
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()["data"]
        self.assertEqual(data["title"], "DS Quiz 2")
        self.assertEqual(len(data["questions"]), 2)
        self.assertEqual(data["questions"][1]["answerIndex"], 1)

        quiz = Quiz.objects.get(title="DS Quiz 2")
        self.assertEqual(quiz.questions.count(), 2)
        self.assertTrue(
            AuditLog.objects.filter(entity="Quiz", action="create").exists()
        )
        self.assertTrue(
            AuditLog.objects.filter(entity="QuizQuestion", action="create").exists()
        )

    def test_student_cannot_create_quiz(self):
        self.client.force_authenticate(self.student)
        resp = self.client.post(
            reverse("quizzes:quizzes-list"),
            {"subjectId": str(self.subject.id), "title": "X",
             "questions": [{"q": "?", "options": ["a", "b"], "answerIndex": 0}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_create_requires_questions(self):
        self.client.force_authenticate(self.faculty)
        resp = self.client.post(
            reverse("quizzes:quizzes-list"),
            {"subjectId": str(self.subject.id), "title": "Empty", "questions": []},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["success"])

    def test_create_rejects_out_of_range_answer_index(self):
        self.client.force_authenticate(self.faculty)
        resp = self.client.post(
            reverse("quizzes:quizzes-list"),
            {"subjectId": str(self.subject.id), "title": "Bad",
             "questions": [{"q": "?", "options": ["a", "b"], "answerIndex": 5}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["success"])

    # -- owner-scoped mutation -------------------------------------------
    def test_faculty_cannot_delete_another_facultys_quiz(self):
        self.client.force_authenticate(self.other_faculty)
        resp = self.client.delete(
            reverse("quizzes:quizzes-detail", args=[self.quiz.id])
        )
        self.assertEqual(resp.status_code, 403)

    def test_admin_can_delete_any_quiz(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.delete(
            reverse("quizzes:quizzes-detail", args=[self.quiz.id])
        )
        self.assertEqual(resp.status_code, 204)
