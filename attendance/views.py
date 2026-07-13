"""HTTP layer for the attendance app.

A single :class:`AttendanceViewSet` serves the whole surface:

Student self-scoped reads (data scoped to the caller's ``students.Student``):
- ``GET /attendance/summary``  → ``AttendanceSummary[]`` (per-subject rollup).
- ``GET /attendance/overall``  → ``{ percent }``.
- ``GET /attendance/records?subjectId=`` → ``AttendanceRecord[]``.

Faculty session endpoints (owner-scoped to the faculty's own classes):
- ``POST /attendance``                → save a session (``AttendanceSession``).
- ``GET  /faculty/attendance?classId=`` → ``AttendanceSession[]`` (date desc).

Admin CRUD over raw :class:`AttendanceRecord` rows via the default router routes.

Reads are cached under the ``attendance`` prefix (TTL 300s); writes flow through
the service layer (audit + cache-invalidation).
"""
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response

from core.cache import TTL_ATTENDANCE, cache_get_or_set, cache_key
from core.permissions import Role, resolve_parent_child
from core.viewsets import BaseModelViewSet

from faculty.models import FacultyClass, FacultyProfile
from students.models import Student

from attendance.models import AttendanceRecord, AttendanceSession, AttendanceStatus
from attendance.permissions import ATTENDANCE_RECORD_MATRIX
from attendance.serializers import (
    AttendanceRecordAppSerializer,
    AttendanceRecordSerializer,
    AttendanceSessionAppSerializer,
    AttendanceSummarySerializer,
    SaveSessionSerializer,
)
from attendance.services import AttendanceAnalyticsService, AttendanceSessionService

_STAFF_ROLES = set(Role.STAFF)


class AttendanceViewSet(BaseModelViewSet):
    """Attendance: admin CRUD on records + student self-reads + faculty sessions."""

    queryset = AttendanceRecord.objects.select_related("student", "subject").all()
    serializer_class = AttendanceRecordSerializer
    service_class = AttendanceSessionService  # write path used by save-session
    permission_matrix = ATTENDANCE_RECORD_MATRIX
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ["student", "subject", "status", "date"]
    ordering_fields = ["date", "created_at"]

    # -- helpers ---------------------------------------------------------
    def _own_student_or_404(self):
        """The :class:`students.Student` linked to the requesting user."""
        student = (
            Student.objects.filter(user=self.request.user).first()
        )
        if student is None:
            raise NotFound("No student profile is linked to this account.")
        return student

    def _own_faculty_or_404(self):
        """The :class:`faculty.FacultyProfile` for the requesting user."""
        profile = FacultyProfile.objects.filter(user=self.request.user).first()
        if profile is None:
            raise NotFound("No faculty profile for the current user.")
        return profile

    def _resolve_student_by_user_id(self, user_id):
        """Resolve the :class:`students.Student` for an *accounts* user id.

        Access rule (mobile contract): a student/parent may only read their OWN
        ``user_id``; staff/admin may read any (within college). The domain record
        is looked up by ``user_id`` (not the student PK).
        """
        user = self.request.user
        if getattr(user, "role", None) == Role.PARENT:
            return resolve_parent_child(user, user_id)
        if user.role not in _STAFF_ROLES and str(user.id) != str(user_id):
            raise PermissionDenied("You can only access your own attendance.")
        student = Student.objects.filter(user_id=user_id, is_deleted=False).first()
        if student is None:
            raise NotFound("No student profile for this user.")
        return student

    def _class_for_current_user(self, class_id):
        """Fetch a FacultyClass, enforcing owner-scoping for faculty users."""
        klass = (
            FacultyClass.objects.select_related("faculty", "faculty__user")
            .filter(pk=class_id)
            .first()
        )
        if klass is None:
            raise NotFound("Class not found.")
        if self.request.user.role == Role.FACULTY:
            if klass.faculty.user_id != self.request.user.id:
                raise PermissionDenied("You can only access your own classes.")
        return klass

    # -- student self-scoped reads ---------------------------------------
    @extend_schema(responses={200: AttendanceSummarySerializer(many=True)})
    @action(detail=False, methods=["get"])
    def summary(self, request):
        """``GET /attendance/summary`` — per-subject attended/total/percent."""
        student = self._own_student_or_404()

        def build():
            rows = (
                AttendanceRecord.objects.filter(student=student)
                .values("subject_id", "subject__name")
                .annotate(
                    total=Count("id"),
                    attended=Count(
                        "id",
                        filter=Q(status__in=AttendanceStatus.ATTENDED),
                    ),
                )
                .order_by("subject__code")
            )
            out = []
            for r in rows:
                total = r["total"] or 0
                attended = r["attended"] or 0
                percent = round(attended / total * 100) if total else 0
                out.append(
                    {
                        "subjectId": str(r["subject_id"]),
                        "subjectName": r["subject__name"] or "",
                        "attended": attended,
                        "total": total,
                        "percent": percent,
                    }
                )
            return out

        data = cache_get_or_set(
            cache_key("attendance", "summary", student.pk), TTL_ATTENDANCE, build
        )
        return Response(data)

    @extend_schema(responses={200: {"type": "object", "properties": {"percent": {"type": "integer"}}}})
    @action(detail=False, methods=["get"])
    def overall(self, request):
        """``GET /attendance/overall`` — overall attendance percent."""
        student = self._own_student_or_404()

        def build():
            agg = AttendanceRecord.objects.filter(student=student).aggregate(
                total=Count("id"),
                attended=Count(
                    "id", filter=Q(status__in=AttendanceStatus.ATTENDED)
                ),
            )
            total = agg["total"] or 0
            attended = agg["attended"] or 0
            percent = round(attended / total * 100) if total else 0
            return {"percent": percent}

        data = cache_get_or_set(
            cache_key("attendance", "overall", student.pk), TTL_ATTENDANCE, build
        )
        return Response(data)

    @extend_schema(
        parameters=[OpenApiParameter("subjectId", str, required=False)],
        responses={200: AttendanceRecordAppSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def records(self, request):
        """``GET /attendance/records?subjectId=`` — the caller's records."""
        student = self._own_student_or_404()
        subject_id = request.query_params.get("subjectId") or ""

        def build():
            qs = AttendanceRecord.objects.filter(student=student).select_related(
                "subject"
            )
            if subject_id:
                qs = qs.filter(subject_id=subject_id)
            qs = qs.order_by("-date")
            return [AttendanceRecordAppSerializer(r).data for r in qs]

        data = cache_get_or_set(
            cache_key("attendance", "records", student.pk, subject_id),
            TTL_ATTENDANCE,
            build,
        )
        return Response(data)

    # -- staff/admin analytics -------------------------------------------
    @extend_schema(
        responses={
            200: {
                "type": "object",
                "properties": {
                    "overall_percent": {"type": "integer"},
                    "by_department": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "code": {"type": "string"},
                                "name": {"type": "string"},
                                "percent": {"type": "integer"},
                            },
                        },
                    },
                    "by_program": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "code": {"type": "string"},
                                "name": {"type": "string"},
                                "percent": {"type": "integer"},
                            },
                        },
                    },
                    "by_faculty": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "name": {"type": "string"},
                                "percent": {"type": "integer"},
                            },
                        },
                    },
                },
            }
        }
    )
    @action(detail=False, methods=["get"])
    def analytics(self, request):
        """``GET /attendance/analytics`` — attendance rollups for the admin graph.

        Staff/admin only (RBAC matrix). Returns overall attendance percent plus
        per-department, per-program and per-faculty percentages, aggregated in
        the service layer and cached under ``attendance:analytics`` (TTL 300s).
        """
        data = AttendanceAnalyticsService().analytics()
        return Response(data)

    # -- mobile spec read: GET /attendance/{user_id} ---------------------
    @extend_schema(
        responses={
            200: {
                "type": "object",
                "properties": {
                    "overall_percentage": {"type": "integer"},
                    "subject_wise": {"type": "array", "items": {"type": "object"}},
                    "monthly": {"type": "array", "items": {"type": "object"}},
                },
            }
        }
    )
    def attendance_by_user(self, request, pk=None):
        """``GET /attendance/{user_id}`` — spec-shaped attendance for a student.

        Resolves ``students.Student`` from the accounts ``user_id`` (``pk``) and
        returns ``{ overall_percentage, subject_wise:[{subject, attended, total,
        percentage}], monthly:[{month, percentage}] }`` (snake_case per contract).
        The core renderer wraps this in the success envelope.
        """
        student = self._resolve_student_by_user_id(pk)

        def build():
            base = AttendanceRecord.objects.filter(student=student)
            agg = base.aggregate(
                total=Count("id"),
                attended=Count(
                    "id", filter=Q(status__in=AttendanceStatus.ATTENDED)
                ),
            )
            total = agg["total"] or 0
            attended = agg["attended"] or 0
            overall = round(attended / total * 100) if total else 0

            subject_rows = (
                base.values("subject_id", "subject__name")
                .annotate(
                    total=Count("id"),
                    attended=Count(
                        "id", filter=Q(status__in=AttendanceStatus.ATTENDED)
                    ),
                )
                .order_by("subject__name")
            )
            subject_wise = [
                {
                    "subject": r["subject__name"] or "",
                    "attended": r["attended"] or 0,
                    "total": r["total"] or 0,
                    "percentage": round(r["attended"] / r["total"] * 100)
                    if r["total"]
                    else 0,
                }
                for r in subject_rows
            ]

            month_rows = (
                base.annotate(m=TruncMonth("date"))
                .values("m")
                .annotate(
                    total=Count("id"),
                    attended=Count(
                        "id", filter=Q(status__in=AttendanceStatus.ATTENDED)
                    ),
                )
                .order_by("m")
            )
            monthly = [
                {
                    "month": r["m"].strftime("%Y-%m") if r["m"] else "",
                    "percentage": round(r["attended"] / r["total"] * 100)
                    if r["total"]
                    else 0,
                }
                for r in month_rows
            ]

            return {
                "overall_percentage": overall,
                "subject_wise": subject_wise,
                "monthly": monthly,
            }

        data = cache_get_or_set(
            cache_key("attendance", "byuser", student.pk), TTL_ATTENDANCE, build
        )
        return Response(data)

    # -- faculty session endpoints ---------------------------------------
    @extend_schema(
        request=SaveSessionSerializer,
        responses={201: AttendanceSessionAppSerializer},
    )
    def create_session(self, request):
        """``POST /attendance`` — save (upsert) a faculty attendance session.

        Bound explicitly to ``POST /attendance`` via ``as_view`` in ``urls.py``
        (the collection root also serves admin ``GET``/``POST`` on records, so
        this is a dedicated action). The action name drives its RBAC entry;
        ``RoleModelPermission`` reads ``view.action`` which ``as_view`` sets from
        the action-map key.
        """
        serializer = SaveSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        klass = self._class_for_current_user(payload["classId"])

        # Map the app's {studentId,status} entries onto AttendanceEntry rows.
        # studentId is treated as a students.Student UUID (student_ref); roll_no
        # is looked up from the class roster when available.
        roster = {
            str(e.student_ref): e.roll_no
            for e in klass.roster_entries.all()
            if e.student_ref is not None
        }
        entries = []
        for item in payload["entries"]:
            sid = item["studentId"]
            entries.append(
                {
                    "student_ref": sid,
                    "roll_no": roster.get(str(sid), ""),
                    "status": item["status"],
                }
            )

        service = self.get_service()
        session = service.save_session(
            faculty_class=klass, date=payload["date"], entries=entries
        )
        session = (
            AttendanceSession.objects.prefetch_related("entries")
            .get(pk=session.pk)
        )
        return Response(AttendanceSessionAppSerializer(session).data, status=201)

    @extend_schema(
        parameters=[OpenApiParameter("classId", str, required=False)],
        responses={200: AttendanceSessionAppSerializer(many=True)},
    )
    def faculty_sessions(self, request):
        """``GET /faculty/attendance?classId=`` — sessions (date desc).

        Faculty see only their own classes' sessions; a ``classId`` filter is
        owner-checked. Admins/super-admins see all.
        """
        class_id = request.query_params.get("classId") or ""

        def build():
            qs = (
                AttendanceSession.objects.select_related("faculty_class")
                .prefetch_related("entries")
            )
            if class_id:
                klass = self._class_for_current_user(class_id)
                qs = qs.filter(faculty_class=klass)
            elif request.user.role == Role.FACULTY:
                profile = self._own_faculty_or_404()
                qs = qs.filter(faculty_class__faculty=profile)
            qs = qs.order_by("-date")
            return [AttendanceSessionAppSerializer(s).data for s in qs]

        # classId-scoped result is cacheable; the un-scoped faculty view depends
        # on the caller so key it by class or faculty user.
        scope = class_id or f"fac-{request.user.id}"
        data = cache_get_or_set(
            cache_key("attendance", "sessions", scope), TTL_ATTENDANCE, build
        )
        return Response(data)
