"""I/O serializers for the materials app.

Flavours:

* ``MaterialSerializer`` — CRUD serializer for the faculty/admin management
  surface + the ``POST /materials`` upload-metadata body (accepts ``subject`` /
  ``faculty_class`` FK ids, ``title``, ``kind``, ``size_label``, ``file``/``url``).
* ``StudentMaterialSerializer`` — emits the exact ``types.ts`` ``Material`` shape
  (camelCase: ``subjectId``/``sizeLabel``/``addedAt``) for the student list.
* ``FacultyMaterialSerializer`` — emits ``types.ts`` ``FacultyMaterial``
  (``classId``/``addedOn``) for the faculty list.
"""
from rest_framework import serializers

from materials.models import Material


# --- CRUD / upload serializer ------------------------------------------------
class MaterialSerializer(serializers.ModelSerializer):
    """Faculty/admin CRUD + ``POST /materials`` upload-metadata serializer."""

    subject_code = serializers.CharField(source="subject.code", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)

    class Meta:
        model = Material
        fields = [
            "id",
            "subject",
            "subject_code",
            "subject_name",
            "faculty_class",
            "title",
            "kind",
            "size_label",
            "file",
            "url",
            "added_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "added_at", "created_at", "updated_at"]

    def validate(self, attrs):
        # A material must be attachable somewhere and must carry content.
        subject = attrs.get("subject", getattr(self.instance, "subject", None))
        faculty_class = attrs.get(
            "faculty_class", getattr(self.instance, "faculty_class", None)
        )
        if subject is None and faculty_class is None:
            raise serializers.ValidationError(
                "A material must reference a subject or a faculty class."
            )

        kind = attrs.get("kind", getattr(self.instance, "kind", Material.KIND_NOTE))
        file = attrs.get("file", getattr(self.instance, "file", None))
        url = attrs.get("url", getattr(self.instance, "url", ""))
        if kind == Material.KIND_LINK and not url:
            raise serializers.ValidationError(
                {"url": "A 'link' material requires a url."}
            )
        if not file and not url:
            raise serializers.ValidationError(
                "Provide a file upload or a url for the material."
            )
        return attrs


# --- App-shaped read serializers (mobile contract) ---------------------------
class StudentMaterialSerializer(serializers.ModelSerializer):
    """Matches ``types.ts`` ``Material`` (student-facing, camelCase)."""

    id = serializers.CharField(read_only=True)
    subjectId = serializers.SerializerMethodField()
    sizeLabel = serializers.CharField(source="size_label", read_only=True)
    addedAt = serializers.DateTimeField(source="added_at", read_only=True)

    class Meta:
        model = Material
        fields = ["id", "subjectId", "title", "kind", "sizeLabel", "addedAt"]

    def get_subjectId(self, obj):
        # Prefer the direct subject; fall back to the class's subject if any.
        if obj.subject_id:
            return str(obj.subject_id)
        if obj.faculty_class_id and obj.faculty_class.subject_id:
            return str(obj.faculty_class.subject_id)
        return ""


class FacultyMaterialSerializer(serializers.ModelSerializer):
    """Matches ``types.ts`` ``FacultyMaterial`` (camelCase)."""

    id = serializers.CharField(read_only=True)
    classId = serializers.SerializerMethodField()
    sizeLabel = serializers.CharField(source="size_label", read_only=True)
    addedOn = serializers.DateTimeField(source="added_at", read_only=True)

    class Meta:
        model = Material
        fields = ["id", "classId", "title", "kind", "sizeLabel", "addedOn"]

    def get_classId(self, obj):
        return str(obj.faculty_class_id) if obj.faculty_class_id else ""
