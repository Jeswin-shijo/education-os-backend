"""I/O serializers for the guardians app.

Two flavours:

* CRUD serializer (``ParentLinkSerializer``) — used by the admin management
  viewset; accepts/returns the ``parent``/``student`` FK ids plus ``relation``
  and denormalises the parent name/email and student roll/name read-only for
  convenience.
* App-shaped serializer (``ParentChildSerializer``) — emits the mobile app's
  ``Student`` shape (``types.ts``) for ``GET /parent/children`` by reusing the
  students app's ``StudentAppSerializer`` and attaching the ``relation`` from
  the link.
"""
from rest_framework import serializers

from students.serializers import StudentAppSerializer

from guardians.models import ParentLink


# --- CRUD serializer (admin console) -----------------------------------------
class ParentLinkSerializer(serializers.ModelSerializer):
    """Admin CRUD serializer for a parent↔student link."""

    parent_name = serializers.CharField(source="parent.full_name", read_only=True)
    parent_email = serializers.CharField(source="parent.email", read_only=True)
    student_roll_no = serializers.CharField(
        source="student.roll_no", read_only=True
    )
    student_name = serializers.CharField(
        source="student.full_name", read_only=True
    )

    class Meta:
        model = ParentLink
        fields = [
            "id",
            "parent",
            "parent_name",
            "parent_email",
            "student",
            "student_roll_no",
            "student_name",
            "relation",
            "is_primary",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        """Reject a duplicate live link for the same (parent, student) pair."""
        parent = attrs.get("parent") or getattr(self.instance, "parent", None)
        student = attrs.get("student") or getattr(self.instance, "student", None)
        if parent and student:
            qs = ParentLink.objects.filter(parent=parent, student=student)
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    "This parent is already linked to this student."
                )
        return attrs

    def validate_parent(self, value):
        from core.permissions import Role

        if value.role != Role.PARENT:
            raise serializers.ValidationError(
                "Linked user must have the 'parent' role."
            )
        return value


# --- App-shaped serializer (mobile contract) ---------------------------------
class ParentChildSerializer(StudentAppSerializer):
    """The app's ``Student`` shape plus the guardian ``relation``.

    Instantiated with a :class:`~guardians.models.ParentLink` instance; the base
    serializer reads the nested ``student``.
    """

    relation = serializers.SerializerMethodField()

    class Meta(StudentAppSerializer.Meta):
        fields = StudentAppSerializer.Meta.fields + ["relation"]

    def __init__(self, instance=None, **kwargs):
        # Accept a ParentLink and serialize its student, remembering the relation.
        self._relation = getattr(instance, "relation", "") if instance else ""
        student = getattr(instance, "student", instance)
        super().__init__(student, **kwargs)

    def get_relation(self, obj) -> str:
        return self._relation
