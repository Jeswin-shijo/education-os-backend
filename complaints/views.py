"""HTTP layer for the complaints app.

A single :class:`ComplaintViewSet` serves the mobile ``complaintService`` and the
Principal/Admin monitoring surface:

- ``GET /complaints`` — the caller's own complaints (students/parents); staff
  roles see the wider (institution) scope. ``types.ts`` ``Complaint[]`` shape.
- ``GET /complaints/{id}`` — one complaint (own, or any for staff).
- ``POST /complaints`` — file a complaint (``ComplaintInput``); owner is the
  request user, status defaults to ``open``.
- ``PATCH /complaints/{id}`` — staff status-workflow transition
  (``open``/``in_progress``/``resolved``).
- ``GET /complaints/monitor`` — Principal/Admin: all complaints + status counts
  (cached under the ``complaints`` prefix, TTL 300s).

Writes flow through the service layer (audit + cache-invalidation) via
:class:`core.viewsets.BaseModelViewSet`.
"""
from django.db.models import Count
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from core.cache import cache_get_or_set, cache_key
from core.permissions import Role
from core.viewsets import BaseModelViewSet

from complaints.models import Complaint
from complaints.permissions import COMPLAINT_MATRIX
from complaints.serializers import (
    ComplaintCreateSerializer,
    ComplaintMonitorSerializer,
    ComplaintSerializer,
    ComplaintStatusSerializer,
)
from complaints.services import ComplaintService

# Complaint monitor is a dashboard-like rollup; cache for 300s.
TTL_COMPLAINTS = 300


class ComplaintViewSet(BaseModelViewSet):
    """Complaints: own-complaint reads/writes + Principal/Admin monitor."""

    queryset = Complaint.objects.select_related("user").all()
    serializer_class = ComplaintSerializer
    service_class = ComplaintService
    permission_matrix = COMPLAINT_MATRIX
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["status", "category"]
    search_fields = ["subject", "description", "category"]
    ordering_fields = ["created_on", "status"]

    def get_serializer_class(self):
        if self.action == "create":
            return ComplaintCreateSerializer
        if self.action == "partial_update":
            return ComplaintStatusSerializer
        return ComplaintSerializer

    def _is_staff_role(self, user) -> bool:
        return getattr(user, "role", None) in set(Role.STAFF)

    def get_queryset(self):
        """Scope: staff see all; everyone else sees only their own complaints."""
        qs = super().get_queryset()
        user = self.request.user
        if self._is_staff_role(user):
            return qs
        return qs.filter(user=user)

    # -- own / scoped list -----------------------------------------------
    @extend_schema(responses={200: ComplaintSerializer(many=True)})
    def list(self, request, *args, **kwargs):
        """``GET /complaints`` — own complaints (staff: institution scope)."""
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        rows = page if page is not None else list(qs)
        data = ComplaintSerializer(rows, many=True).data
        if page is not None:
            return self.get_paginated_response(data)
        return Response(data)

    @extend_schema(responses={200: ComplaintSerializer})
    def retrieve(self, request, *args, **kwargs):
        """``GET /complaints/{id}`` — one complaint (own, or any for staff)."""
        instance = self.get_object()
        return Response(ComplaintSerializer(instance).data)

    # -- create ----------------------------------------------------------
    @extend_schema(
        request=ComplaintCreateSerializer,
        responses={201: ComplaintSerializer},
    )
    def create(self, request, *args, **kwargs):
        """``POST /complaints`` — file a complaint (owner = request user)."""
        serializer = ComplaintCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        service = self.get_service()
        instance = service.create(user=request.user, **serializer.validated_data)
        return Response(ComplaintSerializer(instance).data, status=201)

    # -- status workflow (staff) -----------------------------------------
    @extend_schema(
        request=ComplaintStatusSerializer,
        responses={200: ComplaintSerializer},
    )
    def partial_update(self, request, *args, **kwargs):
        """``PATCH /complaints/{id}`` — staff status-workflow transition."""
        instance = self.get_object()
        serializer = ComplaintStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        service = self.get_service()
        instance = service.set_status(instance, serializer.validated_data["status"])
        return Response(ComplaintSerializer(instance).data)

    # -- monitor (principal/admin) ---------------------------------------
    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="status",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Filter monitored complaints by status.",
            )
        ],
        responses={200: ComplaintMonitorSerializer},
    )
    @action(detail=False, methods=["get"], url_path="monitor")
    def monitor(self, request):
        """``GET /complaints/monitor`` — all complaints + status counts."""
        status_filter = request.query_params.get("status")

        def build():
            base = Complaint.objects.select_related("user").all()
            counts = {row["status"]: row["n"] for row in base.values("status").annotate(n=Count("id"))}
            by_status = [
                {"status": value, "count": counts.get(value, 0)}
                for value, _label in Complaint.STATUS_CHOICES
            ]
            listing = base if not status_filter else base.filter(status=status_filter)
            return {
                "total": base.count(),
                "byStatus": by_status,
                "complaints": list(listing),
            }

        cacheable = not (
            request.query_params.get("search")
            or request.query_params.get("ordering")
        )
        if cacheable:
            payload = cache_get_or_set(
                cache_key("complaints", "monitor", status_filter or "all"),
                TTL_COMPLAINTS,
                build,
            )
        else:
            payload = build()

        complaints = payload["complaints"]
        page = self.paginate_queryset(complaints)
        if page is not None:
            data = ComplaintMonitorSerializer(
                {
                    "total": payload["total"],
                    "byStatus": payload["byStatus"],
                    "complaints": page,
                }
            ).data
            return self.get_paginated_response(data)
        return Response(ComplaintMonitorSerializer(payload).data)
