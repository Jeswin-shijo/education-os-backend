"""Students domain models.

The central :class:`Student` record links an optional ``accounts.User`` login to
the academic structure (``Program``/``Department``/``Semester``/``Section`` from
the academics app) and carries the profile fields the mobile app's ``Student``
type expects. Child tables hold address, guardian, medical and document details.

Every model extends :class:`core.models.BaseModel` (UUID PK, audit fields,
soft-delete). The parent-login link (guardian ↔ user) lives in the later
``guardians`` module; :class:`Guardian` here only stores basic contact info on
the student record.
"""
from django.db import models

from core.models import BaseModel


class Student(BaseModel):
    """A student profile.

    Denormalised display fields (``first_name``/``last_name``/``full_name``,
    ``email``, ``phone``, ``mentor_name``, ``blood_group``) mirror the mobile
    app's ``Student`` type so the roster/profile endpoints can serve it directly,
    while the FKs (``program``/``department``/``semester``/``section``) tie the
    record into the academic structure.
    """

    STATUS_ACTIVE = "active"
    STATUS_INACTIVE = "inactive"
    STATUS_ALUMNI = "alumni"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_INACTIVE, "Inactive"),
        (STATUS_ALUMNI, "Alumni"),
    ]

    GENDER_MALE = "male"
    GENDER_FEMALE = "female"
    GENDER_OTHER = "other"
    GENDER_CHOICES = [
        (GENDER_MALE, "Male"),
        (GENDER_FEMALE, "Female"),
        (GENDER_OTHER, "Other"),
    ]

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="student_profiles",
    )

    # Identity / enrolment
    roll_no = models.CharField(max_length=64, unique=True, db_index=True)
    admission_no = models.CharField(max_length=64, blank=True, default="", db_index=True)

    # Academic structure (academics app)
    program = models.ForeignKey(
        "academics.Program",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="students",
    )
    department = models.ForeignKey(
        "academics.Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="students",
    )
    semester = models.ForeignKey(
        "academics.Semester",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="students",
    )
    section = models.ForeignKey(
        "academics.Section",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="students",
    )

    # Profile (mirrors types.ts Student)
    first_name = models.CharField(max_length=128, blank=True, default="")
    last_name = models.CharField(max_length=128, blank=True, default="")
    full_name = models.CharField(max_length=255)
    gender = models.CharField(
        max_length=16, choices=GENDER_CHOICES, blank=True, default=""
    )
    dob = models.DateField(null=True, blank=True)
    phone = models.CharField(max_length=20, blank=True, default="")
    email = models.EmailField(blank=True, default="", db_index=True)
    cgpa = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    blood_group = models.CharField(max_length=8, blank=True, default="")
    mentor_name = models.CharField(max_length=255, blank=True, default="")
    avatar_color = models.CharField(max_length=9, blank=True, default="")
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
        db_index=True,
    )

    class Meta:
        ordering = ["roll_no"]
        verbose_name = "Student"
        verbose_name_plural = "Students"
        indexes = [
            models.Index(fields=["department", "status"]),
            models.Index(fields=["semester", "section"]),
        ]

    def __str__(self):
        return f"{self.roll_no} — {self.full_name}"

    def save(self, *args, **kwargs):
        if not self.full_name:
            self.full_name = f"{self.first_name} {self.last_name}".strip()
        super().save(*args, **kwargs)


class StudentAddress(BaseModel):
    """A postal address attached to a student (home/correspondence)."""

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="addresses",
    )
    line1 = models.CharField(max_length=255, blank=True, default="")
    line2 = models.CharField(max_length=255, blank=True, default="")
    city = models.CharField(max_length=128, blank=True, default="")
    state = models.CharField(max_length=128, blank=True, default="")
    pincode = models.CharField(max_length=16, blank=True, default="")
    country = models.CharField(max_length=128, blank=True, default="India")

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Address for {self.student_id}"


class Guardian(BaseModel):
    """Basic guardian/contact info on the student record.

    The parent-login link lives in the later ``guardians`` module; this is just
    the display contact for the student's parent/guardian.
    """

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="guardians",
    )
    name = models.CharField(max_length=255)
    relation = models.CharField(max_length=64, blank=True, default="")
    phone = models.CharField(max_length=20, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_primary", "name"]
        indexes = [
            models.Index(fields=["student", "is_primary"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.relation}) for {self.student_id}"


class Medical(BaseModel):
    """Medical details for a student (one record per student)."""

    student = models.OneToOneField(
        Student,
        on_delete=models.CASCADE,
        related_name="medical",
    )
    blood_group = models.CharField(max_length=8, blank=True, default="")
    allergies = models.TextField(blank=True, default="")
    conditions = models.TextField(blank=True, default="")
    notes = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = "Medical record"
        verbose_name_plural = "Medical records"

    def __str__(self):
        return f"Medical for {self.student_id}"


class StudentDocument(BaseModel):
    """A document attached to a student (id proof, certificate, etc.)."""

    KIND_ID = "id"
    KIND_CERTIFICATE = "certificate"
    KIND_MARKSHEET = "marksheet"
    KIND_PHOTO = "photo"
    KIND_OTHER = "other"
    KIND_CHOICES = [
        (KIND_ID, "ID proof"),
        (KIND_CERTIFICATE, "Certificate"),
        (KIND_MARKSHEET, "Marksheet"),
        (KIND_PHOTO, "Photo"),
        (KIND_OTHER, "Other"),
    ]

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    title = models.CharField(max_length=255)
    kind = models.CharField(
        max_length=32, choices=KIND_CHOICES, default=KIND_OTHER, db_index=True
    )
    file = models.FileField(upload_to="student_documents/", null=True, blank=True)
    url = models.URLField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.kind}) for {self.student_id}"
