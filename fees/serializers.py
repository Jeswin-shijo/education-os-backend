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
    studentName = serializers.CharField(source="student.full_name", read_only=True)
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    dueDate = serializers.DateField(
        source="due_date",
        required=False,
        allow_null=True,
        input_formats=[
            "%Y-%m-%d",
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S",
        ],
    )
    paidOn = serializers.DateTimeField(source="paid_on", read_only=True)

    class Meta:
        model = FeeInvoice
        fields = [
            "id",
            "student",
            "studentName",
            "student_name",
            "title",
            "term",
            "amount",
            "dueDate",
            "status",
            "paidOn",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "studentName",
            "student_name",
            "status",
            "paidOn",
            "created_at",
            "updated_at",
        ]


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


# --- Mobile API contract v1 serializers (snake_case, spec-exact) -------------
class FeeInvoiceSpecSerializer(serializers.ModelSerializer):
    """Spec-exact invoice row for ``GET /api/v1/fees/{user_id}``.

    Fields match ``API_CONTRACT_V1`` exactly:
    ``{ id, title, term, amount, due_date, status, paid_on }``.
    """

    id = serializers.CharField(read_only=True)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    due_date = serializers.DateField(read_only=True, allow_null=True)
    paid_on = serializers.DateTimeField(read_only=True, allow_null=True)

    class Meta:
        model = FeeInvoice
        fields = ["id", "title", "term", "amount", "due_date", "status", "paid_on"]


class FeeSummarySpecSerializer(serializers.Serializer):
    """Response for ``GET /api/v1/fees/{user_id}`` (spec-exact envelope data)."""

    total_due = serializers.DecimalField(max_digits=14, decimal_places=2)
    paid_amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    pending_amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    invoices = FeeInvoiceSpecSerializer(many=True)


class PaymentInputSpecSerializer(serializers.Serializer):
    """Request body for ``POST /api/v1/fees/payment`` — ``{ fee_id }``.

    ``amount``/``method``/``reference`` are optional (mobile pays the full
    invoice amount with no extra body); admins may record a partial payment.
    """

    fee_id = serializers.UUIDField()
    amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, min_value=Decimal("0.01")
    )
    method = serializers.ChoiceField(
        choices=Payment.METHOD_CHOICES, required=False, default=Payment.METHOD_OTHER
    )
    reference = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=128
    )


class PaymentResultSpecSerializer(serializers.Serializer):
    """Response for ``POST /api/v1/fees/payment`` — ``{ payment_id, receipt_no }``."""

    payment_id = serializers.CharField()
    receipt_no = serializers.CharField()


class ReceiptSpecSerializer(serializers.Serializer):
    """Response for ``GET /api/v1/fees/receipt/{payment_id}`` — the receipt."""

    payment_id = serializers.CharField()
    receipt_no = serializers.CharField()
    fee_id = serializers.CharField()
    title = serializers.CharField()
    term = serializers.CharField(allow_blank=True)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    method = serializers.CharField()
    paid_at = serializers.DateTimeField()
    reference = serializers.CharField(allow_blank=True)
    student_name = serializers.CharField()
    roll_no = serializers.CharField()
