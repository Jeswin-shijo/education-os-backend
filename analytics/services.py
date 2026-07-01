"""Aggregation services for the HOD + Principal analytics surfaces.

These services are **read-only**: they compose the cheap rollups exposed by
:class:`analytics.repositories.AnalyticsRepository` into the exact response
shapes the mobile ``hodService`` / ``principalService`` expect, and cache each
result under the ``analytics`` prefix (TTL 300s) via
:func:`core.cache.cache_get_or_set`.

Nothing here writes to the database or emits an ``AuditLog`` — analytics never
mutates state, so it does not subclass :class:`core.services.BaseService`.
"""
from __future__ import annotations

from decimal import Decimal

from core.cache import TTL_ANALYTICS, cache_get_or_set, cache_key

from analytics.repositories import AnalyticsRepository

# Grade bands (marks %) mirrored from the app's HOD/Principal analytics.
# Each band is a half-open ``[lo, hi)`` range on marks %, except the top band
# which is closed at 100. Ordered high→low; the first match wins.
_BANDS = [
    ("90-100", 90.0, 100.01),
    ("80-89", 80.0, 90.0),
    ("70-79", 70.0, 80.0),
    ("60-69", 60.0, 70.0),
    ("<60", 0.0, 60.0),
]
_LOW_ATTENDANCE = 75.0  # threshold for "at risk" / "low attendance"
_PASS_MARK = 40.0  # marks % counted as a pass


def _grade_bands(marks_rows) -> list[dict]:
    """Bucket per-student marks% into the fixed grade bands."""
    counts = {band: 0 for band, _, _ in _BANDS}
    for row in marks_rows:
        p = row["percent"]
        for band, lo, hi in _BANDS:
            if lo <= p < hi:
                counts[band] += 1
                break
    return [{"band": band, "count": counts[band]} for band, _, _ in _BANDS]


def _dec(value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return round(float(value), 2)
    return round(float(value), 2)


class HodAnalyticsService:
    """Department-scoped aggregations for the HOD role."""

    def __init__(self, user):
        self.user = user
        self.repo = AnalyticsRepository()
        self.department = self.repo.department_for_user(user)

    # -- cache scope -----------------------------------------------------
    @property
    def _scope(self) -> str:
        return str(self.department.pk) if self.department else "none"

    def _dept_label(self) -> str:
        return self.department.name if self.department else "Department"

    # -- faculty performance --------------------------------------------
    def faculty_performance(self) -> list[dict]:
        return cache_get_or_set(
            cache_key("analytics", "hod", "faculty", self._scope),
            TTL_ANALYTICS,
            self._build_faculty_performance,
        )

    def _build_faculty_performance(self) -> list[dict]:
        dept = self.department
        classes = list(self.repo.faculty_classes(dept))
        # Pre-aggregate marks% per faculty from their classes' marks sheets.
        from django.db.models import Avg, Count, F, Q
        from exams.models import MarkEntry
        from attendance.models import AttendanceSession

        out = []
        for profile in self.repo.faculty_profiles(dept):
            fclasses = [c for c in classes if c.faculty_id == profile.id]
            class_ids = [c.id for c in fclasses]
            student_count = sum(c.student_count for c in fclasses)
            subjects = sorted({c.subject.code for c in fclasses})

            marks_agg = MarkEntry.objects.filter(
                sheet__faculty_class_id__in=class_ids,
                sheet__max_marks__gt=0,
            ).aggregate(
                pct=Avg(F("marks") * Decimal("100") / F("sheet__max_marks"))
            )
            sessions = AttendanceSession.objects.filter(
                faculty_class_id__in=class_ids
            ).count()

            out.append(
                {
                    "facultyId": str(profile.id),
                    "name": profile.user.full_name,
                    "avatarColor": profile.user.avatar_color,
                    "designation": profile.designation or "Faculty",
                    "subjects": subjects,
                    "classCount": len(fclasses),
                    "studentCount": student_count,
                    "avgMarksPercent": _dec(marks_agg["pct"]),
                    "sessionsMarked": sessions,
                }
            )
        out.sort(key=lambda f: f["avgMarksPercent"], reverse=True)
        return out

    def faculty_detail(self, faculty_id) -> dict | None:
        for f in self.faculty_performance():
            if f["facultyId"] == str(faculty_id):
                return f
        return None

    # -- student performance --------------------------------------------
    def student_performance(self) -> dict:
        return cache_get_or_set(
            cache_key("analytics", "hod", "students", self._scope),
            TTL_ANALYTICS,
            self._build_student_performance,
        )

    def _build_student_performance(self) -> dict:
        marks = self.repo.student_marks_percent(self.department)
        top = marks[:5]
        at_risk = sorted(marks, key=lambda s: s["percent"])[:5]
        strip = lambda s: {
            "name": s["name"],
            "rollNo": s["rollNo"],
            "percent": s["percent"],
        }
        return {
            "gradeBands": _grade_bands(marks),
            "topPerformers": [strip(s) for s in top],
            "atRisk": [strip(s) for s in at_risk],
        }

    # -- attendance analytics -------------------------------------------
    def attendance_analytics(self) -> dict:
        return cache_get_or_set(
            cache_key("analytics", "hod", "attendance", self._scope),
            TTL_ANALYTICS,
            self._build_attendance_analytics,
        )

    def _build_attendance_analytics(self) -> dict:
        dept = self.department
        by_student = self.repo.attendance_percent_by_student(dept)
        low = [s for s in by_student if s["percent"] < _LOW_ATTENDANCE]
        strip = lambda s: {
            "name": s["name"],
            "rollNo": s["rollNo"],
            "percent": s["percent"],
        }
        return {
            "overallPercent": self.repo.attendance_percent(dept),
            "trend": self.repo.attendance_monthly_trend(dept),
            "bySubject": self.repo.attendance_percent_by_subject(dept),
            "lowStudents": [strip(s) for s in low],
        }

    # -- profile ---------------------------------------------------------
    def profile(self) -> dict:
        dept = self.department
        return {
            "hod": {
                "id": str(self.user.id),
                "name": self.user.full_name,
                "email": self.user.email,
                "role": self.user.role,
                "avatarColor": self.user.avatar_color,
                "phone": self.user.phone,
            },
            "department": self._dept_label(),
            "facultyCount": self.repo.faculty_count(dept),
            "studentCount": self.repo.student_count(dept),
        }

    # -- dashboard rollup -----------------------------------------------
    def dashboard(self) -> dict:
        return cache_get_or_set(
            cache_key("analytics", "hod", "dashboard", self._scope),
            TTL_ANALYTICS,
            self._build_dashboard,
        )

    def _build_dashboard(self) -> dict:
        dept = self.department
        faculty = self._build_faculty_performance()
        marks = self.repo.student_marks_percent(dept)
        avg_marks = (
            round(sum(m["percent"] for m in marks) / len(marks), 1) if marks else 0.0
        )
        pass_count = sum(1 for m in marks if m["percent"] >= _PASS_MARK)
        pass_rate = round(pass_count * 100.0 / len(marks), 1) if marks else 0.0
        by_student_att = self.repo.attendance_percent_by_student(dept)
        low_att = sum(1 for s in by_student_att if s["percent"] < _LOW_ATTENDANCE)
        return {
            "department": self._dept_label(),
            "facultyCount": self.repo.faculty_count(dept),
            "studentCount": self.repo.student_count(dept),
            "classCount": self.repo.class_count(dept),
            "avgAttendancePercent": self.repo.attendance_percent(dept),
            "avgMarksPercent": avg_marks,
            "passRatePercent": pass_rate,
            "lowAttendanceCount": low_att,
            "topFaculty": faculty[0] if faculty else None,
            "attendanceTrend": self.repo.attendance_monthly_trend(dept),
        }


class PrincipalAnalyticsService:
    """Institution-wide aggregations for the Principal role (read-only)."""

    INSTITUTION = "AI Campus OS"

    def __init__(self, user):
        self.user = user
        self.repo = AnalyticsRepository()

    # -- profile ---------------------------------------------------------
    def profile(self) -> dict:
        return {
            "principal": {
                "id": str(self.user.id),
                "name": self.user.full_name,
                "email": self.user.email,
                "role": self.user.role,
                "avatarColor": self.user.avatar_color,
                "phone": self.user.phone,
            },
            "institution": self.INSTITUTION,
        }

    def _department_cards(self) -> list[dict]:
        return [
            {
                "id": str(d.id),
                "code": d.code,
                "name": d.name,
                "studentCount": self.repo.student_count(d),
                "facultyCount": self.repo.faculty_count(d),
                "avgAttendance": self.repo.attendance_percent(d),
                "avgCgpa": _dec(self.repo.avg_cgpa(d)),
                "passRate": self._dept_pass_rate(d),
                "color": "#13327F",
            }
            for d in self.repo.departments()
        ]

    def _dept_pass_rate(self, department) -> float:
        marks = self.repo.student_marks_percent(department)
        if not marks:
            return 0.0
        passed = sum(1 for m in marks if m["percent"] >= _PASS_MARK)
        return round(passed * 100.0 / len(marks), 1)

    # -- dashboard -------------------------------------------------------
    def dashboard(self) -> dict:
        return cache_get_or_set(
            cache_key("analytics", "principal", "dashboard"),
            TTL_ANALYTICS,
            self._build_dashboard,
        )

    def _build_dashboard(self) -> dict:
        marks = self.repo.student_marks_percent()
        avg_marks_pass = (
            round(sum(1 for m in marks if m["percent"] >= _PASS_MARK) * 100.0 / len(marks), 1)
            if marks
            else 0.0
        )
        collected, target = self.repo.fee_totals()
        fee_pct = (
            round(float(collected) * 100.0 / float(target), 1) if target else 0.0
        )
        placement = self.repo.placement_summary()
        placement_rate = (
            round(placement["placed"] * 100.0 / placement["eligible"], 1)
            if placement["eligible"]
            else 0.0
        )
        cards = self._department_cards()
        return {
            "institution": self.INSTITUTION,
            "totalStudents": self.repo.student_count(),
            "totalFaculty": self.repo.faculty_count(),
            "departmentCount": len(cards),
            "avgAttendance": self.repo.attendance_percent(),
            "avgCgpa": _dec(self.repo.avg_cgpa()),
            "passRate": avg_marks_pass,
            "feeCollectedPercent": fee_pct,
            "placementRatePercent": placement_rate,
            "departments": cards,
            "admissionsTrend": self._admissions_trend(),
        }

    def _admissions_trend(self) -> list[dict]:
        """Admissions by enrolment year, derived from the students table."""
        from django.db.models import Count
        from students.models import Student

        rows = (
            Student.objects.exclude(created_at__isnull=True)
            .values_list("created_at", flat=True)
        )
        # Cheap in-Python bucket by year (student volumes are modest).
        buckets: dict[str, int] = {}
        for dt in rows:
            year = str(dt.year)
            buckets[year] = buckets.get(year, 0) + 1
        return [
            {"year": y, "count": buckets[y]} for y in sorted(buckets)
        ]

    # -- student analytics ----------------------------------------------
    def student_analytics(self) -> dict:
        return cache_get_or_set(
            cache_key("analytics", "principal", "students"),
            TTL_ANALYTICS,
            self._build_student_analytics,
        )

    def _build_student_analytics(self) -> dict:
        marks = self.repo.student_marks_percent()
        at_risk = sum(1 for m in marks if m["percent"] < _PASS_MARK)
        return {
            "totalStudents": self.repo.student_count(),
            "byDepartment": self.repo.students_by_department(),
            "gradeBands": _grade_bands(marks),
            "atRiskCount": at_risk,
        }

    # -- faculty analytics ----------------------------------------------
    def faculty_analytics(self) -> dict:
        return cache_get_or_set(
            cache_key("analytics", "principal", "faculty"),
            TTL_ANALYTICS,
            self._build_faculty_analytics,
        )

    def _build_faculty_analytics(self) -> dict:
        # Reuse the HOD faculty-performance builder across all departments.
        from django.db.models import Avg, Count, F
        from exams.models import MarkEntry
        from attendance.models import AttendanceSession

        classes = list(self.repo.faculty_classes())
        performers = []
        for profile in self.repo.faculty_profiles():
            fclasses = [c for c in classes if c.faculty_id == profile.id]
            class_ids = [c.id for c in fclasses]
            marks_agg = MarkEntry.objects.filter(
                sheet__faculty_class_id__in=class_ids,
                sheet__max_marks__gt=0,
            ).aggregate(pct=Avg(F("marks") * Decimal("100") / F("sheet__max_marks")))
            sessions = AttendanceSession.objects.filter(
                faculty_class_id__in=class_ids
            ).count()
            performers.append(
                {
                    "facultyId": str(profile.id),
                    "name": profile.user.full_name,
                    "avatarColor": profile.user.avatar_color,
                    "designation": profile.designation or "Faculty",
                    "subjects": sorted({c.subject.code for c in fclasses}),
                    "classCount": len(fclasses),
                    "studentCount": sum(c.student_count for c in fclasses),
                    "avgMarksPercent": _dec(marks_agg["pct"]),
                    "sessionsMarked": sessions,
                }
            )
        performers.sort(key=lambda f: f["avgMarksPercent"], reverse=True)
        return {
            "totalFaculty": self.repo.faculty_count(),
            "byDepartment": self.repo.faculty_by_department(),
            "topPerformers": performers[:5],
        }

    # -- fee analytics ---------------------------------------------------
    def fee_analytics(self) -> dict:
        return cache_get_or_set(
            cache_key("analytics", "principal", "fees"),
            TTL_ANALYTICS,
            self._build_fee_analytics,
        )

    def _build_fee_analytics(self) -> dict:
        collection = self.repo.fee_collection()
        collected, target = self.repo.fee_totals()
        pct = round(float(collected) * 100.0 / float(target), 1) if target else 0.0
        return {
            "collection": [
                {
                    "term": c["term"],
                    "collected": _dec(c["collected"]),
                    "target": _dec(c["target"]),
                }
                for c in collection
            ],
            "totalCollected": _dec(collected),
            "totalTarget": _dec(target),
            "collectionPercent": pct,
        }

    # -- placement analytics --------------------------------------------
    def placement_analytics(self) -> dict:
        return cache_get_or_set(
            cache_key("analytics", "principal", "placements"),
            TTL_ANALYTICS,
            self._build_placement_analytics,
        )

    def _build_placement_analytics(self) -> dict:
        summary = self.repo.placement_summary()
        rate = (
            round(summary["placed"] * 100.0 / summary["eligible"], 1)
            if summary["eligible"]
            else 0.0
        )
        return {
            "summary": summary,
            "ratePercent": rate,
            "openings": self.repo.placement_opening_count(),
        }

    # -- complaint monitoring -------------------------------------------
    def complaint_monitoring(self) -> dict:
        return cache_get_or_set(
            cache_key("analytics", "principal", "complaints"),
            TTL_ANALYTICS,
            self._build_complaint_monitoring,
        )

    def _build_complaint_monitoring(self) -> dict:
        recent = self.repo.complaints().order_by("-created_on")[:10]
        return {
            "total": self.repo.complaints().count(),
            "byStatus": self.repo.complaint_counts_by_status(),
            "recent": [
                {
                    "id": str(c.id),
                    "category": c.category,
                    "subject": c.subject,
                    "description": c.description,
                    "status": c.status,
                    "createdOn": c.created_on.isoformat() if c.created_on else None,
                }
                for c in recent
            ],
        }

    # -- AI-style insight cards -----------------------------------------
    def ai_insights(self) -> list[dict]:
        return cache_get_or_set(
            cache_key("analytics", "principal", "insights"),
            TTL_ANALYTICS,
            self._build_ai_insights,
        )

    def _build_ai_insights(self) -> list[dict]:
        """Data-aware insight cards computed from the live rollups.

        These are heuristic ("AI-style") observations derived from the same
        aggregates the dashboards use — no external LLM call. Tones drive the
        card colour in the app (info/success/warning/danger).
        """
        cards: list[dict] = []
        att = self.repo.attendance_percent()
        if att:
            tone = "success" if att >= 85 else "warning" if att >= 75 else "danger"
            cards.append(
                {
                    "id": "insight-attendance",
                    "title": "Institution attendance",
                    "body": (
                        f"Overall attendance is {att}%."
                        + (
                            " Healthy — above the 85% benchmark."
                            if att >= 85
                            else " Below the 85% benchmark; nudge low-attendance cohorts."
                        )
                    ),
                    "tone": tone,
                    "metric": f"{att}%",
                }
            )

        collected, target = self.repo.fee_totals()
        if target:
            pct = round(float(collected) * 100.0 / float(target), 1)
            tone = "success" if pct >= 80 else "warning" if pct >= 50 else "danger"
            cards.append(
                {
                    "id": "insight-fees",
                    "title": "Fee collection",
                    "body": f"{pct}% of billed fees collected this cycle.",
                    "tone": tone,
                    "metric": f"{pct}%",
                }
            )

        placement = self.repo.placement_summary()
        if placement["eligible"]:
            rate = round(placement["placed"] * 100.0 / placement["eligible"], 1)
            tone = "success" if rate >= 70 else "info"
            cards.append(
                {
                    "id": "insight-placement",
                    "title": "Placements",
                    "body": (
                        f"{placement['placed']} of {placement['eligible']} students placed "
                        f"(avg {placement['avgCtcLpa']} LPA)."
                    ),
                    "tone": tone,
                    "metric": f"{rate}%",
                }
            )

        marks = self.repo.student_marks_percent()
        at_risk = sum(1 for m in marks if m["percent"] < _PASS_MARK)
        if at_risk:
            cards.append(
                {
                    "id": "insight-at-risk",
                    "title": "Academically at-risk students",
                    "body": (
                        f"{at_risk} students are below the {int(_PASS_MARK)}% pass mark; "
                        "consider targeted mentoring."
                    ),
                    "tone": "warning" if at_risk < 20 else "danger",
                    "metric": str(at_risk),
                }
            )

        complaints = self.repo.complaints()
        open_count = complaints.exclude(status="resolved").count()
        if open_count:
            cards.append(
                {
                    "id": "insight-complaints",
                    "title": "Open complaints",
                    "body": f"{open_count} complaints are unresolved and need attention.",
                    "tone": "info" if open_count < 5 else "warning",
                    "metric": str(open_count),
                }
            )

        if not cards:
            cards.append(
                {
                    "id": "insight-empty",
                    "title": "All clear",
                    "body": "No standout signals in the current data window.",
                    "tone": "info",
                }
            )
        return cards
