"""HTTP layer for the leave app.

A single :class:`LeaveRequestViewSet` serves the whole workflow, mounted under
``/api/v1/`` by ``config/urls.py``:

- ``GET /leaves`` — the requester's own requests (approvers additionally see the
  requests they may act on: children / department students; admins see all).
- ``GET /leaves/{id}`` — one request (scoped the same way).
- ``POST /leaves`` — apply (``{ type, from, to, reason }``); filed for the
  current user with status ``pending``.
- ``POST /leaves/{id}/approve`` — approve (object-scoped: parent→child,
  faculty/hod→dept students, admin→all).
- ``POST /leaves/{id}/reject`` — reject (same scoping).

Writes flow through :class:`leave.services.LeaveRequestService` (audit + cache
invalidation); the service also owns the approval scoping rules.
"""
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from core.viewsets import BaseModelViewSet

from leave.models import LeaveRequest
from leave.permissions import LEAVE_MATRIX
from leave.serializers import LeaveInputSerializer, LeaveRequestSerializer
from leave.services import LeaveRequestService


class LeaveRequestViewSet(BaseModelViewSet):
    """Leave requests: apply + own list + approve/reject workflow."""

    queryset = LeaveRequest.objects.select_related("user", "decided_by").all()
    serializer_class = LeaveRequestSerializer
    service_class = LeaveRequestService
    permission_matrix = LEAVE_MATRIX
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["status", "type"]
    search_fields = ["reason"]
    ordering_fields = ["applied_on", "start_date", "end_date"]

    # -- scoped queryset -------------------------------------------------
    def get_queryset(self):
        """Scope reads to what the requester may see (own + approvable).

        For detail/approve/reject the scoped set still contains the target (an
        approver's children / department students), and the service re-checks
        authority before mutating.
        """
        service = LeaveRequestService(actor=self.request.user)
        return service.visible_queryset(self.request.user)

    # -- apply -----------------------------------------------------------
    @extend_schema(
        request=LeaveInputSerializer,
        responses={201: LeaveRequestSerializer},
    )
    def create(self, request, *args, **kwargs):
        """``POST /leaves`` — file a leave request for the current user."""
        serializer = LeaveInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        service = LeaveRequestService(actor=request.user, ip=self._client_ip())
        leave = service.apply(
            request.user,
            type=data["type"],
            start_date=data["from_date"],
            end_date=data["to"],
            reason=data.get("reason", ""),
        )
        return Response(LeaveRequestSerializer(leave).data, status=201)

    # -- approve / reject ------------------------------------------------
    @extend_schema(request=None, responses={200: LeaveRequestSerializer})
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        """``POST /leaves/{id}/approve`` — approve (object-scoped)."""
        leave = self.get_object()
        service = LeaveRequestService(actor=request.user, ip=self._client_ip())
        leave = service.approve(leave, request.user)
        return Response(LeaveRequestSerializer(leave).data)

    @extend_schema(request=None, responses={200: LeaveRequestSerializer})
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        """``POST /leaves/{id}/reject`` — reject (object-scoped)."""
        leave = self.get_object()
        service = LeaveRequestService(actor=request.user, ip=self._client_ip())
        leave = service.reject(leave, request.user)
        return Response(LeaveRequestSerializer(leave).data)
