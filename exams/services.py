"""Business-logic layer for the exams app.

Each service extends :class:`core.services.BaseService` so writes auto-stamp
``created_by``/``updated_by``, emit an :class:`~core.models.AuditLog` row, and
invalidate cached exam views. Exam/result reads are cached under the ``exams``
prefix; any write busts that prefix.

The GPA / marks-sheet business rules live here (never in views):

* :meth:`ExamResultService.gpa_for_student` — credit-weighted GPA
  (Σ gradePoint·credits / Σ credits).
* :meth:`MarksSheetService.save_sheet` — upsert a marks sheet + its per-student
  entries by ``(faculty_class, exam)``, mirroring the app's
  ``facultyMarksService.saveSheet``.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from core.cache import invalidate_prefix
from core.services import BaseService

from exams.models import Exam, ExamResult, MarkEntry, MarksSheet
from exams.repositories import (
    ExamRepository,
    ExamResultRepository,
    MarkEntryRepository,
    MarksSheetRepository,
)

# Cache-key prefix owned by this app.
EXAMS_PREFIX = "exams"


class ExamService(BaseService):
    model = Exam
    repository_class = ExamRepository
    entity_name = "Exam"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(EXAMS_PREFIX)


class ExamResultService(BaseService):
    model = ExamResult
    repository_class = ExamResultRepository
    entity_name = "ExamResult"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(EXAMS_PREFIX)

    def gpa_for_student(self, student_id) -> float:
        """Credit-weighted GPA for a student across their exam results.

        GPA = Σ(grade_point · credits) / Σ(credits). Returns ``0.0`` when the
        student has no credited results (avoids divide-by-zero).
        """
        rows = ExamResult.objects.filter(student_id=student_id).values_list(
            "grade_point", "credits"
        )
        total_points = Decimal("0")
        total_credits = Decimal("0")
        for grade_point, credits in rows:
            credits = credits or Decimal("0")
            total_points += (grade_point or Decimal("0")) * credits
            total_credits += credits
        if total_credits == 0:
            return 0.0
        return round(float(total_points / total_credits), 2)

    @staticmethod
    def _is_external(result) -> bool:
        """Classify an :class:`ExamResult` as external (semester/end) vs internal.

        Prefers the linked :class:`Exam` type; falls back to the free-form
        ``exam`` label. Internal assessments + quizzes count as *internal*; the
        semester/end examination counts as *external*.
        """
        ref = result.exam_ref
        if ref is not None:
            return ref.type == Exam.TYPE_SEMESTER
        label = (result.exam or "").lower()
        return any(k in label for k in ("semester", "external", "final", "end"))

    def subject_marks_for_student(self, student_id):
        """Per-subject marks breakdown for the mobile ``GET /marks/{user_id}``.

        Returns ``[{subject, internal, external, total, grade}]`` (snake_case per
        the contract). Internal/external marks are summed from the student's
        :class:`ExamResult` rows for each subject; ``grade`` prefers the external
        (semester) grade, otherwise the first available grade.
        """
        results = (
            ExamResult.objects.filter(student_id=student_id)
            .select_related("subject", "exam_ref")
            .order_by("subject__code")
        )
        by_subject: dict = {}
        for r in results:
            entry = by_subject.setdefault(
                r.subject_id,
                {
                    "subject_id": str(r.subject_id) if r.subject_id else "",
                    "subject": r.subject.name if r.subject else "",
                    "internal": Decimal("0"),
                    "external": Decimal("0"),
                    "grade": "",
                    "grade_point": Decimal("0"),
                    "credits": Decimal("0"),
                },
            )
            marks = r.marks or Decimal("0")
            # Credits are a property of the subject (same across its result rows).
            if r.credits:
                entry["credits"] = r.credits
            if self._is_external(r):
                entry["external"] += marks
                if r.grade:
                    entry["grade"] = r.grade
                if r.grade_point is not None:
                    entry["grade_point"] = r.grade_point
            else:
                entry["internal"] += marks
                if not entry["grade"] and r.grade:
                    entry["grade"] = r.grade
                # Fall back to an internal row's grade point if no external one.
                if not entry["grade_point"] and r.grade_point is not None:
                    entry["grade_point"] = r.grade_point

        subjects = []
        for entry in by_subject.values():
            total = entry["internal"] + entry["external"]
            subjects.append(
                {
                    "subject_id": entry["subject_id"],
                    "subject": entry["subject"],
                    "internal": float(entry["internal"]),
                    "external": float(entry["external"]),
                    "total": float(total),
                    "grade": entry["grade"],
                    "grade_point": float(entry["grade_point"]),
                    "credits": float(entry["credits"]),
                }
            )
        return subjects


class MarksSheetService(BaseService):
    model = MarksSheet
    repository_class = MarksSheetRepository
    entity_name = "MarksSheet"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(EXAMS_PREFIX)

    @transaction.atomic
    def save_sheet(self, faculty_class, exam: str, max_marks, entries) -> MarksSheet:
        """Upsert a marks sheet + per-student entries by ``(faculty_class, exam)``.

        ``entries`` is a list of ``{"student": <Student>, "marks": <Decimal>}``.
        Existing entries for the sheet are replaced (soft-deleted then recreated)
        so a re-save reflects the submitted roster exactly. Mirrors the app's
        ``facultyMarksService.saveSheet`` upsert semantics.
        """
        sheet = (
            MarksSheet.objects.filter(faculty_class=faculty_class, exam=exam).first()
        )
        now = timezone.now()
        if sheet is None:
            sheet = self.create(
                faculty_class=faculty_class,
                exam=exam,
                max_marks=max_marks,
                entered_on=now,
            )
        else:
            sheet = self.update(
                sheet, max_marks=max_marks, entered_on=now
            )
            # Drop the previous entries so the sheet reflects the new roster.
            MarkEntry.objects.filter(sheet=sheet).delete()

        actor = self._actor_or_none()
        for entry in entries:
            MarkEntry.objects.create(
                sheet=sheet,
                student=entry["student"],
                marks=entry.get("marks", Decimal("0")),
                created_by=actor,
                updated_by=actor,
            )
        self.invalidate_cache(sheet)
        return sheet


class MarkEntryService(BaseService):
    model = MarkEntry
    repository_class = MarkEntryRepository
    entity_name = "MarkEntry"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(EXAMS_PREFIX)
