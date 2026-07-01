"""Data-access layer for the fees app.

Repositories wrap each model over the soft-delete-aware default manager and add
``select_related``/``prefetch_related`` where serializers/queries touch related
objects, avoiding N+1 on the fee list and payment endpoints.
"""
from __future__ import annotations

from decimal import Decimal

from django.db.models import Sum

from core.repositories import BaseRepository

from fees.models import FeeInvoice, Payment


class FeeInvoiceRepository(BaseRepository):
    model = FeeInvoice

    def get_queryset(self, include_deleted: bool = False):
        return (
            super()
            .get_queryset(include_deleted)
            .select_related("student", "student__user")
        )

    def for_student(self, student_id):
        """Invoices belonging to a single student."""
        return self.get_queryset().filter(student_id=student_id)

    def total_due(self, student_id=None) -> Decimal:
        """Sum of unpaid (``due``/``overdue``) invoice amounts, optionally scoped."""
        qs = self.get_queryset().exclude(status=FeeInvoice.STATUS_PAID)
        if student_id is not None:
            qs = qs.filter(student_id=student_id)
        total = qs.aggregate(total=Sum("amount"))["total"]
        return total or Decimal("0")


class PaymentRepository(BaseRepository):
    model = Payment

    def get_queryset(self, include_deleted: bool = False):
        return super().get_queryset(include_deleted).select_related("invoice")

    def paid_total(self, invoice_id) -> Decimal:
        """Sum of all payments recorded against an invoice."""
        total = self.get_queryset().filter(invoice_id=invoice_id).aggregate(
            total=Sum("amount")
        )["total"]
        return total or Decimal("0")
