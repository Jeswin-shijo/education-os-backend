"""Fees domain models.

A :class:`FeeInvoice` is a billable charge raised against a
:class:`students.Student` (tuition/hostel/exam fees for a term). One or more
:class:`Payment` rows record money received against an invoice; when the paid
total covers the amount the service marks the invoice ``paid`` and stamps
``paid_on``.

Both models extend :class:`core.models.BaseModel` (UUID PK, audit fields,
soft-delete). Money is stored as :class:`~decimal.Decimal` — never float.
"""
from django.db import models

from core.models import BaseModel


class FeeInvoice(BaseModel):
    """A fee charge against a student (mirrors ``types.ts`` ``FeeInvoice``).

    ``status`` is derived by the service on write (``paid`` once payments cover
    the amount; ``overdue`` past ``due_date`` while unpaid) but is stored so the
    list endpoint can serve/filter it directly.
    """

    STATUS_PAID = "paid"
    STATUS_DUE = "due"
    STATUS_OVERDUE = "overdue"
    STATUS_CHOICES = [
        (STATUS_PAID, "Paid"),
        (STATUS_DUE, "Due"),
        (STATUS_OVERDUE, "Overdue"),
    ]

    student = models.ForeignKey(
        "students.Student",
        on_delete=models.CASCADE,
        related_name="fee_invoices",
    )
    title = models.CharField(max_length=255)
    term = models.CharField(max_length=64, blank=True, default="", db_index=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_DUE,
        db_index=True,
    )
    paid_on = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["due_date", "-created_at"]
        verbose_name = "Fee invoice"
        verbose_name_plural = "Fee invoices"
        indexes = [
            models.Index(fields=["student", "status"]),
            models.Index(fields=["status", "due_date"]),
        ]

    def __str__(self):
        return f"{self.title} — {self.amount} ({self.status})"


class Payment(BaseModel):
    """A payment received against a :class:`FeeInvoice`."""

    METHOD_CARD = "card"
    METHOD_UPI = "upi"
    METHOD_NETBANKING = "netbanking"
    METHOD_CASH = "cash"
    METHOD_CHEQUE = "cheque"
    METHOD_OTHER = "other"
    METHOD_CHOICES = [
        (METHOD_CARD, "Card"),
        (METHOD_UPI, "UPI"),
        (METHOD_NETBANKING, "Net banking"),
        (METHOD_CASH, "Cash"),
        (METHOD_CHEQUE, "Cheque"),
        (METHOD_OTHER, "Other"),
    ]

    invoice = models.ForeignKey(
        FeeInvoice,
        on_delete=models.CASCADE,
        related_name="payments",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(
        max_length=16, choices=METHOD_CHOICES, default=METHOD_OTHER
    )
    paid_at = models.DateTimeField(db_index=True)
    reference = models.CharField(max_length=128, blank=True, default="")

    class Meta:
        ordering = ["-paid_at"]
        verbose_name = "Payment"
        verbose_name_plural = "Payments"
        indexes = [
            models.Index(fields=["invoice", "paid_at"]),
        ]

    def __str__(self):
        return f"{self.amount} for invoice {self.invoice_id}"
