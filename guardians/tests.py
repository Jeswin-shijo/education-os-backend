"""Guardians endpoint tests: happy path + permission/validation cases.

The module's routes are not mounted in ``config/urls`` until the integrate step,
so these tests mount the router under a local ``ROOT_URLCONF`` for isolation.
"""
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import include, path, reverse
from rest_framework.test import APITestCase

from core.permissions import Role

from academics.models import Department, Program, Section, Semester
from students.models import Student
from guardians.models import ParentLink
from guardians.urls import router

User = get_user_model()

# Local urlconf mounting the guardians router at the root for tests.
urlpatterns = [
    path("", include((router.urls, "guardians"), namespace="guardians"))
]


@override_settings(ROOT_URLCONF=__name__)
class GuardiansAPITests(APITestCase):
    def setUp(self):
        pwd = "Str0ng-Pass!23"
        self.admin = User.objects.create_user(
            email="admin@example.com", password=pwd, full_name="Admin",
            role=Role.ADMIN,
        )
        self.parent = User.objects.create_user(
            email="parent@example.com", password=pwd, full_name="Mr. Thomas",
            role=Role.PARENT,
        )
        self.other_parent = User.objects.create_user(
            email="parent2@example.com", password=pwd, full_name="Mrs. Nair",
            role=Role.PARENT,
        )
        self.student_user = User.objects.create_user(
            email="abin@example.com", password=pwd, full_name="Abin",
            role=Role.STUDENT,
        )

        self.dept = Department.objects.create(code="CSE", name="Computer Science")
        self.program = Program.objects.create(
            code="BTCSE", name="B.Tech CSE", department=self.dept,
            duration_years=4, intake=60,
        )
        self.sem = Semester.objects.create(program=self.program, number=5)
        self.section = Section.objects.create(semester=self.sem, name="A")

        self.child = Student.objects.create(
            user=self.student_user, roll_no="CSE001", full_name="Abin Thomas",
            program=self.program, department=self.dept, semester=self.sem,
            section=self.section, cgpa="8.50", email="abin@example.com",
            avatar_color="#2563EB",
        )
        self.other_child = Student.objects.create(
            roll_no="CSE002", full_name="Neha Nair", program=self.program,
            department=self.dept, semester=self.sem, section=self.section,
        )

        self.link = ParentLink.objects.create(
            parent=self.parent, student=self.child,
            relation=ParentLink.RELATION_FATHER, is_primary=True,
        )
        self.other_link = ParentLink.objects.create(
            parent=self.other_parent, student=self.other_child,
            relation=ParentLink.RELATION_MOTHER,
        )

    # -- admin CRUD + listing --------------------------------------------
    def test_admin_can_list_links(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.get(reverse("guardians:guardians-list"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "success")
        self.assertGreaterEqual(len(resp.json()["data"]), 2)

    def test_list_requires_auth(self):
        self.assertEqual(
            self.client.get(reverse("guardians:guardians-list")).status_code, 401
        )

    def test_parent_cannot_list_links(self):
        self.client.force_authenticate(self.parent)
        self.assertEqual(
            self.client.get(reverse("guardians:guardians-list")).status_code, 403
        )

    def test_admin_can_create_link_and_it_is_audited(self):
        from core.models import AuditLog

        new_parent = User.objects.create_user(
            email="p3@example.com", password="Str0ng-Pass!23",
            full_name="Guardian", role=Role.PARENT,
        )
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            reverse("guardians:guardians-list"),
            {"parent": str(new_parent.id), "student": str(self.child.id),
             "relation": "guardian"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(
            ParentLink.objects.filter(parent=new_parent, student=self.child).exists()
        )
        self.assertTrue(
            AuditLog.objects.filter(entity="ParentLink", action="create").exists()
        )

    def test_parent_cannot_create_link(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post(
            reverse("guardians:guardians-list"),
            {"parent": str(self.parent.id), "student": str(self.other_child.id)},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_create_duplicate_link_validation_error(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            reverse("guardians:guardians-list"),
            {"parent": str(self.parent.id), "student": str(self.child.id),
             "relation": "father"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["status"], "error")

    def test_create_link_non_parent_role_validation_error(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            reverse("guardians:guardians-list"),
            {"parent": str(self.student_user.id), "student": str(self.child.id)},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["status"], "error")

    # -- self-scoped parent children read --------------------------------
    def test_parent_children_shape(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.get(reverse("guardians:guardians-children"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], str(self.child.id))
        self.assertEqual(data[0]["name"], "Abin Thomas")
        self.assertEqual(data[0]["rollNo"], "CSE001")
        self.assertEqual(data[0]["branch"], "Computer Science")
        self.assertEqual(data[0]["semester"], 5)
        self.assertEqual(data[0]["section"], "A")
        self.assertEqual(data[0]["relation"], "father")

    def test_parent_children_only_own(self):
        # The other parent must not see this parent's child.
        self.client.force_authenticate(self.other_parent)
        resp = self.client.get(reverse("guardians:guardians-children"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], str(self.other_child.id))

    def test_children_requires_auth(self):
        self.assertEqual(
            self.client.get(reverse("guardians:guardians-children")).status_code,
            401,
        )

    def test_student_cannot_read_children(self):
        self.client.force_authenticate(self.student_user)
        self.assertEqual(
            self.client.get(reverse("guardians:guardians-children")).status_code,
            403,
        )
