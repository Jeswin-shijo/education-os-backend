"""Academics domain models.

The academic structure hierarchy: ``Department`` → ``Program`` (the mobile app
calls these "courses") → ``Semester`` → ``Section``. ``Subject`` belongs to a
department; ``ClassSession`` places a subject in a section's weekly timetable.

Every model extends :class:`core.models.BaseModel` (UUID PK, audit fields,
soft-delete). This app replaces the legacy template ``courses`` app.
"""
from django.db import models

from core.models import BaseModel


class Department(BaseModel):
    """An academic department, e.g. CSE / ECE / MECH."""

    code = models.CharField(max_length=32, unique=True, db_index=True)
    name = models.CharField(max_length=255)

    class Meta:
        ordering = ["code"]
        verbose_name = "Department"
        verbose_name_plural = "Departments"

    def __str__(self):
        return f"{self.code} — {self.name}"


class Program(BaseModel):
    """A degree program / course offered by a department (app calls it "course")."""

    code = models.CharField(max_length=32, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name="programs",
    )
    duration_years = models.PositiveSmallIntegerField(default=4)
    intake = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["code"]
        verbose_name = "Program"
        verbose_name_plural = "Programs"

    def __str__(self):
        return f"{self.code} — {self.name}"


class Semester(BaseModel):
    """A semester within a program (e.g. semester 5 of B.Tech CSE)."""

    program = models.ForeignKey(
        Program,
        on_delete=models.CASCADE,
        related_name="semesters",
    )
    number = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["program", "number"]
        constraints = [
            models.UniqueConstraint(
                fields=["program", "number"],
                condition=models.Q(is_deleted=False),
                name="uniq_semester_program_number",
            )
        ]

    def __str__(self):
        return f"{self.program.code} S{self.number}"


class Section(BaseModel):
    """A section (class group) within a semester, e.g. "A" / "B"."""

    semester = models.ForeignKey(
        Semester,
        on_delete=models.CASCADE,
        related_name="sections",
    )
    name = models.CharField(max_length=32)

    class Meta:
        ordering = ["semester", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["semester", "name"],
                condition=models.Q(is_deleted=False),
                name="uniq_section_semester_name",
            )
        ]

    def __str__(self):
        return f"{self.semester} - {self.name}"


class Subject(BaseModel):
    """A taught subject/course unit belonging to a department."""

    code = models.CharField(max_length=32, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    credits = models.PositiveSmallIntegerField(default=0)
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name="subjects",
    )
    faculty_name = models.CharField(max_length=255, blank=True, default="")
    color = models.CharField(max_length=9, blank=True, default="")

    class Meta:
        ordering = ["code"]
        verbose_name = "Subject"
        verbose_name_plural = "Subjects"

    def __str__(self):
        return f"{self.code} — {self.name}"


class ClassSession(BaseModel):
    """A weekly timetable slot: a subject taught to a section on a given day."""

    DAY_MON = "Mon"
    DAY_TUE = "Tue"
    DAY_WED = "Wed"
    DAY_THU = "Thu"
    DAY_FRI = "Fri"
    DAY_SAT = "Sat"
    DAY_CHOICES = [
        (DAY_MON, "Monday"),
        (DAY_TUE, "Tuesday"),
        (DAY_WED, "Wednesday"),
        (DAY_THU, "Thursday"),
        (DAY_FRI, "Friday"),
        (DAY_SAT, "Saturday"),
    ]
    # Weekday order for grouping/sorting the timetable grid.
    DAY_ORDER = [DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI, DAY_SAT]

    TYPE_LECTURE = "Lecture"
    TYPE_LAB = "Lab"
    TYPE_TUTORIAL = "Tutorial"
    TYPE_CHOICES = [
        (TYPE_LECTURE, "Lecture"),
        (TYPE_LAB, "Lab"),
        (TYPE_TUTORIAL, "Tutorial"),
    ]

    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="sessions",
    )
    section = models.ForeignKey(
        Section,
        on_delete=models.CASCADE,
        related_name="sessions",
    )
    day = models.CharField(max_length=3, choices=DAY_CHOICES, db_index=True)
    # Stored as free-form "HH:MM" strings to mirror the mobile app contract.
    start = models.CharField(max_length=16)
    end = models.CharField(max_length=16)
    room = models.CharField(max_length=64, blank=True, default="")
    type = models.CharField(
        max_length=16, choices=TYPE_CHOICES, default=TYPE_LECTURE
    )

    class Meta:
        ordering = ["day", "start"]
        indexes = [
            models.Index(fields=["section", "day"]),
            models.Index(fields=["subject", "day"]),
        ]

    def __str__(self):
        return f"{self.subject.code} {self.day} {self.start}-{self.end}"
