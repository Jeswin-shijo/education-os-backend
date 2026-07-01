"""HTTP layer for the placement app.

``PlacementOpeningViewSet`` serves:

- ``GET  /placements`` — active openings in the ``types.ts`` ``PlacementOpening``
  shape (per-student ``applied`` flag), filterable/searchable; admins may pass
  ``?all=1`` to include inactive postings.
- ``GET  /placements/{id}`` — one opening (app-shaped).
- ``POST /placements/{id}/apply`` — student applies; returns the opening with
  ``applied: true``.
- ``GET  /placements/applications`` — the requesting student's own applications.
- ``GET  /placements/stats`` — admin/principal placement stats rollup.
- ``POST/PATCH/DELETE /placements-admin/…`` — admin opening CRUD.

``PlacementApplicationViewSet`` gives admins the full application table
(status transitions).

Writes flow through the service layer (audit + cache-invalidation) via
:class:`core.viewsets.BaseModelViewSet`.
"""
from decimal import Decimal

from django.db.models import Avg, Count, Max, Q
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from core.cache import TTL_DASHBOARD, cache_get_or_set, cache_key
from core.permissions import Role
from core.viewsets import BaseModelViewSet

from placement.models import PlacementApplication, PlacementOpening
from placement.permissions import APPLICATION_MATRIX, OPENING_MATRIX
from placement.serializers import (
    PlacementApplicationAppSerializer,
    PlacementApplicationSerializer,
    PlacementOpeningAppSerializer,
    PlacementOpeningSerializer,
    PlacementStatsSerializer,
)
from placement.services import PlacementApplicationService, PlacementOpeningService
from students.models import Student

_STAFF_ROLES = set(Role.STAFF)


class PlacementOpeningViewSet(BaseModelViewSet):
    queryset = PlacementOpening.objects.all()
    serializer_class = PlacementOpeningSerializer
    service_class = PlacementOpeningService
    permission_matrix = OPENING_MATRIX
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["is_active", "location", "company"]
    search_fields = ["company", "role", "location", "eligibility"]
    ordering_fields = ["last_date", "ctc", "company", "created_at"]

    # -- helpers ---------------------------------------------------------
    def _current_student(self):
        """Return the Student row for the current user (or ``None``)."""
        return (
            Student.objects.filter(user=self.request.user)
            .order_by("created_at")
            .first()
        )

    def _resolve_student(self):
        student = self._current_student()
        if student is None:
            raise NotFound("No student profile is linked to this account.")
        return student

    def _applied_ids(self, student):
        """Set of opening ids the student has an application on file for."""
        if student is None:
            return set()
        return set(
            PlacementApplication.objects.filter(student=student).values_list(
                "opening_id", flat=True
            )
        )

    def _visible_openings(self):
        """Active openings by default; admins may include inactive via ?all=1."""
        qs = PlacementOpening.objects.all()
        include_all = (self.request.query_params.get("all") or "").lower() in (
            "1",
            "true",
            "yes",
        )
        if not (include_all and self.request.user.role in set(Role.ADMINS)):
            qs = qs.filter(is_active=True)
        return qs

    # -- GET /placements (app-shaped openings) ---------------------------
    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="all",
                type=bool,
                required=False,
                description="Admins only: include inactive openings.",
            )
        ],
        responses={200: PlacementOpeningAppSerializer(many=True)},
    )
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self._visible_openings())
        page = self.paginate_queryset(queryset)
        rows = page if page is not None else list(queryset)

        student = self._current_student()
        context = {"applied_ids": self._applied_ids(student)}
        data = PlacementOpeningAppSerializer(rows, many=True, context=context).data

        if page is not None:
            return self.get_paginated_response(data)
        return Response(data)

    @extend_schema(responses={200: PlacementOpeningAppSerializer})
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        student = self._current_student()
        context = {"applied_ids": self._applied_ids(student)}
        return Response(
            PlacementOpeningAppSerializer(instance, context=context).data
        )

    # -- POST /placements/{id}/apply -------------------------------------
    @extend_schema(request=None, responses={200: PlacementOpeningAppSerializer})
    @action(detail=True, methods=["post"])
    def apply(self, request, pk=None):
        """``POST /placements/{id}/apply`` — student applies to an opening."""
        opening = self.get_object()
        student = self._resolve_student()

        service = PlacementApplicationService(
            actor=request.user, ip=self._client_ip()
        )
        service.apply(opening, student)

        # Return the opening reflecting the fresh application (applied=true).
        context = {"applied_ids": self._applied_ids(student)}
        return Response(
            PlacementOpeningAppSerializer(opening, context=context).data
        )

    # -- GET /placements/applications (own) ------------------------------
    @extend_schema(responses={200: PlacementApplicationAppSerializer(many=True)})
    @action(detail=False, methods=["get"])
    def applications(self, request):
        """``GET /placements/applications`` — requesting student's applications."""
        student = self._resolve_student()
        qs = (
            PlacementApplication.objects.select_related("opening")
            .filter(student=student)
            .order_by("-applied_on")
        )
        page = self.paginate_queryset(qs)
        rows = page if page is not None else list(qs)
        data = PlacementApplicationAppSerializer(rows, many=True).data
        if page is not None:
            return self.get_paginated_response(data)
        return Response(data)

    # -- GET /placements/stats (admin/principal) -------------------------
    @extend_schema(responses={200: PlacementStatsSerializer})
    @action(detail=False, methods=["get"])
    def stats(self, request):
        """``GET /placements/stats`` — placement rollup (cached, TTL 300s)."""
        key = cache_key("placement", "stats", "institution")

        def produce():
            openings = PlacementOpening.objects.all()
            apps = PlacementApplication.objects.select_related("opening")

            status_counts = {
                row["status"]: row["count"]
                for row in apps.values("status").annotate(count=Count("id"))
            }
            selected = apps.filter(status=PlacementApplication.STATUS_SELECTED)
            placed = selected.values("student_id").distinct().count()

            # CTC of selected offers (converted to lakhs-per-annum for the app).
            sel_agg = selected.aggregate(
                avg_ctc=Avg("opening__ctc"), max_ctc=Max("opening__ctc")
            )
            avg_ctc = sel_agg["avg_ctc"] or Decimal("0")
            max_ctc = sel_agg["max_ctc"] or Decimal("0")

            top_recruiters = list(
                selected.values_list("opening__company", flat=True).distinct()[:5]
            )

            return {
                "placed": placed,
                "eligible": Student.objects.count(),
                "avgCtcLpa": round(float(avg_ctc) / 100000.0, 2),
                "highestCtcLpa": round(float(max_ctc) / 100000.0, 2),
                "topRecruiters": top_recruiters,
                "openings": openings.count(),
                "activeOpenings": openings.filter(is_active=True).count(),
                "totalApplications": apps.count(),
                "byStatus": status_counts,
            }

        data = cache_get_or_set(key, TTL_DASHBOARD, produce)
        return Response(PlacementStatsSerializer(data).data)


class PlacementApplicationViewSet(BaseModelViewSet):
    queryset = PlacementApplication.objects.select_related(
        "opening", "student"
    ).all()
    serializer_class = PlacementApplicationSerializer
    service_class = PlacementApplicationService
    permission_matrix = APPLICATION_MATRIX
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ["opening", "student", "status"]
    ordering_fields = ["applied_on", "status", "created_at"]
