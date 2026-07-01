"""Library endpoint tests: happy path + permission/validation cases.

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

from academics.models import Department, Program, Section, Semester
from library.models import Book, BookLoan
from library.urls import urlpatterns as library_urlpatterns
from students.models import Student

User = get_user_model()

urlpatterns = [path("", include((library_urlpatterns, "library"), namespace="library"))]


@override_settings(ROOT_URLCONF=__name__)
class LibraryAPITests(APITestCase):
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
            program=self.program, department=self.dept, semester=self.sem,
            section=self.section, full_name="Neha", email="neha@example.com",
        )

        self.book = Book.objects.create(
            title="Clean Code", author="Robert Martin", category="Programming",
            isbn="9780132350884", copies_total=3, copies_available=3,
        )
        Book.objects.create(
            title="The Pragmatic Programmer", author="Hunt & Thomas",
            category="Programming", copies_total=2, copies_available=0,
            available=False,
        )
        today = timezone.localdate()
        self.loan = BookLoan.objects.create(
            book=self.book, student=self.student, issued_on=today,
            due_on=today + timedelta(days=14), status=BookLoan.STATUS_BORROWED,
        )
        # A loan belonging to another student, to prove scoping.
        BookLoan.objects.create(
            book=self.book, student=self.other_student, issued_on=today,
            due_on=today + timedelta(days=14), status=BookLoan.STATUS_BORROWED,
        )

    # -- GET /library/books (app-shaped, all roles) ----------------------
    def test_student_can_search_books(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.get(reverse("library:book-search"))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])
        data = resp.json()["data"]
        self.assertEqual(len(data), 2)
        self.assertEqual(set(data[0].keys()), {"id", "title", "author", "category", "available"})

    def test_books_query_filter(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.get(reverse("library:book-search"), {"q": "pragmatic"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["title"], "The Pragmatic Programmer")
        self.assertFalse(data[0]["available"])

    def test_books_requires_auth(self):
        self.assertEqual(
            self.client.get(reverse("library:book-search")).status_code, 401
        )

    # -- GET /library/loans (requesting student's own loans) -------------
    def test_student_sees_only_own_loans(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.get(reverse("library:loan-list"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(len(data), 1)
        row = data[0]
        self.assertEqual(set(row.keys()), {"id", "bookId", "title", "issuedOn", "dueOn", "status"})
        self.assertEqual(row["title"], "Clean Code")
        self.assertEqual(row["bookId"], str(self.book.id))

    def test_loans_404_when_no_student_profile(self):
        staff = User.objects.create_user(
            email="fac@example.com", password="Str0ng-Pass!23",
            full_name="Fac", role=Role.FACULTY,
        )
        self.client.force_authenticate(staff)
        resp = self.client.get(reverse("library:loan-list"))
        self.assertEqual(resp.status_code, 404)

    # -- Admin book CRUD (RBAC + audit + availability sync) --------------
    def test_admin_can_create_book_and_it_is_audited(self):
        from core.models import AuditLog

        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            reverse("library:book-list"),
            {
                "title": "Refactoring", "author": "Martin Fowler",
                "category": "Programming", "isbn": "9780201485677",
                "copies_total": 4, "copies_available": 4,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        book = Book.objects.get(title="Refactoring")
        self.assertTrue(book.available)  # derived from copies_available
        self.assertTrue(
            AuditLog.objects.filter(entity="Book", action="create").exists()
        )

    def test_book_availability_syncs_on_update(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.patch(
            reverse("library:book-detail", args=[self.book.id]),
            {"copies_available": 0}, format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.book.refresh_from_db()
        self.assertEqual(self.book.copies_available, 0)
        self.assertFalse(self.book.available)

    def test_student_cannot_create_book(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.post(
            reverse("library:book-list"),
            {"title": "Nope", "copies_total": 1}, format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_create_book_validation_error(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            reverse("library:book-list"),
            {"copies_total": 1, "copies_available": 5}, format="json",
        )
        # missing title AND copies_available > copies_total
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["success"])

    def test_student_cannot_list_admin_loans(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.get(reverse("library:book-loan-list"))
        self.assertEqual(resp.status_code, 403)
