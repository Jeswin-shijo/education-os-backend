"""Faculty domain models.

A :class:`FacultyProfile` is the teaching identity of an ``accounts.User`` with
role ``faculty`` (its department + designation + the subject codes they teach).
A :class:`FacultyClass` is a concrete teaching assignment: a subject taught to a
particular semester/section by a faculty member, with the weekly ``slots`` grid
and a cached ``student_count``. :class:`RosterEntry` lists the students enrolled
in a class.

The mobile ``students`` app is not yet built, so the roster stores the
``RosterStudent`` shape (``name``/``rollNo``/``avatarColor``) denormalized, with
an optional ``student_ref`` UUID so entries can be linked to
``students.Student`` rows once that module lands. Every model extends
:class:`core.models.BaseModel` (UUID PK, audit fields, soft-delete).
"""
from django.conf import settings
from django.db import models

from core.models import BaseModel


class FacultyProfile(BaseModel):
    """The teaching profile of a faculty user."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="faculty_profile",
    )
    department = models.ForeignKey(
        "academics.Department",
        on_delete=models.PROTECT,
        related_name="faculty_profiles",
    )
    designation = models.CharField(max_length=128, blank=True, default="")
    # List of subject codes this faculty teaches, mirroring the app's
    # ``FacultyPerformance.subjects`` (e.g. ["sub-ds", "sub-os"]).
    subject_codes = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["user__full_name"]
        verbose_name = "Faculty Profile"
        verbose_name_plural = "Faculty Profiles"
        indexes = [
            models.Index(fields=["department"]),
        ]

    def __str__(self):
        return f"{self.user.full_name} ({self.designation or 'Faculty'})"


class FacultyClass(BaseModel):
    """A teaching assignment: a subject taught to a section by a faculty member.

    ``slots`` mirrors the app's ``FacultyClassSlot[]`` — a JSON list of
    ``{"day","start","end","room"}`` objects (weekdays Mon..Sat).
    """

    subject = models.ForeignKey(
        "academics.Subject",
        on_delete=models.CASCADE,
        related_name="faculty_classes",
    )
    semester = models.ForeignKey(
        "academics.Semester",
        on_delete=models.CASCADE,
        related_name="faculty_classes",
    )
    section = models.ForeignKey(
        "academics.Section",
        on_delete=models.CASCADE,
        related_name="faculty_classes",
    )
    faculty = models.ForeignKey(
        FacultyProfile,
        on_delete=models.CASCADE,
        related_name="classes",
    )
    color = models.CharField(max_length=9, blank=True, default="")
    # [{ "day": "Mon", "start": "09:00", "end": "10:00", "room": "B-101" }, ...]
    slots = models.JSONField(default=list, blank=True)
    student_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["subject__code"]
        verbose_name = "Faculty Class"
        verbose_name_plural = "Faculty Classes"
        indexes = [
            models.Index(fields=["faculty"]),
            models.Index(fields=["subject", "section"]),
        ]

    def __str__(self):
        return f"{self.subject.code} → {self.faculty.user.full_name}"


class RosterEntry(BaseModel):
    """A single student's membership in a :class:`FacultyClass` roster.

    Denormalized to the app's ``RosterStudent`` shape so the roster endpoint can
    respond before the ``students`` module exists; ``student_ref`` is reserved
    for the future ``students.Student`` UUID link.
    """

    faculty_class = models.ForeignKey(
        FacultyClass,
        on_delete=models.CASCADE,
        related_name="roster_entries",
    )
    # Future link to students.Student (module not yet built); kept nullable.
    student_ref = models.UUIDField(null=True, blank=True, db_index=True)
    roll_no = models.CharField(max_length=32)
    student_name = models.CharField(max_length=255)
    avatar_color = models.CharField(max_length=9, blank=True, default="")

    class Meta:
        ordering = ["roll_no"]
        verbose_name = "Roster Entry"
        verbose_name_plural = "Roster Entries"
        constraints = [
            models.UniqueConstraint(
                fields=["faculty_class", "roll_no"],
                condition=models.Q(is_deleted=False),
                name="uniq_roster_class_rollno",
            )
        ]
        indexes = [
            models.Index(fields=["faculty_class"]),
        ]

    def __str__(self):
        return f"{self.roll_no} — {self.student_name}"
