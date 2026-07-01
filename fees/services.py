"""Business-logic layer for the fees app.

Services extend :class:`core.services.BaseService` so every write auto-stamps
``created_by``/``updated_by``, emits an :class:`~core.models.AuditLog` row and
invalidates the cached fee views. All fee business rules live here — never in
views: recomputing invoice status, and the ``pay`` flow that records a
:class:`~fees.models.Payment` and marks the invoice paid.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from core.cache import invalidate_prefix
from core.models import AuditLog
from core.services import BaseService

from fees.models import FeeInvoice, Payment
from fees.repositories import FeeInvoiceRepository, PaymentRepository

# Cache key prefix owned by this app.
FEES_PREFIX = "fees"


class FeeInvoiceService(BaseService):
    model = FeeInvoice
    repository_class = FeeInvoiceRepository
    entity_name = "FeeInvoice"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.payments = PaymentRepository(Payment)

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(FEES_PREFIX)

    # -- status ----------------------------------------------------------
    @staticmethod
    def _derive_status(invoice: FeeInvoice, paid_total: Decimal) -> str:
        """paid once payments cover the amount; overdue past due while unpaid."""
        if paid_total >= invoice.amount:
            return FeeInvoice.STATUS_PAID
        due = invoice.due_date
        if due is not None and due < timezone.now().date():
            return FeeInvoice.STATUS_OVERDUE
        return FeeInvoice.STATUS_DUE

    # -- pay flow --------------------------------------------------------
    def pay(
        self,
        invoice: FeeInvoice,
        amount: Decimal | None = None,
        method: str = Payment.METHOD_OTHER,
        reference: str = "",
    ) -> FeeInvoice:
        """Record a payment against ``invoice`` and mark it paid.

        Amount defaults to the invoice's full amount. Runs in a transaction so
        the Payment insert and the invoice status update commit together; both
        the payment and the invoice change are audited and the cache invalidated.
        """
        pay_amount = Decimal(amount) if amount is not None else invoice.amount
        now = timezone.now()
        actor = self._actor_or_none()

        with transaction.atomic():
            payment = self.payments.create(
                invoice=invoice,
                amount=pay_amount,
                method=method,
                paid_at=now,
                reference=reference,
                created_by=actor,
                updated_by=actor,
            )

            paid_total = self.payments.paid_total(invoice.id)
            status = self._derive_status(invoice, paid_total)
            invoice = self.repository.update(
                invoice,
                status=status,
                paid_on=now if status == FeeInvoice.STATUS_PAID else invoice.paid_on,
                updated_by=actor,
            )

        # Audit both the payment and the resulting invoice change.
        self.audit(
            AuditLog.ACTION_CREATE,
            entity_id=payment.pk,
            changes={
                "type": "payment",
                "invoice_id": str(invoice.pk),
                "amount": str(pay_amount),
                "method": method,
            },
        )
        self.audit(
            AuditLog.ACTION_UPDATE,
            entity_id=invoice.pk,
            changes={"status": status},
        )
        self.invalidate_cache(invoice)
        return invoice

    # -- reporting -------------------------------------------------------
    def total_due(self, student_id=None) -> Decimal:
        return self.repository.total_due(student_id=student_id)


class PaymentService(BaseService):
    model = Payment
    repository_class = PaymentRepository
    entity_name = "Payment"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(FEES_PREFIX)
