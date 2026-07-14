"""Business-logic layer for the academics app.

Each service extends :class:`core.services.BaseService` so writes auto-stamp
``created_by``/``updated_by``, emit an :class:`~core.models.AuditLog` row, and
invalidate the relevant cached views. Timetable and subject reads are cached
(TTL 3600s per the contract); any write to a subject or class session busts the
``timetable``/``subjects`` cache prefixes.
"""
from __future__ import annotations

from collections import OrderedDict
from decimal import Decimal
from typing import Any

from rest_framework.exceptions import ValidationError

from core.cache import invalidate_prefix
from core.services import BaseService

from academics.models import (
    ClassSession,
    Department,
    Program,
    Section,
    Semester,
    Subject,
)
from academics.repositories import (
    ClassSessionRepository,
    DepartmentRepository,
    ProgramRepository,
    SectionRepository,
    SemesterRepository,
    SubjectRepository,
)

# Cache key prefixes owned by this app.
TIMETABLE_PREFIX = "timetable"
SUBJECTS_PREFIX = "subjects"


class DepartmentService(BaseService):
    model = Department
    repository_class = DepartmentRepository
    entity_name = "Department"

    def create(self, **data):
        """Restore a soft-deleted department instead of inserting a duplicate.

        ``code`` is unique at the DB level, and the constraint counts
        soft-deleted rows — so re-creating a department whose code matches a
        previously-deleted one would raise an IntegrityError (surfacing as a
        500). If a soft-deleted department already owns this code, undelete it
        and apply the new values; this also re-links any programs/students that
        still point at that row. Otherwise create normally.
        """
        code = data.get("code")
        if code:
            existing = self.model.all_objects.filter(code=code, is_deleted=True).first()
            if existing is not None:
                existing.restore()
                return self.update(existing, **data)
        return super().create(**data)

    def delete(self, instance):
        """Refuse to delete a department that still owns records.

        Departments are soft-deleted, so the FK ``on_delete`` rules never fire —
        deleting one would silently orphan its programs/students/subjects/faculty
        (their FKs would keep pointing at a now-hidden row, which breaks the
        dependent queries, e.g. ``/programs?department=<id>`` starts 400-ing).
        Block the delete with a clear message so those records are reassigned or
        removed first. Counts use the default manager, so already soft-deleted
        children don't keep a department pinned.
        """
        blockers = []
        for count, noun in (
            (instance.programs.count(), "program"),
            (instance.students.count(), "student"),
            (instance.subjects.count(), "subject"),
            (instance.faculty_profiles.count(), "faculty member"),
        ):
            if count:
                blockers.append(f"{count} {noun}{'' if count == 1 else 's'}")
        if blockers:
            raise ValidationError(
                f'Cannot delete department "{instance.name}" — it still has '
                f"{', '.join(blockers)}. Reassign or remove them first."
            )
        return super().delete(instance)


class ProgramService(BaseService):
    model = Program
    repository_class = ProgramRepository
    entity_name = "Program"

    def create(self, **data):
        """Create the program and auto-generate its semesters.

        A program spans ``duration_years * 2`` semesters (4yr → 1..8, 3yr → 1..6,
        2yr → 1..4). Semester generation is idempotent, so re-running only fills
        the gaps.
        """
        program = super().create(**data)
        self.ensure_semesters(program)
        return program

    def ensure_semesters(self, program) -> int:
        """Idempotently create the ``1..duration_years*2`` semesters for a program.

        Returns the number of semesters newly created. Only missing numbers are
        inserted (soft-deleted rows are restored rather than duplicated), so this
        is safe to call repeatedly.
        """
        total = (program.duration_years or 0) * 2
        if total <= 0:
            return 0

        existing = set(
            Semester.all_objects.filter(program=program).values_list(
                "number", flat=True
            )
        )
        created = 0
        for number in range(1, total + 1):
            if number in existing:
                # Restore a soft-deleted semester rather than leaving a gap.
                sem = Semester.all_objects.filter(
                    program=program, number=number, is_deleted=True
                ).first()
                if sem is not None:
                    sem.restore()
                continue
            Semester.objects.create(
                program=program,
                number=number,
                created_by=self._actor_or_none(),
                updated_by=self._actor_or_none(),
            )
            created += 1
        if created:
            self.invalidate_cache(program)
        return created


class SemesterService(BaseService):
    model = Semester
    repository_class = SemesterRepository
    entity_name = "Semester"


class SectionService(BaseService):
    model = Section
    repository_class = SectionRepository
    entity_name = "Section"

    def create(self, **data):
        """Create a section, guarding the ``(semester, name)`` uniqueness.

        The DB constraint is *partial* (``condition=is_deleted=False``), so DRF's
        ``ModelSerializer`` doesn't auto-generate a ``UniqueTogetherValidator``
        for it — a duplicate would otherwise reach the DB and raise an
        ``IntegrityError`` that surfaces as a bare 500 ("Internal server
        error."). Convert that into a clean 400: reject an active duplicate with
        a readable message, and restore a soft-deleted match instead of leaving
        an orphaned row behind a fresh insert.
        """
        semester = data.get("semester")
        name = data.get("name")
        if semester is not None and name:
            if self.model.objects.filter(semester=semester, name=name).exists():
                raise ValidationError(
                    f'Section "{name}" already exists in this semester.'
                )
            deleted = self.model.all_objects.filter(
                semester=semester, name=name, is_deleted=True
            ).first()
            if deleted is not None:
                deleted.restore()
                return self.update(deleted, **data)
        return super().create(**data)

    def invalidate_cache(self, instance=None) -> None:
        # Sections shape the timetable grid grouping.
        invalidate_prefix(TIMETABLE_PREFIX)


class SubjectService(BaseService):
    model = Subject
    repository_class = SubjectRepository
    entity_name = "Subject"

    def create(self, **data):
        """Create a subject, assigning the ``faculties`` M2M after insert.

        ``faculties`` arrives as a list of faculty *User* instances (see
        :class:`~academics.serializers.SubjectSerializer`). Each is resolved to
        its :class:`~faculty.models.FacultyProfile` — created on demand under the
        subject's department for any faculty that lacks one — before the M2M is
        set. A M2M cannot be set during ``objects.create``, so it is applied
        after the row exists. The first selection is mirrored onto the legacy
        ``faculty``/``faculty_name`` fields.
        """
        faculty_users = data.pop("faculties", None)
        if faculty_users is not None:
            self._apply_legacy_faculty(data, faculty_users)
        instance = super().create(**data)
        if faculty_users is not None:
            instance.faculties.set(
                self._resolve_profiles(faculty_users, instance.department_id)
            )
        return instance

    def update(self, instance, **data):
        """Update a subject; only reassign ``faculties`` when it was supplied."""
        has_faculties = "faculties" in data
        faculty_users = data.pop("faculties", None)
        if has_faculties:
            self._apply_legacy_faculty(data, faculty_users or [])
        instance = super().update(instance, **data)
        if has_faculties:
            instance.faculties.set(
                self._resolve_profiles(faculty_users or [], instance.department_id)
            )
        return instance

    @staticmethod
    def _resolve_profiles(faculty_users, department_id):
        """Map faculty ``User`` objects to their ``FacultyProfile`` rows.

        A faculty user may not have a profile yet (e.g. one created before
        profiles were auto-provisioned), so missing profiles are created under
        ``department_id`` — the subject's department — as a sensible default.
        Returns a list of ``FacultyProfile`` instances for the M2M.
        """
        from faculty.models import FacultyProfile

        profiles = []
        for user in faculty_users:
            profile, _ = FacultyProfile.objects.get_or_create(
                user=user,
                defaults={"department_id": department_id},
            )
            profiles.append(profile)
        return profiles

    @staticmethod
    def _apply_legacy_faculty(data, faculty_users):
        """Mirror the first selected faculty onto the legacy single-faculty
        ``faculty`` FK + ``faculty_name``.

        The admin console only sends ``faculties``; keeping the legacy fields in
        sync preserves the attendance ``by_faculty`` rollup and the mobile
        ``SubjectAppSerializer`` (which read the singular ``faculty``).
        """
        first = faculty_users[0] if faculty_users else None
        data["faculty"] = first
        data["faculty_name"] = first.full_name if first else ""

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(SUBJECTS_PREFIX)
        invalidate_prefix(TIMETABLE_PREFIX)


class ClassSessionService(BaseService):
    model = ClassSession
    repository_class = ClassSessionRepository
    entity_name = "ClassSession"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(TIMETABLE_PREFIX)


# --- Read-only per-student academic services (mobile API contract v1) --------
class AcademicRecordService:
    """Builds the student's academic record for ``GET /academics/{user_id}``.

    Read-only aggregator (no writes to audit), so it does not extend
    :class:`BaseService`. The caller resolves + access-checks the
    :class:`students.Student`; this service only shapes the spec payload.
    """

    def __init__(self, actor=None, ip=None):
        self.actor = actor
        self.ip = ip

    def academic_record(self, student) -> dict[str, Any]:
        return {
            "degree": student.program.name if student.program_id else "",
            "department": student.department.name if student.department_id else "",
            "semester": student.semester.number if student.semester_id else 0,
            "section": student.section.name if student.section_id else "",
            "mentor": student.mentor_name,
            "cgpa": float(student.cgpa or 0),
        }


class AcademicProgressService:
    """Builds academic-progress analytics for ``GET /progress/{user_id}``.

    GPA trend + overall CGPA come from the student's :class:`exams.ExamResult`
    rows (reusing :meth:`exams.services.ExamResultService.gpa_for_student` for the
    credit-weighted overall CGPA); ``ai_insights`` are heuristic cards derived
    from those same aggregates (no external LLM call).
    """

    def __init__(self, actor=None, ip=None):
        self.actor = actor
        self.ip = ip

    def progress(self, student) -> dict[str, Any]:
        from exams.services import ExamResultService

        trend = self._gpa_trend(student.pk)
        overall = ExamResultService(actor=self.actor).gpa_for_student(student.pk)
        semester_gpa = trend[-1]["gpa"] if trend else overall
        return {
            "gpa_trend": trend,
            "semester_gpa": semester_gpa,
            "overall_cgpa": overall,
            "ai_insights": self._ai_insights(student, trend, overall),
        }

    def _gpa_trend(self, student_id) -> list[dict[str, Any]]:
        """Credit-weighted GPA per exam term for a student, in chronological order.

        Groups the student's :class:`exams.ExamResult` rows by their ``exam``
        term label (the app's per-term axis) and computes
        Σ(grade_point·credits)/Σ(credits) per group.
        """
        from exams.models import ExamResult

        rows = (
            ExamResult.objects.filter(student_id=student_id)
            .order_by("created_at")
            .values_list("exam", "grade_point", "credits")
        )
        groups: "OrderedDict[str, list[Decimal]]" = OrderedDict()
        for label, grade_point, credits in rows:
            key = label or "—"
            credits = credits or Decimal("0")
            acc = groups.setdefault(key, [Decimal("0"), Decimal("0")])
            acc[0] += (grade_point or Decimal("0")) * credits
            acc[1] += credits
        trend = []
        for label, (points, total_credits) in groups.items():
            gpa = round(float(points / total_credits), 2) if total_credits else 0.0
            trend.append({"semester": label, "gpa": gpa})
        return trend

    def _ai_insights(self, student, trend, overall) -> list[dict[str, Any]]:
        cards: list[dict[str, Any]] = []
        if overall:
            tone = "success" if overall >= 8 else "warning" if overall >= 6 else "danger"
            cards.append(
                {
                    "id": "insight-cgpa",
                    "title": "CGPA standing",
                    "body": (
                        f"Your overall CGPA is {overall}."
                        + (
                            " Excellent — keep it up."
                            if overall >= 8
                            else " Solid; a focused push can lift it further."
                            if overall >= 6
                            else " Below par; prioritise weaker subjects."
                        )
                    ),
                    "tone": tone,
                    "metric": str(overall),
                }
            )
        if len(trend) >= 2:
            delta = round(trend[-1]["gpa"] - trend[-2]["gpa"], 2)
            if delta > 0:
                cards.append(
                    {
                        "id": "insight-trend",
                        "title": "Upward trend",
                        "body": f"Your GPA rose {delta} since the previous term.",
                        "tone": "success",
                        "metric": f"+{delta}",
                    }
                )
            elif delta < 0:
                cards.append(
                    {
                        "id": "insight-trend",
                        "title": "Dip in GPA",
                        "body": f"Your GPA fell {abs(delta)} since the previous term.",
                        "tone": "warning",
                        "metric": str(delta),
                    }
                )
        return cards
