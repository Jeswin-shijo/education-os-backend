"""Materials endpoint tests: happy path + permission/validation cases.

The module's routes are not mounted in ``config/urls`` until the integrate step,
so these tests mount the urlpatterns under a local ``ROOT_URLCONF`` for
isolation.
"""
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import include, path, reverse
from rest_framework.test import APITestCase

from core.models import AuditLog
from core.permissions import Role

from academics.models import Department, Program, Section, Semester, Subject
from faculty.models import FacultyClass, FacultyProfile

from materials.models import Material
from materials.urls import urlpatterns as materials_urlpatterns

User = get_user_model()

urlpatterns = [
    path("", include((materials_urlpatterns, "materials"), namespace="materials")),
]


@override_settings(ROOT_URLCONF=__name__)
class MaterialAPITests(APITestCase):
    def setUp(self):
        pwd = "Str0ng-Pass!23"
        self.admin = User.objects.create_user(
            email="admin@example.com", password=pwd, full_name="Admin",
            role=Role.ADMIN,
        )
        self.faculty_user = User.objects.create_user(
            email="rao@example.com", password=pwd, full_name="Dr. Rao",
            role=Role.FACULTY,
        )
        self.other_faculty_user = User.objects.create_user(
            email="menon@example.com", password=pwd, full_name="Dr. Menon",
            role=Role.FACULTY,
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
        self.subject = Subject.objects.create(
            code="sub-ds", name="Data Structures", credits=4,
            department=self.dept, faculty_name="Dr. Rao", color="#2563EB",
        )
        self.other_subject = Subject.objects.create(
            code="sub-os", name="Operating Systems", credits=4,
            department=self.dept, faculty_name="Dr. Menon", color="#F59E0B",
        )

        self.profile = FacultyProfile.objects.create(
            user=self.faculty_user, department=self.dept,
            designation="Associate Professor", subject_codes=["sub-ds"],
        )
        self.other_profile = FacultyProfile.objects.create(
            user=self.other_faculty_user, department=self.dept,
            designation="Assistant Professor",
        )
        self.klass = FacultyClass.objects.create(
            subject=self.subject, semester=self.sem, section=self.section,
            faculty=self.profile, color="#2563EB", student_count=1, slots=[],
        )
        self.other_klass = FacultyClass.objects.create(
            subject=self.other_subject, semester=self.sem, section=self.section,
            faculty=self.other_profile, color="#F59E0B", student_count=0, slots=[],
        )

        self.mat_ds = Material.objects.create(
            subject=self.subject, faculty_class=self.klass,
            title="DS Notes Ch.1", kind=Material.KIND_NOTE,
            size_label="2.4 MB", url="https://cdn.example/ds1.pdf",
        )
        self.mat_ds_video = Material.objects.create(
            subject=self.subject, faculty_class=self.klass,
            title="DS Lecture", kind=Material.KIND_VIDEO,
            size_label="12 min", url="https://cdn.example/ds.mp4",
        )
        self.mat_os = Material.objects.create(
            subject=self.other_subject, faculty_class=self.other_klass,
            title="OS Slides", kind=Material.KIND_SLIDE,
            size_label="1.1 MB", url="https://cdn.example/os.pdf",
        )

    # -- reads -----------------------------------------------------------
    def test_list_requires_auth(self):
        self.assertEqual(
            self.client.get(reverse("materials:materials-list")).status_code, 401
        )

    def test_student_list_shape(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.get(reverse("materials:materials-list"))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])
        data = resp.json()["data"]
        self.assertEqual(len(data), 3)
        row = data[0]
        # Student-facing camelCase Material shape.
        for key in ("id", "subjectId", "title", "kind", "sizeLabel", "addedAt"):
            self.assertIn(key, row)
        self.assertNotIn("faculty_class", row)

    def test_subject_id_filter(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.get(
            reverse("materials:materials-list"),
            {"subjectId": str(self.subject.id)},
        )
        self.assertEqual(resp.status_code, 200)
        titles = sorted(m["title"] for m in resp.json()["data"])
        self.assertEqual(titles, ["DS Lecture", "DS Notes Ch.1"])

    def test_faculty_materials_own_classes_only(self):
        self.client.force_authenticate(self.faculty_user)
        resp = self.client.get(reverse("materials:materials-faculty-materials"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        titles = sorted(m["title"] for m in data)
        self.assertEqual(titles, ["DS Lecture", "DS Notes Ch.1"])
        # Faculty shape uses classId/addedOn.
        for key in ("id", "classId", "title", "kind", "sizeLabel", "addedOn"):
            self.assertIn(key, data[0])

    # -- writes ----------------------------------------------------------
    def test_faculty_upload_creates_and_audits(self):
        self.client.force_authenticate(self.faculty_user)
        resp = self.client.post(
            reverse("materials:materials-list"),
            {
                "subject": str(self.subject.id),
                "faculty_class": str(self.klass.id),
                "title": "DS Notes Ch.2",
                "kind": "note",
                "size_label": "3.0 MB",
                "url": "https://cdn.example/ds2.pdf",
            },
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertTrue(
            Material.objects.filter(title="DS Notes Ch.2").exists()
        )
        self.assertTrue(
            AuditLog.objects.filter(entity="Material", action="create").exists()
        )

    def test_upload_requires_content(self):
        self.client.force_authenticate(self.faculty_user)
        resp = self.client.post(
            reverse("materials:materials-list"),
            {
                "subject": str(self.subject.id),
                "title": "No content",
                "kind": "note",
            },
        )
        self.assertEqual(resp.status_code, 400)

    def test_student_cannot_upload(self):
        self.client.force_authenticate(self.student_user)
        resp = self.client.post(
            reverse("materials:materials-list"),
            {
                "subject": str(self.subject.id),
                "title": "Sneaky",
                "kind": "note",
                "url": "https://cdn.example/x.pdf",
            },
        )
        self.assertEqual(resp.status_code, 403)
