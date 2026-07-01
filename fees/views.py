"""HTTP layer for the fees app.

``FeeInvoiceViewSet`` serves the mobile contract:

* ``GET  /fees``            — list invoices (scoped to self/child for
  students/parents; full for staff), searchable/filterable/sortable.
* ``POST /fees/{id}/pay``   — record a payment and mark the invoice paid.
* ``GET  /fees/total-due``  — ``{ total }`` of unpaid invoices (scoped).

Writes flow through :class:`FeeInvoiceService` (audit + cache-invalidate). All
business logic (payment recording, status derivation) lives in the service.
"""
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from core.permissions import Role
from core.viewsets import BaseModelViewSet

from fees.models import FeeInvoice
from fees.permissions import CanAccessInvoice, FEE_MATRIX, student_ids_for
from fees.serializers import (
    FeeInvoiceSerializer,
    PayInputSerializer,
    TotalDueSerializer,
)
from fees.services import FeeInvoiceService

_STAFF_ROLES = set(Role.STAFF)


class FeeInvoiceViewSet(BaseModelViewSet):
    queryset = FeeInvoice.objects.select_related("student", "student__user").all()
    serializer_class = FeeInvoiceSerializer
    service_class = FeeInvoiceService
    permission_matrix = FEE_MATRIX
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["student", "status", "term"]
    search_fields = ["title", "term"]
    ordering_fields = ["due_date", "amount", "status", "created_at"]

    def get_permissions(self):
        perms = super().get_permissions()
        # Object-level scoping for detail/pay (list is scoped via get_queryset).
        if self.action in {"retrieve", "update", "partial_update", "destroy", "pay"}:
            perms.append(CanAccessInvoice())
        return perms

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        allowed = student_ids_for(user)  # None => staff, no restriction
        if allowed is None:
            return qs
        return qs.filter(student_id__in=allowed)

    # -- POST /fees/{id}/pay --------------------------------------------------
    @extend_schema(request=PayInputSerializer, responses={200: FeeInvoiceSerializer})
    @action(detail=True, methods=["post"])
    def pay(self, request, pk=None):
        invoice = self.get_object()  # runs CanAccessInvoice object check
        serializer = PayInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        updated = self.get_service().pay(
            invoice,
            amount=data.get("amount"),
            method=data.get("method"),
            reference=data.get("reference", ""),
        )
        return Response(FeeInvoiceSerializer(updated).data)

    # -- GET /fees/total-due --------------------------------------------------
    @extend_schema(responses={200: TotalDueSerializer})
    @action(detail=False, methods=["get"], url_path="total-due")
    def total_due(self, request):
        user = request.user
        allowed = student_ids_for(user)  # None => staff
        # Staff see the institution-wide total; students/parents their scoped one.
        if allowed is None:
            total = self.get_service().total_due()
        elif len(allowed) == 1:
            total = self.get_service().total_due(student_id=allowed[0])
        else:
            # No students (or multiple children): sum the scoped queryset.
            from decimal import Decimal
            from django.db.models import Sum

            agg = (
                self.get_queryset()
                .exclude(status=FeeInvoice.STATUS_PAID)
                .aggregate(total=Sum("amount"))["total"]
            )
            total = agg or Decimal("0")
        return Response({"total": total})
