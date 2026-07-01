"""I/O serializers for the fees app.

* ``FeeInvoiceSerializer`` — app-shaped (camelCase) output matching ``types.ts``
  ``FeeInvoice`` (``{id, title, term, amount, dueDate, status, paidOn}``), used
  by the list and pay endpoints. Writable fields back the admin create/update.
* ``PaymentSerializer`` — reads a recorded payment.
* ``PayInputSerializer`` / ``TotalDueSerializer`` — request/response shapes for
  the ``pay`` and ``total-due`` custom actions.
"""
from decimal import Decimal

from rest_framework import serializers

from fees.models import FeeInvoice, Payment


class FeeInvoiceSerializer(serializers.ModelSerializer):
    """Matches ``types.ts`` ``FeeInvoice`` (camelCase); amount as a number."""

    id = serializers.CharField(read_only=True)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    dueDate = serializers.DateField(source="due_date", required=False, allow_null=True)
    paidOn = serializers.DateTimeField(source="paid_on", read_only=True)

    class Meta:
        model = FeeInvoice
        fields = [
            "id",
            "student",
            "title",
            "term",
            "amount",
            "dueDate",
            "status",
            "paidOn",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "status", "paidOn", "created_at", "updated_at"]


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = [
            "id",
            "invoice",
            "amount",
            "method",
            "paid_at",
            "reference",
            "created_at",
        ]
        read_only_fields = ["id", "paid_at", "created_at"]


class PayInputSerializer(serializers.Serializer):
    """Optional body for ``POST /fees/{id}/pay``.

    The mobile app sends no body (pays the full invoice amount); admins/parents
    may optionally specify a partial ``amount``, ``method`` and ``reference``.
    """

    amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, min_value=Decimal("0.01")
    )
    method = serializers.ChoiceField(
        choices=Payment.METHOD_CHOICES, required=False, default=Payment.METHOD_OTHER
    )
    reference = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=128
    )


class TotalDueSerializer(serializers.Serializer):
    """Response shape for ``GET /fees/total-due`` → ``{ total }``."""

    total = serializers.DecimalField(max_digits=14, decimal_places=2)
