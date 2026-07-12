"""HTTP layer for the students app.

``StudentViewSet`` gives admins/staff the roster (list with ``?search=`` over
name/roll and ``?department=&semester=&section=&status=`` filters) and admins
full CRUD, all flowing through :class:`StudentService` (audit + cache-invalidate).

The mobile app's ``GET /students/me`` + ``PUT /students/me`` are served by the
``me`` custom action, returning the app-shaped ``Student`` for the requesting
user's linked profile; the write updates only the student-editable profile
fields. Child collections (addresses/guardians/medical/documents) get thin
staff/admin viewsets.
"""
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.cache import invalidate_prefix
from core.permissions import Role
from core.viewsets import BaseModelViewSet

from students.models import (
    Guardian,
    Medical,
    Student,
    StudentAddress,
    StudentDocument,
)
from students.permissions import CHILD_MATRIX, STUDENT_MATRIX
from students.serializers import (
    GuardianSerializer,
    MedicalSerializer,
    StudentAddressSerializer,
    StudentAppSerializer,
    StudentDocumentSerializer,
    StudentProfileSpecSerializer,
    StudentSerializer,
)
from students.services import (
    DASHBOARD_PREFIX,
    GuardianService,
    MedicalService,
    STUDENTS_PREFIX,
    StudentAddressService,
    StudentDocumentService,
    StudentService,
)

_STAFF_ROLES = set(Role.STAFF)


def _truthy(value) -> bool:
    return str(value).lower() in ("1", "true", "yes", "on")


class StudentViewSet(BaseModelViewSet):
    queryset = Student.objects.select_related(
        "user", "program", "department", "semester", "section"
    ).all()
    serializer_class = StudentSerializer
    service_class = StudentService
    permission_matrix = STUDENT_MATRIX
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["department", "semester", "section", "status", "program"]
    search_fields = ["full_name", "first_name", "last_name", "roll_no", "email"]
    ordering_fields = ["roll_no", "full_name", "cgpa", "created_at"]

    def get_queryset(self):
        # The detail view prefetches child collections; list stays lean.
        qs = super().get_queryset()
        # ?active=true|false filters by the linked login's is_active, so the
        # roster can show active-only (default) or include deactivated students.
        active = self.request.query_params.get("active")
        if active is not None:
            qs = qs.filter(user__is_active=_truthy(active))
        if self.action == "retrieve":
            return qs.prefetch_related(
                "addresses", "guardians", "documents", "medical"
            )
        return qs

    def perform_destroy(self, instance):
        # `?hard=true` = permanent removal: hard-delete the student (child
        # attendance/fees/etc. cascade) AND their login account, so it's gone
        # from the DB forever. Default stays a soft-delete + login deactivation
        # (StudentService.delete), which is reversible.
        if _truthy(self.request.query_params.get("hard", "")):
            user = instance.user
            instance.hard_delete()
            if user is not None:
                user.hard_delete()
            invalidate_prefix(STUDENTS_PREFIX)
            invalidate_prefix(DASHBOARD_PREFIX)
            return
        super().perform_destroy(instance)

    # -- GET/PUT /students/me -------------------------------------------------
    def _resolve_me(self, request):
        """The Student profile linked to the requesting user (staff-or-self)."""
        student = (
            Student.objects.select_related(
                "user", "program", "department", "semester", "section"
            )
            .filter(user=request.user)
            .first()
        )
        if student is None:
            raise NotFound("No student profile is linked to this account.")
        # Non-staff may only reach their own profile (already filtered by user);
        # the explicit check guards against future query changes.
        if request.user.role not in _STAFF_ROLES and student.user_id != request.user.id:
            raise PermissionDenied("You can only access your own profile.")
        return student

    @extend_schema(
        request=StudentAppSerializer,
        responses={200: StudentAppSerializer},
    )
    @action(detail=False, methods=["get", "put"])
    def me(self, request):
        student = self._resolve_me(request)
        if request.method == "GET":
            return Response(StudentAppSerializer(student).data)

        serializer = StudentAppSerializer(student, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = self.get_service().update(student, **serializer.validated_data)
        return Response(StudentAppSerializer(updated).data)


class StudentAddressViewSet(BaseModelViewSet):
    queryset = StudentAddress.objects.select_related("student").all()
    serializer_class = StudentAddressSerializer
    service_class = StudentAddressService
    permission_matrix = CHILD_MATRIX
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ["student"]
    ordering_fields = ["created_at"]


class GuardianViewSet(BaseModelViewSet):
    queryset = Guardian.objects.select_related("student").all()
    serializer_class = GuardianSerializer
    service_class = GuardianService
    permission_matrix = CHILD_MATRIX
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["student", "is_primary"]
    search_fields = ["name", "phone", "email"]
    ordering_fields = ["name", "created_at"]


class MedicalViewSet(BaseModelViewSet):
    queryset = Medical.objects.select_related("student").all()
    serializer_class = MedicalSerializer
    service_class = MedicalService
    permission_matrix = CHILD_MATRIX
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["student"]


class StudentDocumentViewSet(BaseModelViewSet):
    queryset = StudentDocument.objects.select_related("student").all()
    serializer_class = StudentDocumentSerializer
    service_class = StudentDocumentService
    permission_matrix = CHILD_MATRIX
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["student", "kind"]
    search_fields = ["title"]
    ordering_fields = ["created_at", "title"]


# ---------------------------------------------------------------------------
# Mobile API contract (spec) endpoint — snake_case + {user_id} resolution.
# ---------------------------------------------------------------------------
class StudentProfileByUserView(APIView):
    """``GET /api/v1/students/by-user/{user_id}`` — a student's profile (snake_case).

    ``{user_id}`` is the accounts user id; resolved to the linked
    :class:`Student`. Non-staff callers may only fetch their own profile.
    On its own path so it doesn't shadow the ViewSet's ``{pk}`` detail route.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: StudentProfileSpecSerializer})
    def get(self, request, user_id):
        if request.user.role not in _STAFF_ROLES and str(request.user.id) != str(
            user_id
        ):
            raise PermissionDenied("You can only access your own profile.")
        student = (
            Student.objects.select_related("department", "semester", "section")
            .filter(user_id=user_id)
            .first()
        )
        if student is None:
            raise NotFound("Student profile not found.")
        return Response(StudentProfileSpecSerializer(student).data)
