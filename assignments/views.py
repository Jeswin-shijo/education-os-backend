"""HTTP layer for the assignments app.

A single :class:`AssignmentViewSet` serves both the student-facing reads and the
faculty create/list surface:

- ``GET /assignments`` — list (``?status=`` filter) in the student-facing
  ``types.ts`` ``Assignment`` shape; per-student status/grade come from the
  requesting student's submissions.
- ``GET /assignments/{id}`` — one assignment (student-facing shape).
- ``POST /assignments`` — faculty/admin create (CRUD shape).
- ``POST /assignments/{id}/submit`` — student turn-in (``{ fileName }``).
- ``GET /faculty/assignments`` — faculty-created list (``FacultyAssignment[]``,
  ``?classId=`` filter, submission counts).

Writes flow through the service layer (audit + cache-invalidation) via
:class:`core.viewsets.BaseModelViewSet`.
"""
from django.db.models import Count, Q
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from core.permissions import Role
from core.viewsets import BaseModelViewSet

from assignments.models import Assignment, Submission
from assignments.permissions import ASSIGNMENT_MATRIX
from assignments.serializers import (
    AssignmentSerializer,
    FacultyAssignmentSerializer,
    StudentAssignmentSerializer,
    SubmitInputSerializer,
)
from assignments.services import AssignmentService, SubmissionService

# Local import guard: the student lookup needs the Student model.
from students.models import Student


class AssignmentViewSet(BaseModelViewSet):
    """Assignments: student-facing reads + faculty create/list."""

    queryset = Assignment.objects.select_related(
        "subject", "faculty_class", "faculty_class__subject"
    ).all()
    serializer_class = AssignmentSerializer
    service_class = AssignmentService
    permission_matrix = ASSIGNMENT_MATRIX
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["status", "subject", "faculty_class"]
    search_fields = ["title", "description", "subject__code", "subject__name"]
    ordering_fields = ["due_date", "created_at", "title"]

    # -- helpers ---------------------------------------------------------
    def _current_student(self):
        """Return the Student row for the current user (or ``None``)."""
        return (
            Student.objects.filter(user=self.request.user)
            .order_by("created_at")
            .first()
        )

    def _submissions_map(self, student, assignments):
        """Map ``{assignment_id: Submission}`` for a student across assignments."""
        if student is None:
            return {}
        subs = Submission.objects.filter(
            student=student, assignment__in=[a.id for a in assignments]
        )
        return {s.assignment_id: s for s in subs}

    # -- student-facing list / retrieve ----------------------------------
    @extend_schema(responses={200: StudentAssignmentSerializer(many=True)})
    def list(self, request, *args, **kwargs):
        """``GET /assignments`` — student-facing list with ``?status=`` filter."""
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        rows = page if page is not None else list(queryset)

        student = self._current_student()
        context = {"submissions": self._submissions_map(student, rows)}
        data = StudentAssignmentSerializer(rows, many=True, context=context).data

        if page is not None:
            return self.get_paginated_response(data)
        return Response(data)

    @extend_schema(responses={200: StudentAssignmentSerializer})
    def retrieve(self, request, *args, **kwargs):
        """``GET /assignments/{id}`` — one assignment (student-facing shape)."""
        instance = self.get_object()
        student = self._current_student()
        context = {"submissions": self._submissions_map(student, [instance])}
        return Response(
            StudentAssignmentSerializer(instance, context=context).data
        )

    # -- student submit --------------------------------------------------
    @extend_schema(
        request=SubmitInputSerializer,
        responses={200: StudentAssignmentSerializer},
    )
    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        """``POST /assignments/{id}/submit`` — student turn-in (``{ fileName }``)."""
        assignment = self.get_object()

        student = self._current_student()
        if student is None:
            raise NotFound("No student profile for the current user.")

        serializer = SubmitInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        file_name = serializer.validated_data["fileName"]

        service = SubmissionService(actor=request.user, ip=self._client_ip())
        service.submit(assignment, student, file_name)

        # Return the assignment in the student-facing shape, reflecting the
        # fresh submission.
        assignment.refresh_from_db()
        context = {"submissions": self._submissions_map(student, [assignment])}
        return Response(
            StudentAssignmentSerializer(assignment, context=context).data
        )

    # -- faculty-created list --------------------------------------------
    @extend_schema(responses={200: FacultyAssignmentSerializer(many=True)})
    @action(detail=False, methods=["get"])
    def faculty_assignments(self, request):
        """``GET /faculty/assignments`` — faculty-created list (``?classId=``)."""
        qs = (
            Assignment.objects.select_related("subject", "faculty_class")
            .annotate(
                submission_count=Count(
                    "submissions", filter=Q(submissions__is_deleted=False)
                )
            )
            .order_by("-created_at")
        )

        # Faculty see only their own classes' assignments; admins see all.
        if request.user.role == Role.FACULTY:
            qs = qs.filter(faculty_class__faculty__user=request.user)

        class_id = request.query_params.get("classId")
        if class_id:
            try:
                qs = qs.filter(faculty_class_id=class_id)
                # Force evaluation catch for malformed UUIDs happens lazily; a
                # bad value simply yields an empty queryset below.
            except (ValueError, ValidationError):
                qs = qs.none()

        page = self.paginate_queryset(qs)
        rows = page if page is not None else list(qs)
        data = FacultyAssignmentSerializer(rows, many=True).data
        if page is not None:
            return self.get_paginated_response(data)
        return Response(data)
