"""Assignment domain models.

An :class:`Assignment` is created by a faculty member for a subject (and,
optionally, a specific :class:`faculty.FacultyClass`). It carries the shared
metadata every student sees — ``title``/``description``/``due_date``/
``max_marks`` — plus a ``status`` that mirrors the app's faculty view of an
assignment's lifecycle (``pending``/``submitted``/``graded``/``late``).

A :class:`Submission` is one student's turn-in for an assignment: the uploaded
``file_name``, ``submitted_at`` timestamp, and an optional ``grade`` once the
faculty marks it. The mobile student-facing ``Assignment`` shape (``types.ts``)
carries a *per-student* ``status``/``submittedAt``/``grade``/``attachmentName``;
those are derived at read time from the current student's submission (see
``serializers.StudentAssignmentSerializer``).

Every model extends :class:`core.models.BaseModel` (UUID PK, audit fields,
soft-delete).
"""
from django.db import models

from core.models import BaseModel


class Assignment(BaseModel):
    """A faculty-created assignment for a subject / class."""

    STATUS_PENDING = "pending"
    STATUS_SUBMITTED = "submitted"
    STATUS_GRADED = "graded"
    STATUS_LATE = "late"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_SUBMITTED, "Submitted"),
        (STATUS_GRADED, "Graded"),
        (STATUS_LATE, "Late"),
    ]

    subject = models.ForeignKey(
        "academics.Subject",
        on_delete=models.CASCADE,
        related_name="assignments",
    )
    # Optional link to a concrete teaching assignment (a subject/section taught
    # by a faculty member). Null for subject-wide assignments.
    faculty_class = models.ForeignKey(
        "faculty.FacultyClass",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assignments",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    due_date = models.DateTimeField()
    max_marks = models.PositiveIntegerField(default=100)
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )

    class Meta:
        ordering = ["-due_date"]
        verbose_name = "Assignment"
        verbose_name_plural = "Assignments"
        indexes = [
            models.Index(fields=["subject", "status"]),
            models.Index(fields=["faculty_class"]),
            models.Index(fields=["due_date"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.subject.code})"


class Submission(BaseModel):
    """A single student's submission for an :class:`Assignment`."""

    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name="submissions",
    )
    student = models.ForeignKey(
        "students.Student",
        on_delete=models.CASCADE,
        related_name="assignment_submissions",
    )
    file_name = models.CharField(max_length=512)
    submitted_at = models.DateTimeField()
    grade = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-submitted_at"]
        verbose_name = "Submission"
        verbose_name_plural = "Submissions"
        constraints = [
            # One live submission per (assignment, student); re-submitting
            # updates the existing row rather than creating a duplicate.
            models.UniqueConstraint(
                fields=["assignment", "student"],
                condition=models.Q(is_deleted=False),
                name="uniq_submission_assignment_student",
            )
        ]
        indexes = [
            models.Index(fields=["assignment"]),
            models.Index(fields=["student"]),
        ]

    def __str__(self):
        return f"{self.student.roll_no} → {self.assignment.title}"
