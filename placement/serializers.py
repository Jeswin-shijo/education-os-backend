"""I/O serializers for the placement app.

Two flavours per resource:

* CRUD serializers (``*Serializer``) — used by the admin management viewset;
  accept/return the full model fields.
* App-shaped serializers (``*AppSerializer``) — emit the exact camelCase shape
  the mobile app expects (``types.ts`` ``PlacementOpening``) for the
  ``GET /placements`` read.
"""
from rest_framework import serializers

from placement.models import PlacementApplication, PlacementOpening


# --- CRUD serializers (admin console) ----------------------------------------
class PlacementOpeningSerializer(serializers.ModelSerializer):
    """Full opening record for admin CRUD."""

    class Meta:
        model = PlacementOpening
        fields = [
            "id",
            "company",
            "role",
            "ctc",
            "location",
            "eligibility",
            "last_date",
            "logo_color",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class PlacementApplicationSerializer(serializers.ModelSerializer):
    """Full application record for admin management (status updates etc.)."""

    studentName = serializers.CharField(source="student.full_name", read_only=True)
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    company_role = serializers.SerializerMethodField()

    class Meta:
        model = PlacementApplication
        fields = [
            "id",
            "opening",
            "company_role",
            "student",
            "studentName",
            "student_name",
            "status",
            "applied_on",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "company_role",
            "studentName",
            "student_name",
            "applied_on",
            "created_at",
            "updated_at",
        ]

    def get_company_role(self, obj):
        if not getattr(obj, "opening_id", None):
            return ""
        opening = obj.opening
        return f"{opening.company} - {opening.role}"


# --- App-shaped serializers (mobile contract: types.ts) ----------------------
class PlacementOpeningAppSerializer(serializers.ModelSerializer):
    """Matches ``types.ts`` ``PlacementOpening``:
    ``{id, company, role, ctc, location, eligibility, lastDate, logoColor,
    applied}``.

    ``applied`` is per-student and derived from ``context['applied_ids']`` — the
    set of opening ids the requesting student has applied to.
    """

    id = serializers.CharField(read_only=True)
    ctc = serializers.FloatField(read_only=True)
    lastDate = serializers.DateField(source="last_date", read_only=True)
    logoColor = serializers.CharField(source="logo_color", read_only=True)
    applied = serializers.SerializerMethodField()

    class Meta:
        model = PlacementOpening
        fields = [
            "id",
            "company",
            "role",
            "ctc",
            "location",
            "eligibility",
            "lastDate",
            "logoColor",
            "applied",
        ]

    def get_applied(self, obj) -> bool:
        applied_ids = self.context.get("applied_ids") or set()
        return obj.id in applied_ids


class PlacementApplicationAppSerializer(serializers.ModelSerializer):
    """App-shaped own-application row for ``GET /placements/applications``.

    Embeds the opening it targets so the app can render the application list
    without a second fetch.
    """

    id = serializers.CharField(read_only=True)
    openingId = serializers.CharField(source="opening_id", read_only=True)
    company = serializers.CharField(source="opening.company", read_only=True)
    role = serializers.CharField(source="opening.role", read_only=True)
    ctc = serializers.FloatField(source="opening.ctc", read_only=True)
    logoColor = serializers.CharField(source="opening.logo_color", read_only=True)
    appliedOn = serializers.DateField(source="applied_on", read_only=True)

    class Meta:
        model = PlacementApplication
        fields = [
            "id",
            "openingId",
            "company",
            "role",
            "ctc",
            "logoColor",
            "status",
            "appliedOn",
        ]


class PlacementStatsSerializer(serializers.Serializer):
    """Placement stats rollup (``types.ts`` ``PlacementSummary`` + counts).

    Emitted by the admin ``stats`` action.
    """

    placed = serializers.IntegerField()
    eligible = serializers.IntegerField()
    avgCtcLpa = serializers.FloatField()
    highestCtcLpa = serializers.FloatField()
    topRecruiters = serializers.ListField(child=serializers.CharField())
    openings = serializers.IntegerField()
    activeOpenings = serializers.IntegerField()
    totalApplications = serializers.IntegerField()
    byStatus = serializers.DictField(child=serializers.IntegerField())
