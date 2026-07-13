"""Academics domain models.

The academic structure hierarchy: ``Department`` → ``Program`` (the mobile app
calls these "courses") → ``Semester`` → ``Section``. ``Subject`` belongs to a
department; ``ClassSession`` places a subject in a section's weekly timetable.

Every model extends :class:`core.models.BaseModel` (UUID PK, audit fields,
soft-delete). This app replaces the legacy template ``courses`` app.
"""
from django.db import models

from core.models import BaseModel


# Shift choices shared by ``Section`` (the class group) and ``ClassSession``
# (a timetable slot). A class group is conceptually
# Program + Semester + Shift + Section(name).
SHIFT_MORNING = "Morning"
SHIFT_AFTERNOON = "Afternoon"
SHIFT_EVENING = "Evening"
SHIFT_CHOICES = [
    (SHIFT_MORNING, "Morning"),
    (SHIFT_AFTERNOON, "Afternoon"),
    (SHIFT_EVENING, "Evening"),
]


class Department(BaseModel):
    """An academic department, e.g. CSE / ECE / MECH."""

    code = models.CharField(max_length=32, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    hod = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hod_departments",
        help_text="Head of Department (must be a faculty/hod-role user).",
    )

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
    """A section (class group) within a semester, e.g. "A" / "B".

    A class group is conceptually Program + Semester + Shift + Section(name);
    the owning ``Program``/``Semester`` are reached via the ``semester`` FK, and
    ``shift`` distinguishes the Morning/Afternoon/Evening batch.
    """

    semester = models.ForeignKey(
        Semester,
        on_delete=models.CASCADE,
        related_name="sections",
    )
    name = models.CharField(max_length=32)
    shift = models.CharField(
        max_length=16,
        choices=SHIFT_CHOICES,
        default=SHIFT_MORNING,
        help_text="Daily shift for this class group.",
    )

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
    """A taught subject/course unit belonging to a department and semester."""

    code = models.CharField(max_length=32, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    credits = models.PositiveSmallIntegerField(default=0)
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name="subjects",
    )
    program = models.ForeignKey(
        Program,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subjects",
        help_text="The program this subject belongs to.",
    )
    semester = models.ForeignKey(
        Semester,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subjects",
        help_text="The semester this subject is taught in.",
    )
    academic_session = models.CharField(
        max_length=16,
        blank=True,
        default="",
        help_text='Academic year label, e.g. "2026-2027".',
    )
    # Single-faculty fields kept for back-compat with the existing mobile
    # endpoints; ``faculties`` is the new multi-faculty relation.
    faculty = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subjects_teaching",
        help_text="Assigned faculty member for this subject (legacy single-faculty).",
    )
    faculty_name = models.CharField(max_length=255, blank=True, default="")
    faculties = models.ManyToManyField(
        "faculty.FacultyProfile",
        blank=True,
        related_name="taught_subjects",
        help_text="All faculty members who teach this subject (multi-faculty).",
    )
    color = models.CharField(max_length=9, blank=True, default="")

    class Meta:
        ordering = ["code"]
        verbose_name = "Subject"
        verbose_name_plural = "Subjects"

    def __str__(self):
        return f"{self.code} — {self.name}"

    def save(self, *args, **kwargs):
        # Auto-sync faculty_name from the linked user if available.
        if self.faculty_id and not self.faculty_name:
            self.faculty_name = self.faculty.full_name
        super().save(*args, **kwargs)


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

    STATUS_ACTIVE = "active"
    STATUS_INACTIVE = "inactive"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_INACTIVE, "Inactive"),
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
    faculty = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="timetable_sessions",
        help_text="Faculty taking this session (overrides subject default).",
    )
    day = models.CharField(max_length=3, choices=DAY_CHOICES, db_index=True)
    # Stored as free-form "HH:MM" strings to mirror the mobile app contract.
    start = models.CharField(max_length=16)
    end = models.CharField(max_length=16)
    room = models.CharField(max_length=64, blank=True, default="")
    type = models.CharField(
        max_length=16, choices=TYPE_CHOICES, default=TYPE_LECTURE
    )
    academic_session = models.CharField(
        max_length=16,
        blank=True,
        default="",
        help_text='Academic year label, e.g. "2026-2027".',
    )
    shift = models.CharField(
        max_length=16,
        choices=SHIFT_CHOICES,
        default=SHIFT_MORNING,
        help_text="Daily shift for this session (mirrors Section.shift).",
    )
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
        db_index=True,
    )

    class Meta:
        ordering = ["day", "start"]
        indexes = [
            models.Index(fields=["section", "day"]),
            models.Index(fields=["subject", "day"]),
        ]

    def __str__(self):
        return f"{self.subject.code} {self.day} {self.start}-{self.end}"
