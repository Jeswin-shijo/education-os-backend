"""I/O serializers for the complaints app.

Flavours:

* ``ComplaintSerializer`` — emits the exact ``types.ts`` ``Complaint`` shape
  (camelCase: ``createdOn``) for ``GET /complaints`` and the monitor view; the
  owner ``user`` is set from the request, never the client, so the read fields
  ``id``/``status``/``createdOn`` are read-only.
* ``ComplaintCreateSerializer`` — the ``POST /complaints`` body
  (``ComplaintInput`` = ``{category, subject, description}``).
* ``ComplaintStatusSerializer`` — the ``PATCH /complaints/{id}`` body (staff
  status-workflow transition); validates the target status.
* ``ComplaintMonitorSerializer`` — the Principal/Admin monitor envelope
  (all complaints + status counts).
"""
from rest_framework import serializers

from complaints.models import Complaint


class ComplaintSerializer(serializers.ModelSerializer):
    """Matches ``types.ts`` ``Complaint`` (camelCase read shape)."""

    id = serializers.CharField(read_only=True)
    createdOn = serializers.DateTimeField(source="created_on", read_only=True)

    class Meta:
        model = Complaint
        fields = ["id", "category", "subject", "description", "status", "createdOn"]
        read_only_fields = ["id", "status", "createdOn"]


class ComplaintCreateSerializer(serializers.ModelSerializer):
    """``POST /complaints`` body — ``ComplaintInput`` (category/subject/description)."""

    class Meta:
        model = Complaint
        fields = ["category", "subject", "description"]

    def validate_category(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Category is required.")
        return value

    def validate_subject(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Subject is required.")
        return value

    def validate_description(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Description is required.")
        return value


class ComplaintStatusSerializer(serializers.Serializer):
    """``PATCH /complaints/{id}`` body — staff status transition."""

    status = serializers.ChoiceField(choices=Complaint.STATUS_CHOICES)


class ComplaintMonitorSerializer(serializers.Serializer):
    """Principal/Admin monitor envelope: all complaints + status counts.

    Mirrors the app's ``PrincipalComplaintMonitoring`` shape (``total`` /
    ``byStatus`` / ``recent``); ``complaints`` carries the full (paginated) list.
    """

    total = serializers.IntegerField()
    byStatus = serializers.ListField(child=serializers.DictField())
    complaints = ComplaintSerializer(many=True)
