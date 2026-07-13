"""HTTP layer for the fees app.

``FeeInvoiceViewSet`` serves the mobile contract:

* ``GET  /fees``            — list invoices (scoped to self/child for
  students/parents; full for staff), searchable/filterable/sortable.
* ``POST /fees/{id}/pay``   — record a payment and mark the invoice paid.
* ``GET  /fees/total-due``  — ``{ total }`` of unpaid invoices (scoped).

Writes flow through :class:`FeeInvoiceService` (audit + cache-invalidate). All
business logic (payment recording, status derivation) lives in the service.
"""
from decimal import Decimal

from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from core.cache import cache_get_or_set, cache_key
from core.permissions import Role, resolve_parent_child
from core.viewsets import BaseModelViewSet

from students.models import Student

from fees.models import FeeInvoice, Payment
from fees.permissions import CanAccessInvoice, FEE_MATRIX, student_ids_for
from fees.serializers import (
    FeeInvoiceSerializer,
    FeeInvoiceSpecSerializer,
    FeeSummarySpecSerializer,
    PaymentInputSpecSerializer,
    PaymentResultSpecSerializer,
    PayInputSerializer,
    ReceiptSpecSerializer,
    TotalDueSerializer,
)
from fees.services import FEES_PREFIX, FeeInvoiceService

_STAFF_ROLES = set(Role.STAFF)
# TTL for the per-user fees summary cache (fees:{user_id}); mirrors dashboard.
TTL_FEES = 300


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

    # -- GET /fees/summary ----------------------------------------------------
    # Aggregate money totals over the SAME scoped + filtered (student/status/term/
    # search) queryset the list uses, so the FeeManagement summary cards stay
    # correct even though the list itself is paginated.
    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        from decimal import Decimal
        from django.db.models import Q, Sum

        qs = self.filter_queryset(self.get_queryset())
        unpaid = ~Q(status=FeeInvoice.STATUS_PAID)
        agg = qs.aggregate(
            billed=Sum("amount"),
            outstanding=Sum("amount", filter=unpaid),
            paid=Sum("amount", filter=Q(status=FeeInvoice.STATUS_PAID)),
        )
        zero = Decimal("0")
        return Response(
            {
                "billed": agg["billed"] or zero,
                "outstanding": agg["outstanding"] or zero,
                "paid": agg["paid"] or zero,
                "count": qs.count(),
            }
        )

    # ======================================================================
    # Mobile API contract v1 (snake_case, {user_id}-parameterized) endpoints.
    # ======================================================================
    def _assert_user_access(self, request, user_id):
        """Non-staff may only use their own accounts user id; staff any."""
        if getattr(request.user, "role", None) in _STAFF_ROLES:
            return
        if str(request.user.id) != str(user_id):
            raise PermissionDenied("You can only access your own fees.")

    def _student_for_user_id(self, request, user_id):
        """Resolve the students.Student for an accounts user id (access-checked).

        Parents reuse this endpoint for their child, addressing it with their own
        user id (or the child's), so resolve them to their linked child.
        """
        if getattr(request.user, "role", None) == Role.PARENT:
            return resolve_parent_child(request.user, user_id)
        self._assert_user_access(request, user_id)
        try:
            return Student.objects.get(user_id=user_id)
        except Student.DoesNotExist:
            raise NotFound("No student profile is linked to this user.")

    def _assert_invoice_access(self, request, invoice):
        """Invoice-scoped access: staff any; a student/parent only their own /
        their child's invoices (same ownership model as ``CanAccessInvoice``)."""
        allowed = student_ids_for(request.user)  # None => staff, unrestricted
        if allowed is None:
            return
        if invoice.student_id not in set(allowed):
            raise PermissionDenied("You can only access your own fees.")

    # -- GET /api/v1/fees/{user_id} -----------------------------------------
    @extend_schema(responses={200: FeeSummarySpecSerializer})
    def by_user(self, request, pk=None):
        """Spec: ``{ total_due, paid_amount, pending_amount, invoices:[...] }``.

        The ``<uuid:pk>`` on ``/fees/{user_id}`` is the accounts user id here
        (PUT/PATCH/DELETE on the same path treat it as an invoice pk instead).
        ``total_due`` = total billed across the student's invoices;
        ``paid_amount`` = payments received; ``pending_amount`` = outstanding.
        Cached under ``fees:summary:{user_id}`` (busted on any fee write).
        """
        student = self._student_for_user_id(request, pk)
        repo = self.get_service().repository

        def build():
            invoices = repo.for_student(student.pk).order_by("due_date", "-created_at")
            total_due = invoices.aggregate(t=Sum("amount"))["t"] or Decimal("0")
            paid_amount = (
                Payment.objects.filter(invoice__student_id=student.pk).aggregate(
                    t=Sum("amount")
                )["t"]
                or Decimal("0")
            )
            pending_amount = total_due - paid_amount
            return {
                "total_due": total_due,
                "paid_amount": paid_amount,
                "pending_amount": pending_amount,
                "invoices": FeeInvoiceSpecSerializer(invoices, many=True).data,
            }

        data = cache_get_or_set(
            cache_key(FEES_PREFIX, "summary", student.user_id), TTL_FEES, build
        )
        return Response(data)

    # -- POST /api/v1/fees/payment ------------------------------------------
    @extend_schema(
        request=PaymentInputSpecSerializer,
        responses={201: PaymentResultSpecSerializer},
    )
    def make_payment(self, request):
        """Spec: body ``{ fee_id }`` → ``{ payment_id, receipt_no }``."""
        serializer = PaymentInputSpecSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        invoice = get_object_or_404(
            FeeInvoice.objects.select_related("student"), pk=data["fee_id"]
        )
        self._assert_invoice_access(request, invoice)

        _, payment = self.get_service().record_payment(
            invoice,
            amount=data.get("amount"),
            method=data.get("method"),
            reference=data.get("reference", ""),
        )
        return Response(
            {
                "payment_id": str(payment.pk),
                "receipt_no": FeeInvoiceService.receipt_no(payment),
            },
            status=201,
        )

    # -- GET /api/v1/fees/receipt/{payment_id} ------------------------------
    @extend_schema(responses={200: ReceiptSpecSerializer})
    def receipt(self, request, payment_id=None):
        """Spec: ``GET /fees/receipt/{payment_id}`` → the payment receipt."""
        payment = get_object_or_404(
            Payment.objects.select_related("invoice", "invoice__student"),
            pk=payment_id,
        )
        self._assert_invoice_access(request, payment.invoice)
        invoice = payment.invoice
        return Response(
            {
                "payment_id": str(payment.pk),
                "receipt_no": FeeInvoiceService.receipt_no(payment),
                "fee_id": str(invoice.pk),
                "title": invoice.title,
                "term": invoice.term,
                "amount": payment.amount,
                "method": payment.method,
                "paid_at": payment.paid_at,
                "reference": payment.reference,
                "student_name": invoice.student.full_name,
                "roll_no": invoice.student.roll_no,
            }
        )
