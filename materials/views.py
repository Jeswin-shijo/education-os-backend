"""HTTP layer for the materials app.

A single :class:`MaterialViewSet` serves both the student-facing reads and the
faculty upload/list surface:

- ``GET /materials?subjectId=`` — list in the student-facing ``types.ts``
  ``Material`` shape (camelCase), filterable by subject.
- ``GET /materials/{id}`` — one material (student-facing shape).
- ``POST /materials`` — faculty/admin upload metadata (CRUD shape;
  ``subject``/``faculty_class`` FK ids + ``file``/``url``).
- ``GET /materials/faculty`` — faculty-created list (``FacultyMaterial[]``,
  ``?classId=`` filter, own-classes only for faculty).

Student reads are cached under the ``materials`` prefix (TTL 600s); writes flow
through the service layer (audit + cache-invalidation) via
:class:`core.viewsets.BaseModelViewSet`.
"""
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from core.cache import cache_get_or_set, cache_key
from core.permissions import Role
from core.viewsets import BaseModelViewSet

from materials.models import Material
from materials.permissions import MATERIAL_MATRIX
from materials.serializers import (
    FacultyMaterialSerializer,
    MaterialSerializer,
    StudentMaterialSerializer,
)
from materials.services import MaterialService

# Materials are library-like content; cache student reads for 600s.
TTL_MATERIALS = 600


class MaterialViewSet(BaseModelViewSet):
    """Materials: student-facing reads + faculty upload/list."""

    queryset = Material.objects.select_related(
        "subject", "faculty_class", "faculty_class__subject"
    ).all()
    serializer_class = MaterialSerializer
    service_class = MaterialService
    permission_matrix = MATERIAL_MATRIX
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["kind", "subject", "faculty_class"]
    search_fields = ["title", "subject__code", "subject__name"]
    ordering_fields = ["added_at", "title"]

    # -- student-facing list / retrieve ----------------------------------
    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="subjectId",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Filter materials by subject id.",
            )
        ],
        responses={200: StudentMaterialSerializer(many=True)},
    )
    def list(self, request, *args, **kwargs):
        """``GET /materials?subjectId=`` — student-facing list."""
        subject_id = request.query_params.get("subjectId")

        def build():
            qs = self.filter_queryset(self.get_queryset())
            if subject_id:
                # Match either the direct subject or the class's subject.
                qs = qs.filter(subject_id=subject_id)
            return list(qs)

        # Cache the unpaginated, subject-scoped id/row set only when there is no
        # dynamic search/ordering in play (keep the cache key simple + safe).
        cacheable = not (
            request.query_params.get("search")
            or request.query_params.get("ordering")
        )
        if cacheable:
            rows = cache_get_or_set(
                cache_key("materials", "subject", subject_id or "all"),
                TTL_MATERIALS,
                build,
            )
        else:
            rows = build()

        page = self.paginate_queryset(rows)
        target = page if page is not None else rows
        data = StudentMaterialSerializer(target, many=True).data
        if page is not None:
            return self.get_paginated_response(data)
        return Response(data)

    @extend_schema(responses={200: StudentMaterialSerializer})
    def retrieve(self, request, *args, **kwargs):
        """``GET /materials/{id}`` — one material (student-facing shape)."""
        instance = self.get_object()
        return Response(StudentMaterialSerializer(instance).data)

    # -- faculty-created list --------------------------------------------
    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="classId",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Filter faculty materials by class id.",
            )
        ],
        responses={200: FacultyMaterialSerializer(many=True)},
    )
    @action(detail=False, methods=["get"], url_path="faculty")
    def faculty_materials(self, request):
        """``GET /materials/faculty`` — faculty-created list (``?classId=``)."""
        qs = (
            Material.objects.select_related("faculty_class", "subject")
            .filter(faculty_class__isnull=False)
            .order_by("-added_at")
        )

        # Faculty see only their own classes' materials; admins see all.
        if request.user.role == Role.FACULTY:
            qs = qs.filter(faculty_class__faculty__user=request.user)

        class_id = request.query_params.get("classId")
        if class_id:
            qs = qs.filter(faculty_class_id=class_id)

        page = self.paginate_queryset(qs)
        rows = page if page is not None else list(qs)
        data = FacultyMaterialSerializer(rows, many=True).data
        if page is not None:
            return self.get_paginated_response(data)
        return Response(data)
