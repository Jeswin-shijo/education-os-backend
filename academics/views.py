"""HTTP layer for the academics app.

CRUD viewsets (departments, programs, semesters, sections, subjects) extend
:class:`core.viewsets.BaseModelViewSet` so writes flow through the service layer
(audit + cache-invalidation) and the global renderer/pagination apply.

Timetable is exposed via a read-focused viewset with ``week`` (grouped by
weekday) and ``today`` custom actions, both cached (TTL 3600s). The mobile app's
``GET /subjects/:id`` is served by ``SubjectViewSet.retrieve`` using the
app-shaped serializer.
"""
from datetime import date

from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.cache import TTL_SUBJECTS, TTL_TIMETABLE, cache_get_or_set, cache_key
from core.permissions import Role, RoleModelPermission
from core.viewsets import BaseModelViewSet

from academics.models import (
    ClassSession,
    Department,
    Program,
    Section,
    Semester,
    Subject,
)
from academics.permissions import (
    ADMIN_HOD_WRITE_MATRIX,
    ADMIN_WRITE_MATRIX,
    TIMETABLE_MATRIX,
)
from academics.serializers import (
    AcademicProgressSerializer,
    AcademicRecordSerializer,
    ClassSessionAppSerializer,
    ClassSessionSerializer,
    DepartmentSerializer,
    ProgramSerializer,
    SectionSerializer,
    SemesterSerializer,
    SubjectAppSerializer,
    SubjectSerializer,
)
from academics.services import (
    AcademicProgressService,
    AcademicRecordService,
    ClassSessionService,
    DepartmentService,
    ProgramService,
    SectionService,
    SemesterService,
    SubjectService,
)

_STAFF_ROLES = set(Role.STAFF)


def _resolve_student_for_user_id(request, user_id):
    """Resolve the :class:`students.Student` for an accounts ``user_id``.

    Enforces the contract access rule: a student/parent may only use their OWN
    ``user_id``; staff/admin may use any. Raises ``PermissionDenied`` (403) on a
    cross-user request and ``NotFound`` (404) when no live student profile is
    linked to the given user id.
    """
    user = request.user
    if user.role not in _STAFF_ROLES and str(user.id) != str(user_id):
        raise PermissionDenied("You can only access your own data.")

    from students.models import Student

    student = (
        Student.objects.select_related(
            "user", "program", "department", "semester", "section"
        )
        .filter(user_id=user_id, is_deleted=False)
        .first()
    )
    if student is None:
        raise NotFound("No student profile is linked to this user.")
    return student


def _client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class AcademicRecordView(APIView):
    """``GET /api/v1/academics/{user_id}`` — the student's academic record.

    Spec-exact snake_case ``{ degree, department, semester, section, mentor,
    cgpa }``; ``{user_id}`` is the accounts user id, self-scoped for
    students/parents.
    """

    permission_classes = [IsAuthenticated, RoleModelPermission]
    permission_matrix = {"get": list(Role.ALL)}

    @extend_schema(responses={200: AcademicRecordSerializer})
    def get(self, request, user_id):
        student = _resolve_student_for_user_id(request, user_id)
        service = AcademicRecordService(actor=request.user, ip=_client_ip(request))
        data = AcademicRecordSerializer(service.academic_record(student)).data
        return Response(data)


class AcademicProgressView(APIView):
    """``GET /api/v1/progress/{user_id}`` — the student's academic progress.

    Spec-exact snake_case ``{ gpa_trend:[{semester,gpa}], semester_gpa,
    overall_cgpa, ai_insights:[...] }``; ``{user_id}`` is the accounts user id,
    self-scoped for students/parents.
    """

    permission_classes = [IsAuthenticated, RoleModelPermission]
    permission_matrix = {"get": list(Role.ALL)}

    @extend_schema(responses={200: AcademicProgressSerializer})
    def get(self, request, user_id):
        student = _resolve_student_for_user_id(request, user_id)
        service = AcademicProgressService(actor=request.user, ip=_client_ip(request))
        data = AcademicProgressSerializer(service.progress(student)).data
        return Response(data)

# Map Python weekday() (Mon=0) to the app's weekday codes. Sunday (6) has no
# code in the contract (Mon..Sat only) -> resolves to None.
_WEEKDAY_BY_INDEX = {
    0: ClassSession.DAY_MON,
    1: ClassSession.DAY_TUE,
    2: ClassSession.DAY_WED,
    3: ClassSession.DAY_THU,
    4: ClassSession.DAY_FRI,
    5: ClassSession.DAY_SAT,
}


class DepartmentViewSet(BaseModelViewSet):
    queryset = Department.objects.select_related("hod").all()
    serializer_class = DepartmentSerializer
    service_class = DepartmentService
    permission_matrix = ADMIN_WRITE_MATRIX
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["code"]
    search_fields = ["code", "name"]
    ordering_fields = ["code", "name", "created_at"]

    @action(detail=False, methods=["get"], url_path="hod-candidates")
    def hod_candidates(self, request):
        """``GET /departments/hod-candidates`` — faculty/hod users for dropdown."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        users = User.objects.filter(
            role__in=[Role.FACULTY, Role.HOD],
            is_active=True,
        ).values("id", "full_name", "email", "role").order_by("full_name")
        return Response(list(users))


class ProgramViewSet(BaseModelViewSet):
    queryset = Program.objects.select_related("department").all()
    serializer_class = ProgramSerializer
    service_class = ProgramService
    permission_matrix = ADMIN_WRITE_MATRIX
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["code", "department"]
    search_fields = ["code", "name"]
    ordering_fields = ["code", "name", "intake", "created_at"]


class SemesterViewSet(BaseModelViewSet):
    queryset = Semester.objects.select_related("program").all()
    serializer_class = SemesterSerializer
    service_class = SemesterService
    permission_matrix = ADMIN_WRITE_MATRIX
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ["program", "number"]
    ordering_fields = ["number", "created_at"]


class SectionViewSet(BaseModelViewSet):
    queryset = Section.objects.select_related("semester").all()
    serializer_class = SectionSerializer
    service_class = SectionService
    permission_matrix = ADMIN_HOD_WRITE_MATRIX
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["semester", "name"]
    search_fields = ["name"]
    ordering_fields = ["name", "created_at"]


class SubjectViewSet(BaseModelViewSet):
    queryset = (
        Subject.objects.select_related(
            "department", "faculty", "program", "semester", "semester__program"
        )
        .prefetch_related("faculties__user")
        .all()
    )
    serializer_class = SubjectSerializer
    service_class = SubjectService
    permission_matrix = ADMIN_HOD_WRITE_MATRIX
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = [
        "code",
        "department",
        "program",
        "semester",
        "credits",
        "faculty",
        "faculties",
        "academic_session",
    ]
    search_fields = ["code", "name", "faculty_name"]
    ordering_fields = ["code", "name", "credits", "created_at"]

    @action(
        detail=False,
        methods=["get"],
        permission_classes=[IsAuthenticated],
    )
    def mine(self, request):
        """``GET /subjects/mine`` — the requesting student's enrolled subjects.

        App-shaped (camelCase, with ``color``) and scoped to the student's
        semester (falling back to their department). Empty list for a user with
        no student profile. This is what the mobile Subjects screen consumes, so
        the ids it navigates with are the backend's real subject ids.
        """
        from students.models import Student

        student = Student.objects.filter(
            user=request.user, is_deleted=False
        ).first()
        if student is None:
            return Response([])
        qs = self.get_queryset()
        if student.semester_id:
            qs = qs.filter(semester_id=student.semester_id)
        elif student.department_id:
            qs = qs.filter(department_id=student.department_id)
        else:
            qs = qs.none()
        return Response(SubjectAppSerializer(qs.order_by("code"), many=True).data)

    @action(detail=False, methods=["get"], url_path="faculty-candidates")
    def faculty_candidates(self, request):
        """``GET /subjects/faculty-candidates`` — faculty users for dropdown."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        users = User.objects.filter(
            role=Role.FACULTY,
            is_active=True,
        ).values("id", "full_name", "email").order_by("full_name")
        return Response(list(users))

    def retrieve(self, request, *args, **kwargs):
        """``GET /subjects/:id`` — returns the app-shaped Subject (cached)."""
        instance = self.get_object()
        data = cache_get_or_set(
            cache_key(SubjectAppSerializer.Meta.model.__name__.lower(), "app", instance.pk),
            TTL_SUBJECTS,
            lambda: SubjectAppSerializer(instance).data,
        )
        return Response(data)


class TimetableViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Weekly class-session timetable.

    - ``GET /timetable/`` — flat list (paginated/filterable).
    - ``GET /timetable/week/`` — sessions grouped by weekday (Mon..Sat).
    - ``GET /timetable/today/`` — today's sessions (flat list).
    Writes (admin-only) flow through :class:`ClassSessionService`.
    """

    queryset = ClassSession.objects.select_related(
        "subject", "section", "faculty"
    ).all()
    serializer_class = ClassSessionSerializer
    service_class = ClassSessionService
    permission_classes = [IsAuthenticated, RoleModelPermission]
    permission_matrix = TIMETABLE_MATRIX
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    # ``faculty`` filters the timetable to one faculty member's sessions
    # (``GET /timetable?faculty=<user_id>``).
    filterset_fields = ["section", "subject", "day", "type", "faculty", "shift", "status"]
    ordering_fields = ["day", "start", "created_at"]

    # -- service-backed writes (mirror BaseModelViewSet) -----------------
    def _client_ip(self):
        xff = self.request.META.get("HTTP_X_FORWARDED_FOR")
        if xff:
            return xff.split(",")[0].strip()
        return self.request.META.get("REMOTE_ADDR")

    def get_service(self):
        return self.service_class(actor=self.request.user, ip=self._client_ip())

    def perform_create(self, serializer):
        serializer.instance = self.get_service().create(**serializer.validated_data)

    def perform_update(self, serializer):
        serializer.instance = self.get_service().update(
            serializer.instance, **serializer.validated_data
        )

    def perform_destroy(self, instance):
        self.get_service().delete(instance)

    def _section_scope(self):
        """Optional ``?section=<id>`` scoping for the grouped/today reads."""
        return self.request.query_params.get("section") or "all"

    @extend_schema(responses={200: ClassSessionAppSerializer(many=True)})
    @action(detail=False, methods=["get"])
    def week(self, request):
        """Sessions grouped by weekday: ``{Mon:[...], Tue:[...], ...}``."""
        section = self._section_scope()

        def build():
            qs = ClassSession.objects.select_related("subject").all()
            if section != "all":
                qs = qs.filter(section_id=section)
            grouped = {day: [] for day in ClassSession.DAY_ORDER}
            for sess in qs.order_by("start"):
                if sess.day in grouped:
                    grouped[sess.day].append(ClassSessionAppSerializer(sess).data)
            return grouped

        data = cache_get_or_set(
            cache_key("timetable", "week", section), TTL_TIMETABLE, build
        )
        return Response(data)

    @extend_schema(responses={200: ClassSessionAppSerializer(many=True)})
    @action(detail=False, methods=["get"])
    def today(self, request):
        """Today's sessions (flat list, app-shaped)."""
        section = self._section_scope()
        today_code = _WEEKDAY_BY_INDEX.get(date.today().weekday())

        def build():
            if today_code is None:
                return []
            qs = ClassSession.objects.select_related("subject").filter(day=today_code)
            if section != "all":
                qs = qs.filter(section_id=section)
            return [
                ClassSessionAppSerializer(sess).data for sess in qs.order_by("start")
            ]

        data = cache_get_or_set(
            cache_key("timetable", "today", today_code or "none", section),
            TTL_TIMETABLE,
            build,
        )
        return Response(data)
