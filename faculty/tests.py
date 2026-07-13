"""Faculty endpoint tests: happy path + permission/validation cases.

The module's routes are not mounted in ``config/urls`` until the integrate step,
so these tests mount the router under a local ``ROOT_URLCONF`` for isolation.
"""
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import include, path, reverse
from rest_framework.test import APITestCase

from core.permissions import Role

from academics.models import Department, Program, Section, Semester, Subject
from faculty.models import FacultyClass, FacultyProfile, RosterEntry
from faculty.urls import router

User = get_user_model()

# Local urlconf mounting the faculty router at the root for tests.
urlpatterns = [path("", include((router.urls, "faculty"), namespace="faculty"))]


@override_settings(ROOT_URLCONF=__name__)
class FacultyAPITests(APITestCase):
    def setUp(self):
        pwd = "Str0ng-Pass!23"
        self.admin = User.objects.create_user(
            email="admin@example.com", password=pwd, full_name="Admin", role=Role.ADMIN
        )
        self.faculty_user = User.objects.create_user(
            email="rao@example.com", password=pwd, full_name="Dr. Rao",
            role=Role.FACULTY, avatar_color="#13327F",
        )
        self.other_faculty_user = User.objects.create_user(
            email="menon@example.com", password=pwd, full_name="Dr. Menon",
            role=Role.FACULTY,
        )
        self.student = User.objects.create_user(
            email="abin@example.com", password=pwd, full_name="Abin", role=Role.STUDENT
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

        self.profile = FacultyProfile.objects.create(
            user=self.faculty_user, department=self.dept,
            designation="Associate Professor", subject_codes=["sub-ds"],
        )
        self.other_profile = FacultyProfile.objects.create(
            user=self.other_faculty_user, department=self.dept,
            designation="Assistant Professor", subject_codes=["sub-os"],
        )
        self.klass = FacultyClass.objects.create(
            subject=self.subject, semester=self.sem, section=self.section,
            faculty=self.profile, color="#2563EB", student_count=2,
            slots=[{"day": "Mon", "start": "09:00", "end": "10:00", "room": "B-101"}],
        )
        self.other_klass = FacultyClass.objects.create(
            subject=self.subject, semester=self.sem, section=self.section,
            faculty=self.other_profile, color="#F59E0B", student_count=0, slots=[],
        )
        RosterEntry.objects.create(
            faculty_class=self.klass, roll_no="CSE001",
            student_name="Abin Thomas", avatar_color="#2563EB",
        )
        RosterEntry.objects.create(
            faculty_class=self.klass, roll_no="CSE002",
            student_name="Neha Nair", avatar_color="#F43F5E",
        )

    # -- admin CRUD + directory listing ----------------------------------
    def test_admin_can_list_faculty(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.get(reverse("faculty:faculty-list"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "success")
        self.assertGreaterEqual(resp.json()["data"]["pagination"]["count"], 2)

    def test_list_requires_auth(self):
        self.assertEqual(
            self.client.get(reverse("faculty:faculty-list")).status_code, 401
        )

    def test_student_cannot_list_faculty(self):
        self.client.force_authenticate(self.student)
        self.assertEqual(
            self.client.get(reverse("faculty:faculty-list")).status_code, 403
        )

    def test_admin_can_create_profile_and_it_is_audited(self):
        from core.models import AuditLog

        new_user = User.objects.create_user(
            email="iyer@example.com", password="Str0ng-Pass!23",
            full_name="Dr. Iyer", role=Role.FACULTY,
        )
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            reverse("faculty:faculty-list"),
            {"user": str(new_user.id), "department": str(self.dept.id),
             "designation": "Professor", "subject_codes": ["sub-cn"]},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(FacultyProfile.objects.filter(user=new_user).exists())
        self.assertTrue(
            AuditLog.objects.filter(entity="FacultyProfile", action="create").exists()
        )

    def test_admin_can_create_faculty_with_uploaded_photo(self):
        """A multipart create carrying a ``profile_pic`` file stores the image on
        the new faculty User and surfaces it back through ``photo_url``."""
        import shutil
        import tempfile
        from io import BytesIO

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        buf = BytesIO()
        Image.new("RGB", (4, 4), "#123456").save(buf, format="PNG")
        photo = SimpleUploadedFile("face.png", buf.getvalue(), content_type="image/png")

        media_tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media_tmp, ignore_errors=True)

        self.client.force_authenticate(self.admin)
        with override_settings(MEDIA_ROOT=media_tmp):
            resp = self.client.post(
                reverse("faculty:faculty-list"),
                {
                    "full_name": "Dr. Photo",
                    "email": "photo@example.com",
                    "department": str(self.dept.id),
                    "designation": "Professor",
                    "profile_pic": photo,
                },
                format="multipart",
            )
        self.assertEqual(resp.status_code, 201, resp.content)
        photo_url = resp.json()["data"]["photo_url"]
        self.assertTrue(photo_url)
        self.assertIn(".png", photo_url.lower())
        created = User.objects.get(email__iexact="photo@example.com")
        self.assertTrue(created.profile_pic)

    def test_faculty_cannot_create_profile(self):
        self.client.force_authenticate(self.faculty_user)
        resp = self.client.post(
            reverse("faculty:faculty-list"),
            {"user": str(self.student.id), "department": str(self.dept.id)},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_create_profile_validation_error(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            reverse("faculty:faculty-list"),
            {"department": str(self.dept.id)},  # missing required `user`
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["status"], "error")

    # -- self-scoped reads -----------------------------------------------
    def test_faculty_me_shape(self):
        self.client.force_authenticate(self.faculty_user)
        resp = self.client.get(reverse("faculty:faculty-me"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["faculty"]["name"], "Dr. Rao")
        self.assertEqual(data["department"], "Computer Science")
        self.assertEqual(data["designation"], "Associate Professor")
        self.assertEqual(len(data["classes"]), 1)
        self.assertEqual(data["classes"][0]["subjectCode"], "sub-ds")
        self.assertEqual(data["classes"][0]["semester"], 5)
        self.assertEqual(data["classes"][0]["section"], "A")

    def test_faculty_classes_list(self):
        self.client.force_authenticate(self.faculty_user)
        resp = self.client.get(reverse("faculty:faculty-classes"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["subjectId"], str(self.subject.id))
        self.assertEqual(data[0]["studentCount"], 2)

    def test_faculty_class_detail_owner_scoped(self):
        self.client.force_authenticate(self.faculty_user)
        ok = self.client.get(
            reverse("faculty:faculty-class-detail", args=[self.klass.id])
        )
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()["data"]["id"], str(self.klass.id))
        # Faculty cannot read another faculty's class.
        forbidden = self.client.get(
            reverse("faculty:faculty-class-detail", args=[self.other_klass.id])
        )
        self.assertEqual(forbidden.status_code, 403)

    def test_admin_can_read_any_class(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.get(
            reverse("faculty:faculty-class-detail", args=[self.other_klass.id])
        )
        self.assertEqual(resp.status_code, 200)

    def test_class_roster_shape(self):
        self.client.force_authenticate(self.faculty_user)
        resp = self.client.get(
            reverse("faculty:faculty-roster", args=[self.klass.id])
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["rollNo"], "CSE001")
        self.assertEqual(data[0]["name"], "Abin Thomas")
        self.assertIn("avatarColor", data[0])

    def test_me_404_when_no_profile(self):
        # A staff user (principal) with no FacultyProfile hits /faculty/me.
        principal = User.objects.create_user(
            email="prin@example.com", password="Str0ng-Pass!23",
            full_name="Principal", role=Role.PRINCIPAL,
        )
        self.client.force_authenticate(principal)
        resp = self.client.get(reverse("faculty:faculty-me"))
        self.assertEqual(resp.status_code, 404)
