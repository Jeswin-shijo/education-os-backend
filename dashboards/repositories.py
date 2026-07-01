"""Data-access layer for the dashboards app.

Read-only aggregation queries over the source apps' models. Each repository
method returns a plain queryset / scalar; the services compose them into the
per-role dashboard payloads. Nothing here mutates data (the dashboards app is a
pure read/cache layer), so there is no :class:`core.repositories.BaseRepository`
subclass — these are stateless query helpers.

Kept deliberately thin and dependency-light so the services stay the single
place the aggregation shape is decided.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db.models import Count, Q, Sum

from academics.models import ClassSession
from assignments.models import Assignment, Submission
from attendance.models import AttendanceRecord, AttendanceStatus
from chat.models import ChatThread
from exams.models import Exam
from fees.models import FeeInvoice
from guardians.models import ParentLink
from leave.models import LeaveRequest
from notifications.models import Notification
from quizzes.models import Quiz


class DashboardRepository:
    """Stateless read helpers powering the dashboard aggregations."""

    # -- students -------------------------------------------------------------
    def student_for_user(self, user):
        """The :class:`students.Student` linked to ``user`` (or ``None``)."""
        from students.models import Student

        return (
            Student.objects.select_related(
                "user", "program", "department", "semester", "section"
            )
            .filter(user=user)
            .first()
        )

    def student_by_id(self, student_id):
        from students.models import Student

        return (
            Student.objects.select_related(
                "user", "program", "department", "semester", "section"
            )
            .filter(pk=student_id)
            .first()
        )

    # -- guardians / parent ---------------------------------------------------
    def primary_child_link(self, parent_user):
        """The parent's primary child link (falls back to first live link)."""
        qs = (
            ParentLink.objects.select_related(
                "student",
                "student__program",
                "student__department",
                "student__semester",
                "student__section",
            )
            .filter(parent=parent_user)
            .order_by("-is_primary", "student__roll_no")
        )
        return qs.first()

    # -- attendance -----------------------------------------------------------
    def attendance_percent(self, student) -> int:
        """Overall attendance percent for a student (late counts as attended).

        Mirrors ``attendance/overall`` so the dashboard matches the standalone
        endpoint exactly (integer percent, 0 when no records).
        """
        agg = AttendanceRecord.objects.filter(student=student).aggregate(
            total=Count("id"),
            attended=Count(
                "id", filter=Q(status__in=AttendanceStatus.ATTENDED)
            ),
        )
        total = agg["total"] or 0
        attended = agg["attended"] or 0
        return round(attended / total * 100) if total else 0

    # -- assignments ----------------------------------------------------------
    def pending_assignment_count(self, student) -> int:
        """Assignments visible to the student with no live submission yet.

        An assignment counts as *pending* when the student has not submitted it
        (no live :class:`Submission` row). Scoped to the student's section when a
        section is set, else all subject-wide assignments.
        """
        qs = Assignment.objects.all()
        if student.section_id:
            qs = qs.filter(
                Q(faculty_class__section_id=student.section_id)
                | Q(faculty_class__isnull=True)
            )
        submitted_ids = Submission.objects.filter(student=student).values_list(
            "assignment_id", flat=True
        )
        return qs.exclude(id__in=submitted_ids).count()

    # -- timetable ------------------------------------------------------------
    def today_sessions(self, section_id, today_code):
        """Today's :class:`ClassSession` rows for a section (ordered by start)."""
        if today_code is None or not section_id:
            return ClassSession.objects.none()
        return (
            ClassSession.objects.select_related("subject")
            .filter(section_id=section_id, day=today_code)
            .order_by("start")
        )

    # -- fees -----------------------------------------------------------------
    def due_fees_total(self, student) -> Decimal:
        """Sum of the student's unpaid invoice amounts (``Decimal``)."""
        agg = (
            FeeInvoice.objects.filter(student=student)
            .exclude(status=FeeInvoice.STATUS_PAID)
            .aggregate(total=Sum("amount"))
        )
        return agg["total"] or Decimal("0")

    # -- exams ----------------------------------------------------------------
    def next_exam_for_student(self, student):
        """The student's next upcoming :class:`Exam` (today onwards) or ``None``.

        Scoped to the student's department subjects when a department is set so a
        student only sees exams for subjects in their department; ordered by date
        then time so the soonest exam is returned.
        """
        qs = Exam.objects.select_related("subject").filter(date__gte=date.today())
        if student.department_id:
            qs = qs.filter(subject__department_id=student.department_id)
        return qs.order_by("date", "time").first()

    # -- notifications --------------------------------------------------------
    def unread_notification_count(self, user) -> int:
        """Unread notification count for a user (directly-targeted rows).

        Matches ``notifications/unread-count`` semantics: unread rows whose
        recipient is the user.
        """
        return Notification.objects.filter(recipient=user, read=False).count()

    # -- parent: leave approvals + chat --------------------------------------
    def pending_child_leaves(self, child) -> int:
        """Pending leave requests filed by the child's login account.

        Mirrors the parent app's ``pendingApprovals`` (``leaveService.list``
        filtered to ``status === 'pending'``). Returns 0 when the child has no
        linked login (nothing to approve).
        """
        if child is None or child.user_id is None:
            return 0
        return LeaveRequest.objects.filter(
            user_id=child.user_id, status=LeaveRequest.STATUS_PENDING
        ).count()

    def unread_chat_count(self, user) -> int:
        """Sum of the user's unread chat counters across their threads.

        Matches the parent app's ``unreadChats`` (Σ ``ChatThread.unread`` for the
        requesting participant). Each thread stores a per-user unread map, so we
        sum ``unread_for(user)`` across the threads the user participates in.
        """
        threads = ChatThread.objects.filter(
            Q(teacher=user) | Q(parent=user)
        ).only("unread_count", "teacher_id", "parent_id")
        return sum(t.unread_for(user) for t in threads)

    # -- faculty --------------------------------------------------------------
    def faculty_profile_for_user(self, user):
        """The :class:`faculty.FacultyProfile` for ``user`` (or ``None``)."""
        from faculty.models import FacultyProfile

        return (
            FacultyProfile.objects.select_related("user", "department")
            .filter(user=user)
            .first()
        )

    def faculty_classes(self, profile):
        """The faculty's classes (with subject/section for the today grid)."""
        from faculty.models import FacultyClass

        return (
            FacultyClass.objects.select_related("subject", "semester", "section")
            .filter(faculty=profile)
            .order_by("subject__code")
        )

    def faculty_student_count(self, profile) -> int:
        """Total students across the faculty's classes (Σ ``student_count``)."""
        agg = self.faculty_classes(profile).aggregate(total=Sum("student_count"))
        return int(agg["total"] or 0)

    def faculty_pending_assignments(self, profile, horizon_date) -> int:
        """Faculty assignments due on/before ``horizon_date`` (pending window).

        Mirrors the faculty app rule: assignments whose ``dueDate`` is past or
        within the next few days count as pending. Scoped to the faculty's own
        classes.
        """
        class_ids = list(
            self.faculty_classes(profile).values_list("id", flat=True)
        )
        if not class_ids:
            return 0
        return Assignment.objects.filter(
            faculty_class_id__in=class_ids, due_date__date__lte=horizon_date
        ).count()

    def faculty_quiz_count(self, profile) -> int:
        """Quizzes scoped to the faculty's classes."""
        class_ids = list(
            self.faculty_classes(profile).values_list("id", flat=True)
        )
        if not class_ids:
            return 0
        return Quiz.objects.filter(faculty_class_id__in=class_ids).count()
