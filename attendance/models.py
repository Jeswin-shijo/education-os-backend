"""Attendance domain models.

Two complementary shapes:

* :class:`AttendanceRecord` — the per-student, per-subject daily attendance row.
  This is the source of truth for the *student-facing* reads (``types.ts``
  ``AttendanceRecord`` / ``AttendanceSummary`` and the overall percentage).
* :class:`AttendanceSession` + :class:`AttendanceEntry` — a *faculty-saved*
  attendance take for one :class:`faculty.FacultyClass` on a given date. The
  session groups the per-student entries a faculty member records in the app
  (``types.ts`` ``AttendanceSession`` with ``entries: ClassAttendanceEntry[]``).

Entries mirror the faculty roster pattern (see ``faculty.RosterEntry``): the
student is referenced by an optional ``student_ref`` UUID (linking to
``students.Student`` when available) plus a denormalized ``roll_no`` so a session
can be read back as ``{studentId, status}`` regardless of link state.

Every model extends :class:`core.models.BaseModel` (UUID PK, audit fields,
soft-delete).
"""
from django.db import models

from core.models import BaseModel


class AttendanceStatus:
    """Shared status vocabulary (mirrors ``types.ts`` attendance status)."""

    PRESENT = "present"
    ABSENT = "absent"
    LATE = "late"
    CHOICES = [
        (PRESENT, "Present"),
        (ABSENT, "Absent"),
        (LATE, "Late"),
    ]
    # Statuses that count towards "attended" in summaries (late still counts).
    ATTENDED = (PRESENT, LATE)


class AttendanceRecord(BaseModel):
    """One student's attendance for one subject on one date.

    Drives the student-facing summary/records/overall endpoints. The
    denormalized ``subject_code``/``subject_name`` avoid a join when serializing
    the app's ``AttendanceSummary``.
    """

    student = models.ForeignKey(
        "students.Student",
        on_delete=models.CASCADE,
        related_name="attendance_records",
    )
    subject = models.ForeignKey(
        "academics.Subject",
        on_delete=models.CASCADE,
        related_name="attendance_records",
    )
    date = models.DateField(db_index=True)
    status = models.CharField(
        max_length=16,
        choices=AttendanceStatus.CHOICES,
        default=AttendanceStatus.PRESENT,
        db_index=True,
    )

    class Meta:
        ordering = ["-date"]
        verbose_name = "Attendance Record"
        verbose_name_plural = "Attendance Records"
        constraints = [
            models.UniqueConstraint(
                fields=["student", "subject", "date"],
                condition=models.Q(is_deleted=False),
                name="uniq_attendance_student_subject_date",
            )
        ]
        indexes = [
            models.Index(fields=["student", "subject"]),
            models.Index(fields=["student", "date"]),
        ]

    def __str__(self):
        return f"{self.student_id} {self.subject_id} {self.date} {self.status}"


class AttendanceSession(BaseModel):
    """A faculty-recorded attendance take for a class on a date.

    Uniqueness is per ``(faculty_class, date)`` so saving the same class/date
    upserts rather than duplicating (see :class:`AttendanceSessionService`).
    """

    faculty_class = models.ForeignKey(
        "faculty.FacultyClass",
        on_delete=models.CASCADE,
        related_name="attendance_sessions",
    )
    date = models.DateField(db_index=True)

    class Meta:
        ordering = ["-date"]
        verbose_name = "Attendance Session"
        verbose_name_plural = "Attendance Sessions"
        constraints = [
            models.UniqueConstraint(
                fields=["faculty_class", "date"],
                condition=models.Q(is_deleted=False),
                name="uniq_attendance_session_class_date",
            )
        ]
        indexes = [
            models.Index(fields=["faculty_class", "date"]),
        ]

    def __str__(self):
        return f"Session {self.faculty_class_id} @ {self.date}"


class AttendanceEntry(BaseModel):
    """A single student's status within an :class:`AttendanceSession`.

    ``student_ref`` links to a ``students.Student`` UUID when known; ``roll_no``
    is denormalized so the entry always serializes to ``{studentId, status}``.
    """

    session = models.ForeignKey(
        AttendanceSession,
        on_delete=models.CASCADE,
        related_name="entries",
    )
    # Link to students.Student (kept nullable to mirror faculty.RosterEntry).
    student_ref = models.UUIDField(null=True, blank=True, db_index=True)
    roll_no = models.CharField(max_length=32, blank=True, default="")
    status = models.CharField(
        max_length=16,
        choices=AttendanceStatus.CHOICES,
        default=AttendanceStatus.PRESENT,
    )

    class Meta:
        ordering = ["roll_no"]
        verbose_name = "Attendance Entry"
        verbose_name_plural = "Attendance Entries"
        indexes = [
            models.Index(fields=["session"]),
            models.Index(fields=["student_ref"]),
        ]

    def __str__(self):
        return f"{self.roll_no or self.student_ref} — {self.status}"
