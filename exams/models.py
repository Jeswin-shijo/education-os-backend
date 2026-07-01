"""Exams domain models.

Three concerns, mirroring the mobile app's ``types.ts``:

* :class:`Exam` — a scheduled examination for a subject (``types.ts`` ``Exam``:
  name/date/time/room/durationMins/type). Consumed by ``examService.list`` and
  ``examService.upcoming``.
* :class:`ExamResult` — a student's graded result for a subject exam
  (``types.ts`` ``ExamResult``: marks/maxMarks/grade/gradePoint/credits). Drives
  ``examService.results`` and the ``results/gpa`` aggregation.
* :class:`MarksSheet` + :class:`MarkEntry` — faculty marks-entry for a
  :class:`~faculty.models.FacultyClass` (``types.ts`` ``MarksSheet`` /
  ``MarkEntry``). Powers faculty ``POST /marks`` and ``GET /faculty/marks``.

Every model extends :class:`core.models.BaseModel` (UUID PK, audit fields,
soft-delete). Marks/points use ``Decimal`` (never float).
"""
from django.db import models

from core.models import BaseModel


class Exam(BaseModel):
    """A scheduled examination for a subject (mirrors ``types.ts`` ``Exam``)."""

    TYPE_INTERNAL = "Internal"
    TYPE_SEMESTER = "Semester"
    TYPE_QUIZ = "Quiz"
    TYPE_CHOICES = [
        (TYPE_INTERNAL, "Internal"),
        (TYPE_SEMESTER, "Semester"),
        (TYPE_QUIZ, "Quiz"),
    ]

    subject = models.ForeignKey(
        "academics.Subject",
        on_delete=models.CASCADE,
        related_name="exams",
    )
    name = models.CharField(max_length=255)
    date = models.DateField(db_index=True)
    # Stored as a free-form "HH:MM"/"10:00 AM" string to mirror the app contract.
    time = models.CharField(max_length=32, blank=True, default="")
    room = models.CharField(max_length=64, blank=True, default="")
    duration_mins = models.PositiveIntegerField(default=0)
    type = models.CharField(
        max_length=16, choices=TYPE_CHOICES, default=TYPE_INTERNAL, db_index=True
    )

    class Meta:
        ordering = ["date", "time"]
        verbose_name = "Exam"
        verbose_name_plural = "Exams"
        indexes = [
            models.Index(fields=["subject", "date"]),
            models.Index(fields=["date", "type"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.subject.code} {self.date})"


class ExamResult(BaseModel):
    """A student's graded result for a subject exam (``types.ts`` ``ExamResult``).

    ``exam`` is a free-form label (e.g. "Internal 1", "Semester") to match the
    app's ``ExamResult.exam: string``; the optional ``exam_ref`` FK links to a
    concrete :class:`Exam` row when available.
    """

    student = models.ForeignKey(
        "students.Student",
        on_delete=models.CASCADE,
        related_name="exam_results",
    )
    subject = models.ForeignKey(
        "academics.Subject",
        on_delete=models.CASCADE,
        related_name="exam_results",
    )
    # Optional link to a concrete Exam row; the display label lives in ``exam``.
    exam_ref = models.ForeignKey(
        Exam,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="results",
    )
    exam = models.CharField(max_length=128, blank=True, default="")
    marks = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    max_marks = models.DecimalField(max_digits=6, decimal_places=2, default=100)
    grade = models.CharField(max_length=8, blank=True, default="")
    grade_point = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    credits = models.DecimalField(max_digits=4, decimal_places=1, default=0)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Exam Result"
        verbose_name_plural = "Exam Results"
        indexes = [
            models.Index(fields=["student", "subject"]),
            models.Index(fields=["student"]),
        ]

    def __str__(self):
        return f"{self.student.roll_no} {self.subject.code} {self.exam}: {self.marks}/{self.max_marks}"


class MarksSheet(BaseModel):
    """Faculty marks-entry for one exam of a :class:`~faculty.models.FacultyClass`.

    Mirrors ``types.ts`` ``MarksSheet`` (classId/exam/maxMarks/enteredOn/entries).
    The per-student marks live in child :class:`MarkEntry` rows. Upserted by
    ``(faculty_class, exam)`` in the service layer.
    """

    faculty_class = models.ForeignKey(
        "faculty.FacultyClass",
        on_delete=models.CASCADE,
        related_name="marks_sheets",
    )
    exam = models.CharField(max_length=128)
    max_marks = models.DecimalField(max_digits=6, decimal_places=2, default=100)
    entered_on = models.DateTimeField(db_index=True)

    class Meta:
        ordering = ["-entered_on"]
        verbose_name = "Marks Sheet"
        verbose_name_plural = "Marks Sheets"
        constraints = [
            models.UniqueConstraint(
                fields=["faculty_class", "exam"],
                condition=models.Q(is_deleted=False),
                name="uniq_markssheet_class_exam",
            )
        ]
        indexes = [
            models.Index(fields=["faculty_class"]),
        ]

    def __str__(self):
        return f"{self.faculty_class_id} — {self.exam}"


class MarkEntry(BaseModel):
    """A single student's marks within a :class:`MarksSheet` (``types.ts`` ``MarkEntry``)."""

    sheet = models.ForeignKey(
        MarksSheet,
        on_delete=models.CASCADE,
        related_name="entries",
    )
    student = models.ForeignKey(
        "students.Student",
        on_delete=models.CASCADE,
        related_name="mark_entries",
    )
    marks = models.DecimalField(max_digits=6, decimal_places=2, default=0)

    class Meta:
        ordering = ["student__roll_no"]
        verbose_name = "Mark Entry"
        verbose_name_plural = "Mark Entries"
        constraints = [
            models.UniqueConstraint(
                fields=["sheet", "student"],
                condition=models.Q(is_deleted=False),
                name="uniq_markentry_sheet_student",
            )
        ]
        indexes = [
            models.Index(fields=["sheet"]),
        ]

    def __str__(self):
        return f"{self.student.roll_no}: {self.marks}"
