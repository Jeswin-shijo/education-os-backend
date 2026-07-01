"""HTTP layer for the faculty app.

A single :class:`FacultyProfileViewSet` serves both the admin management surface
and the self-scoped mobile reads:

- ``/faculty/`` — admin CRUD + list of faculty profiles.
- ``GET /faculty/me`` — the current user's :class:`FacultyProfile` + classes
  (``facultyService.getProfile`` shape).
- ``GET /faculty/classes`` — the current faculty's classes.
- ``GET /faculty/classes/{id}`` — one class (owner-scoped).
- ``GET /faculty/classes/{id}/roster`` — that class's roster (``RosterStudent[]``).

Self-scoped reads are cached under the ``faculty`` prefix (TTL 3600s); writes
flow through the service layer (audit + cache-invalidation) via
:class:`core.viewsets.BaseModelViewSet`.
"""
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from core.cache import TTL_TIMETABLE, cache_get_or_set, cache_key
from core.permissions import Role
from core.viewsets import BaseModelViewSet

from faculty.models import FacultyClass, FacultyProfile, RosterEntry
from faculty.permissions import FACULTY_PROFILE_MATRIX
from faculty.serializers import (
    FacultyClassAppSerializer,
    FacultyProfileMeSerializer,
    FacultyProfileSerializer,
    RosterStudentSerializer,
)
from faculty.services import FacultyProfileService

# TTL for cached faculty reads (teaching structure is timetable-like, 3600s).
TTL_FACULTY = TTL_TIMETABLE


class FacultyProfileViewSet(BaseModelViewSet):
    """Faculty profiles: admin CRUD + list, plus self-scoped mobile reads."""

    queryset = (
        FacultyProfile.objects.select_related("user", "department")
        .prefetch_related("classes__subject", "classes__semester", "classes__section")
        .all()
    )
    serializer_class = FacultyProfileSerializer
    service_class = FacultyProfileService
    permission_matrix = FACULTY_PROFILE_MATRIX
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["department", "designation"]
    search_fields = ["user__full_name", "user__email", "designation"]
    ordering_fields = ["designation", "created_at"]

    # -- helpers ---------------------------------------------------------
    def _own_profile_or_404(self):
        """Return the current user's FacultyProfile (404 if none)."""
        profile = (
            FacultyProfile.objects.select_related("user", "department")
            .prefetch_related(
                "classes__subject", "classes__semester", "classes__section"
            )
            .filter(user=self.request.user)
            .first()
        )
        if profile is None:
            raise NotFound("No faculty profile for the current user.")
        return profile

    def _class_for_current_user(self, pk):
        """Fetch a FacultyClass, enforcing owner-scoping for faculty users.

        Faculty may only reach their own classes; other staff roles (admin,
        principal, hod) may read any class.
        """
        klass = (
            FacultyClass.objects.select_related(
                "subject", "semester", "section", "faculty", "faculty__user"
            )
            .filter(pk=pk)
            .first()
        )
        if klass is None:
            raise NotFound("Class not found.")
        if self.request.user.role == Role.FACULTY:
            if klass.faculty.user_id != self.request.user.id:
                raise PermissionDenied("You can only access your own classes.")
        return klass

    # -- self-scoped mobile reads ----------------------------------------
    @extend_schema(responses={200: FacultyProfileMeSerializer})
    @action(detail=False, methods=["get"])
    def me(self, request):
        """``GET /faculty/me`` — current user's profile + classes."""
        profile = self._own_profile_or_404()
        data = cache_get_or_set(
            cache_key("faculty", "me", profile.pk),
            TTL_FACULTY,
            lambda: FacultyProfileMeSerializer(profile).data,
        )
        return Response(data)

    @extend_schema(responses={200: FacultyClassAppSerializer(many=True)})
    @action(detail=False, methods=["get"])
    def classes(self, request):
        """``GET /faculty/classes`` — the current faculty's classes."""
        profile = self._own_profile_or_404()

        def build():
            qs = (
                FacultyClass.objects.select_related(
                    "subject", "semester", "section"
                )
                .filter(faculty=profile)
                .order_by("subject__code")
            )
            return [FacultyClassAppSerializer(k).data for k in qs]

        data = cache_get_or_set(
            cache_key("faculty", "classes", profile.pk), TTL_FACULTY, build
        )
        return Response(data)

    @extend_schema(responses={200: FacultyClassAppSerializer})
    @action(detail=False, methods=["get"], url_path="classes/(?P<pk>[^/.]+)")
    def class_detail(self, request, pk=None):
        """``GET /faculty/classes/{id}`` — one class (owner-scoped)."""
        klass = self._class_for_current_user(pk)
        return Response(FacultyClassAppSerializer(klass).data)

    @extend_schema(responses={200: RosterStudentSerializer(many=True)})
    @action(
        detail=False,
        methods=["get"],
        url_path="classes/(?P<pk>[^/.]+)/roster",
    )
    def roster(self, request, pk=None):
        """``GET /faculty/classes/{id}/roster`` — the class roster."""
        klass = self._class_for_current_user(pk)

        def build():
            qs = RosterEntry.objects.filter(faculty_class=klass).order_by("roll_no")
            return [RosterStudentSerializer(e).data for e in qs]

        data = cache_get_or_set(
            cache_key("faculty", "roster", klass.pk), TTL_FACULTY, build
        )
        return Response(data)
