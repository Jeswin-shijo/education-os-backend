"""I/O serializers for the leave app.

* ``LeaveRequestSerializer`` — emits the mobile ``types.ts`` ``LeaveRequest``
  shape (camelCase: ``from``/``to``/``appliedOn``) for reads. ``from`` is a
  Python keyword, so it is declared via ``serializers.DateField`` bound to the
  model ``start_date`` and named through ``Meta.extra_kwargs``-style field maps.
* ``LeaveInputSerializer`` — validates the ``POST /leaves`` apply body
  (``{ type, from, to, reason }``) matching the app's ``LeaveInput``.
"""
from rest_framework import serializers

from leave.models import LeaveRequest


class LeaveRequestSerializer(serializers.ModelSerializer):
    """Read serializer matching ``types.ts`` ``LeaveRequest`` (camelCase)."""

    id = serializers.CharField(read_only=True)
    student = serializers.CharField(source="user_id", read_only=True)
    studentName = serializers.CharField(source="user.full_name", read_only=True)
    student_name = serializers.CharField(source="user.full_name", read_only=True)
    # ``from`` is a reserved word; declare the field then rename it below.
    to = serializers.DateField(source="end_date", read_only=True)
    appliedOn = serializers.DateTimeField(source="applied_on", read_only=True)

    class Meta:
        model = LeaveRequest
        fields = [
            "id",
            "student",
            "studentName",
            "student_name",
            "type",
            "to",
            "reason",
            "status",
            "appliedOn",
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Emit ``from`` (reserved keyword, can't be a field attribute name).
        data["from"] = instance.start_date.isoformat() if instance.start_date else None
        # Preserve app field order roughly (from before to).
        ordered = {
            "id": data["id"],
            "student": data["student"],
            "studentName": data["studentName"],
            "student_name": data["student_name"],
            "type": data["type"],
            "from": data["from"],
            "to": data["to"],
            "reason": data["reason"],
            "status": data["status"],
            "appliedOn": data["appliedOn"],
        }
        return ordered


class LeaveSpecSerializer(serializers.ModelSerializer):
    """Spec (mobile API contract) read shape — snake_case.

    ``{ id, type, from_date, to_date, reason, status, applied_on }``.
    """

    id = serializers.CharField(read_only=True)
    student = serializers.CharField(source="user_id", read_only=True)
    studentName = serializers.CharField(source="user.full_name", read_only=True)
    student_name = serializers.CharField(source="user.full_name", read_only=True)
    from_date = serializers.DateField(source="start_date", read_only=True)
    to_date = serializers.DateField(source="end_date", read_only=True)
    applied_on = serializers.DateTimeField(read_only=True)

    class Meta:
        model = LeaveRequest
        fields = [
            "id",
            "student",
            "studentName",
            "student_name",
            "type",
            "from_date",
            "to_date",
            "reason",
            "status",
            "applied_on",
        ]


class LeaveSpecInputSerializer(serializers.Serializer):
    """Validates ``POST /api/v1/leaves`` (spec): ``{ type, from_date, to_date, reason }``."""

    type = serializers.ChoiceField(choices=LeaveRequest.TYPE_CHOICES)
    from_date = serializers.DateField()
    to_date = serializers.DateField()
    reason = serializers.CharField(allow_blank=True, required=False, default="")

    def validate(self, attrs):
        if attrs["to_date"] < attrs["from_date"]:
            raise serializers.ValidationError("`to_date` cannot be before `from_date`.")
        return attrs


class LeaveStatusSerializer(serializers.Serializer):
    """Validates ``PUT /api/v1/leaves/{leave_id}`` (spec): ``{ status }``."""

    status = serializers.ChoiceField(
        choices=[LeaveRequest.STATUS_APPROVED, LeaveRequest.STATUS_REJECTED]
    )


class LeaveInputSerializer(serializers.Serializer):
    """Validates ``POST /leaves`` (``LeaveInput``: type/from/to/reason)."""

    type = serializers.ChoiceField(choices=LeaveRequest.TYPE_CHOICES)
    # Accept ``from``/``to`` (mobile) with ``start_date``/``end_date`` aliases.
    from_date = serializers.DateField()
    to = serializers.DateField()
    reason = serializers.CharField(allow_blank=True, required=False, default="")

    def to_internal_value(self, data):
        # Map the app's reserved ``from`` key onto ``from_date`` before validation.
        if "from" in data and "from_date" not in data:
            data = {**data, "from_date": data["from"]}
        return super().to_internal_value(data)

    def validate(self, attrs):
        if attrs["to"] < attrs["from_date"]:
            raise serializers.ValidationError("`to` cannot be before `from`.")
        return attrs
