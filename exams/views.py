"""HTTP layer for the exams app.

Three viewsets serve the mobile contract (all mounted under ``/api/v1/``):

* :class:`ExamViewSet` — ``GET /exams``, ``GET /exams/upcoming`` (+ admin CRUD).
* :class:`ExamResultViewSet` — ``GET /results``, ``GET /results/gpa`` (+ faculty
  CRUD). Student/parent reads are self/child scoped.
* :class:`MarksSheetViewSet` — faculty marks entry: ``POST /marks``,
  ``GET /faculty/marks`` (+ staff CRUD). Owner-scoped to the faculty's classes.

Self-scoped mobile reads are cached under the ``exams`` prefix (TTL 3600s for the
timetable-like schedule; the GPA/results reads use it too); writes flow through
the service layer (audit + cache-invalidation) via
:class:`core.viewsets.BaseModelViewSet`.
"""
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from core.cache import TTL_TIMETABLE, cache_get_or_set, cache_key
from core.permissions import Role
from core.viewsets import BaseModelViewSet

from academics.models import Subject
from faculty.models import FacultyClass, FacultyProfile
from students.models import Student

from exams.models import Exam, ExamResult, MarksSheet
from exams.permissions import (
    EXAM_MATRIX,
    EXAM_RESULT_MATRIX,
    MARKS_SHEET_MATRIX,
)
from exams.serializers import (
    ExamAppSerializer,
    ExamResultAppSerializer,
    ExamResultSerializer,
    ExamSerializer,
    MarksSheetAppSerializer,
    SaveSheetInputSerializer,
)
from exams.services import ExamResultService, ExamService, MarksSheetService

# Exam schedule + results are cached under the ``exams`` prefix.
TTL_EXAMS = TTL_TIMETABLE

_STAFF_ROLES = set(Role.STAFF)


def _current_student(request):
    """Return the Student linked to the requesting user, or ``None``.

    Non-staff users (student/parent) are scoped to this record. Parent-child
    resolution will refine to the linked child once the guardians module lands;
    for now a parent resolves via their own linked student profile if any.
    """
    return (
        Student.objects.select_related("program", "department", "semester", "section")
        .filter(user=request.user)
        .first()
    )


class ExamViewSet(BaseModelViewSet):
    """Exams: ``GET /exams``, ``GET /exams/upcoming`` + admin CRUD."""

    queryset = Exam.objects.select_related("subject").all()
    serializer_class = ExamSerializer
    service_class = ExamService
    permission_matrix = EXAM_MATRIX
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["subject", "type", "date"]
    search_fields = ["name", "subject__code", "subject__name", "room"]
    ordering_fields = ["date", "time", "created_at"]

    def _student_subject_ids(self):
        """Subject ids relevant to a self-scoped student (their section's subjects).

        Falls back to all subjects when the student has no section wired up, so a
        freshly-seeded account still sees the exam schedule.
        """
        student = _current_student(self.request)
        if student is None or student.section_id is None:
            return None
        ids = list(
            Subject.objects.filter(
                sessions__section_id=student.section_id
            ).values_list("id", flat=True).distinct()
        )
        return ids

    def get_queryset(self):
        qs = super().get_queryset()
        # Students/parents see only their section's subject exams (best-effort);
        # staff see everything.
        if self.request.user.role not in _STAFF_ROLES:
            subject_ids = self._student_subject_ids()
            if subject_ids is not None:
                qs = qs.filter(subject_id__in=subject_ids)
        return qs

    @extend_schema(responses={200: ExamAppSerializer(many=True)})
    def list(self, request, *args, **kwargs):
        """``GET /exams`` — app-shaped exam list (paginated)."""
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        if page is not None:
            data = ExamAppSerializer(page, many=True).data
            return self.get_paginated_response(data)
        return Response(ExamAppSerializer(qs, many=True).data)

    @extend_schema(responses={200: ExamAppSerializer(many=True)})
    @action(detail=False, methods=["get"])
    def upcoming(self, request):
        """``GET /exams/upcoming`` — exams dated today or later (app-shaped)."""
        today = timezone.localdate()
        qs = self.get_queryset().filter(date__gte=today).order_by("date", "time")
        return Response(ExamAppSerializer(qs, many=True).data)


class ExamResultViewSet(BaseModelViewSet):
    """Exam results: ``GET /results``, ``GET /results/gpa`` + faculty CRUD."""

    queryset = ExamResult.objects.select_related(
        "student", "subject", "exam_ref"
    ).all()
    serializer_class = ExamResultSerializer
    service_class = ExamResultService
    permission_matrix = EXAM_RESULT_MATRIX
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["student", "subject", "exam"]
    search_fields = ["exam", "subject__code", "subject__name", "grade"]
    ordering_fields = ["created_at", "marks", "grade_point"]

    def _self_or_404(self):
        student = _current_student(self.request)
        if student is None:
            raise NotFound("No student profile is linked to this account.")
        return student

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.role not in _STAFF_ROLES:
            # Student/parent only ever see their own (child) results.
            student = _current_student(self.request)
            qs = qs.filter(student=student) if student else qs.none()
        return qs

    @extend_schema(responses={200: ExamResultAppSerializer(many=True)})
    def list(self, request, *args, **kwargs):
        """``GET /results`` — app-shaped result list (paginated)."""
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        if page is not None:
            data = ExamResultAppSerializer(page, many=True).data
            return self.get_paginated_response(data)
        return Response(ExamResultAppSerializer(qs, many=True).data)

    @extend_schema(responses={200: {"type": "object", "properties": {"gpa": {"type": "number"}}}})
    @action(detail=False, methods=["get"])
    def gpa(self, request):
        """``GET /results/gpa`` — credit-weighted GPA ``{gpa}`` for the scoped student."""
        if request.user.role not in _STAFF_ROLES:
            student = self._self_or_404()
            student_id = student.id
        else:
            # Staff must pass ?student=<id> to scope the GPA.
            student_id = request.query_params.get("student")
            if not student_id:
                raise ValidationError({"student": "This query param is required for staff."})
        service = ExamResultService(actor=request.user)

        def build():
            return {"gpa": service.gpa_for_student(student_id)}

        data = cache_get_or_set(
            cache_key("exams", "gpa", student_id), TTL_EXAMS, build
        )
        return Response(data)


class MarksSheetViewSet(BaseModelViewSet):
    """Faculty marks entry: ``POST /marks``, ``GET /faculty/marks`` + staff CRUD."""

    queryset = (
        MarksSheet.objects.select_related(
            "faculty_class",
            "faculty_class__subject",
            "faculty_class__faculty",
            "faculty_class__faculty__user",
        )
        .prefetch_related("entries__student")
        .all()
    )
    serializer_class = MarksSheetAppSerializer
    service_class = MarksSheetService
    permission_matrix = MARKS_SHEET_MATRIX
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ["faculty_class", "exam"]
    ordering_fields = ["entered_on", "created_at"]

    # -- helpers ---------------------------------------------------------
    def _own_profile_or_404(self):
        profile = FacultyProfile.objects.filter(user=self.request.user).first()
        if profile is None:
            raise NotFound("No faculty profile for the current user.")
        return profile

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
                raise PermissionDenied("You can only enter marks for your own classes.")
        return klass

    @extend_schema(
        request=SaveSheetInputSerializer,
        responses={200: MarksSheetAppSerializer},
    )
    @action(detail=False, methods=["post"], url_path="marks")
    def save_marks(self, request):
        """``POST /marks`` — upsert a marks sheet for one of the faculty's classes."""
        serializer = SaveSheetInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        klass = self._class_for_current_user(data["classId"])

        student_ids = [e["studentId"] for e in data["entries"]]
        students = {
            str(s.id): s
            for s in Student.objects.filter(id__in=student_ids)
        }
        missing = [sid for sid in student_ids if sid not in students]
        if missing:
            raise ValidationError({"entries": f"Unknown student ids: {missing}"})

        entries = [
            {"student": students[e["studentId"]], "marks": e["marks"]}
            for e in data["entries"]
        ]

        service = MarksSheetService(actor=request.user, ip=self._client_ip())
        sheet = service.save_sheet(
            faculty_class=klass,
            exam=data["exam"],
            max_marks=data["maxMarks"],
            entries=entries,
        )
        sheet = (
            MarksSheet.objects.prefetch_related("entries__student")
            .get(pk=sheet.pk)
        )
        return Response(MarksSheetAppSerializer(sheet).data)

    @extend_schema(responses={200: MarksSheetAppSerializer(many=True)})
    @action(detail=False, methods=["get"], url_path="faculty/marks")
    def faculty_marks(self, request):
        """``GET /faculty/marks`` — the faculty's marks sheets (optionally ?classId=)."""
        class_id = request.query_params.get("classId")
        qs = self.get_queryset()

        if request.user.role == Role.FACULTY:
            profile = self._own_profile_or_404()
            qs = qs.filter(faculty_class__faculty=profile)
        if class_id:
            qs = qs.filter(faculty_class_id=class_id)
        qs = qs.order_by("-entered_on")
        return Response(MarksSheetAppSerializer(qs, many=True).data)
