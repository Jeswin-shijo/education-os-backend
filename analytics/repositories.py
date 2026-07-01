"""Data-access helpers for the analytics aggregations.

These functions wrap the soft-delete-aware default managers of the domain apps
(``academics``/``students``/``faculty``/``attendance``/``exams``/``fees``/
``placement``/``complaints``) and return plain querysets or lightweight rows.
All analytics reads are cheap COUNT/AVG rollups; each uses ``.only()`` /
aggregation where possible to avoid pulling wide rows or N+1 joins.

No writes ever happen here — the analytics app is read-only.
"""
from __future__ import annotations

from decimal import Decimal

from django.db.models import Avg, Count, F, Q, Sum

from academics.models import Department, Subject
from attendance.models import AttendanceRecord
from complaints.models import Complaint
from exams.models import ExamResult
from faculty.models import FacultyClass, FacultyProfile
from fees.models import FeeInvoice
from placement.models import PlacementApplication, PlacementOpening
from students.models import Student

# Statuses that count as "attended" (present + late).
_ATTENDED = ("present", "late")


class AnalyticsRepository:
    """Read-only queries backing the HOD + Principal analytics endpoints.

    Every method returns querysets/instances or plain aggregates from the
    soft-delete-aware ``objects`` managers. HOD-scoped variants accept a
    ``department`` so the service can restrict institution-wide data to one
    department.
    """

    # -- academics -------------------------------------------------------
    def departments(self):
        return Department.objects.all().order_by("code")

    def department_for_user(self, user):
        """Resolve the department a HOD/faculty user belongs to.

        Uses the user's :class:`faculty.FacultyProfile` (the teaching identity
        that carries a department). Returns ``None`` when the user has no
        profile (institution-wide roles fall back to no scope).
        """
        profile = (
            FacultyProfile.objects.select_related("department")
            .filter(user=user)
            .first()
        )
        return profile.department if profile else None

    # -- students --------------------------------------------------------
    def students(self, department=None):
        qs = Student.objects.filter(status=Student.STATUS_ACTIVE)
        if department is not None:
            qs = qs.filter(department=department)
        return qs

    def student_count(self, department=None) -> int:
        return self.students(department).count()

    def students_by_department(self):
        """[(dept_code, count)] active students grouped by department code."""
        rows = (
            Student.objects.filter(status=Student.STATUS_ACTIVE)
            .values("department__code")
            .annotate(count=Count("id"))
            .order_by("department__code")
        )
        return [
            {"code": r["department__code"] or "—", "count": r["count"]}
            for r in rows
        ]

    def avg_cgpa(self, department=None) -> Decimal | None:
        return self.students(department).aggregate(v=Avg("cgpa"))["v"]

    # -- faculty ---------------------------------------------------------
    def faculty_profiles(self, department=None):
        qs = FacultyProfile.objects.select_related("user", "department")
        if department is not None:
            qs = qs.filter(department=department)
        return qs

    def faculty_count(self, department=None) -> int:
        return self.faculty_profiles(department).count()

    def faculty_by_department(self):
        rows = (
            FacultyProfile.objects.values("department__code")
            .annotate(count=Count("id"))
            .order_by("department__code")
        )
        return [
            {"code": r["department__code"] or "—", "count": r["count"]}
            for r in rows
        ]

    def faculty_classes(self, department=None):
        qs = FacultyClass.objects.select_related(
            "subject", "faculty", "faculty__user", "faculty__department"
        )
        if department is not None:
            qs = qs.filter(faculty__department=department)
        return qs

    def class_count(self, department=None) -> int:
        return self.faculty_classes(department).count()

    # -- exams / results -------------------------------------------------
    def exam_results(self, department=None):
        qs = ExamResult.objects.select_related("subject", "student")
        if department is not None:
            qs = qs.filter(student__department=department)
        return qs

    def marks_percent_by_subject(self, department=None):
        """[(subject_code, avg_percent)] mean marks% per subject."""
        qs = self.exam_results(department).filter(max_marks__gt=0)
        rows = (
            qs.values("subject__code")
            .annotate(
                pct=Avg(F("marks") * Decimal("100") / F("max_marks"))
            )
            .order_by("subject__code")
        )
        return [
            {"subject": r["subject__code"] or "—", "percent": _pct(r["pct"])}
            for r in rows
        ]

    def student_marks_percent(self, department=None):
        """[(student, avg_percent)] mean marks% per student (for grade bands)."""
        qs = self.exam_results(department).filter(max_marks__gt=0)
        rows = (
            qs.values(
                "student__id", "student__full_name", "student__roll_no"
            )
            .annotate(pct=Avg(F("marks") * Decimal("100") / F("max_marks")))
            .order_by("-pct")
        )
        return [
            {
                "id": str(r["student__id"]),
                "name": r["student__full_name"],
                "rollNo": r["student__roll_no"],
                "percent": _pct(r["pct"]),
            }
            for r in rows
        ]

    # -- attendance ------------------------------------------------------
    def attendance_percent(self, department=None) -> float:
        qs = AttendanceRecord.objects.all()
        if department is not None:
            qs = qs.filter(student__department=department)
        agg = qs.aggregate(
            total=Count("id"),
            attended=Count("id", filter=Q(status__in=_ATTENDED)),
        )
        return _rate(agg["attended"], agg["total"])

    def attendance_percent_by_subject(self, department=None):
        qs = AttendanceRecord.objects.all()
        if department is not None:
            qs = qs.filter(student__department=department)
        rows = (
            qs.values("subject__code")
            .annotate(
                total=Count("id"),
                attended=Count("id", filter=Q(status__in=_ATTENDED)),
            )
            .order_by("subject__code")
        )
        return [
            {
                "subject": r["subject__code"] or "—",
                "percent": _rate(r["attended"], r["total"]),
            }
            for r in rows
        ]

    def attendance_percent_by_student(self, department=None):
        """[(student, percent)] per-student attendance %, ascending (worst first)."""
        qs = AttendanceRecord.objects.all()
        if department is not None:
            qs = qs.filter(student__department=department)
        rows = (
            qs.values(
                "student__id", "student__full_name", "student__roll_no"
            )
            .annotate(
                total=Count("id"),
                attended=Count("id", filter=Q(status__in=_ATTENDED)),
            )
        )
        out = [
            {
                "id": str(r["student__id"]),
                "name": r["student__full_name"],
                "rollNo": r["student__roll_no"],
                "percent": _rate(r["attended"], r["total"]),
            }
            for r in rows
        ]
        out.sort(key=lambda s: s["percent"])
        return out

    def attendance_monthly_trend(self, department=None, points: int = 6):
        """Recent monthly attendance % trend ([{label, percent}], oldest→newest)."""
        from django.db.models.functions import TruncMonth

        qs = AttendanceRecord.objects.all()
        if department is not None:
            qs = qs.filter(student__department=department)
        rows = (
            qs.annotate(m=TruncMonth("date"))
            .values("m")
            .annotate(
                total=Count("id"),
                attended=Count("id", filter=Q(status__in=_ATTENDED)),
            )
            .order_by("m")
        )
        trend = [
            {
                "label": r["m"].strftime("%b") if r["m"] else "—",
                "percent": _rate(r["attended"], r["total"]),
            }
            for r in rows
        ]
        return trend[-points:]

    # -- fees ------------------------------------------------------------
    def fee_collection(self):
        """Collected vs target per term ([{term, collected, target}])."""
        rows = (
            FeeInvoice.objects.values("term")
            .annotate(
                target=Sum("amount"),
                collected=Sum("amount", filter=Q(status=FeeInvoice.STATUS_PAID)),
            )
            .order_by("term")
        )
        return [
            {
                "term": r["term"] or "—",
                "collected": r["collected"] or Decimal("0"),
                "target": r["target"] or Decimal("0"),
            }
            for r in rows
        ]

    def fee_totals(self):
        agg = FeeInvoice.objects.aggregate(
            target=Sum("amount"),
            collected=Sum("amount", filter=Q(status=FeeInvoice.STATUS_PAID)),
        )
        return (
            agg["collected"] or Decimal("0"),
            agg["target"] or Decimal("0"),
        )

    # -- placement -------------------------------------------------------
    def placement_summary(self):
        eligible = self.student_count()
        placed = (
            PlacementApplication.objects.filter(
                status=PlacementApplication.STATUS_SELECTED
            )
            .values("student")
            .distinct()
            .count()
        )
        from django.db.models import Max

        ctc_agg = PlacementOpening.objects.aggregate(avg=Avg("ctc"), high=Max("ctc"))
        recruiters = list(
            PlacementOpening.objects.values_list("company", flat=True).distinct()[:5]
        )
        # CTC is stored as absolute rupees; express as LPA (lakh per annum).
        avg_lpa = float(ctc_agg["avg"] or 0) / 100000.0
        high_lpa = float(ctc_agg["high"] or 0) / 100000.0
        return {
            "placed": placed,
            "eligible": eligible,
            "avgCtcLpa": round(avg_lpa, 2),
            "highestCtcLpa": round(high_lpa, 2),
            "topRecruiters": recruiters,
        }

    def placement_opening_count(self) -> int:
        return PlacementOpening.objects.filter(is_active=True).count()

    # -- complaints ------------------------------------------------------
    def complaints(self):
        return Complaint.objects.select_related("user")

    def complaint_counts_by_status(self):
        rows = (
            Complaint.objects.values("status")
            .annotate(count=Count("id"))
            .order_by("status")
        )
        return [{"status": r["status"], "count": r["count"]} for r in rows]


# -- module-level helpers ----------------------------------------------------
def _rate(part, total) -> float:
    if not total:
        return 0.0
    return round((part or 0) * 100.0 / total, 1)


def _pct(value) -> float:
    if value is None:
        return 0.0
    return round(float(value), 1)
