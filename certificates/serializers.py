"""I/O serializers for the certificates app.

Two flavours:

* :class:`CertificateSerializer` — CRUD serializer for the admin/staff console;
  accepts/returns the full model fields (``student`` FK included).
* :class:`CertificateAppSerializer` — emits the exact camelCase shape the mobile
  app expects (``types.ts`` ``Certificate``: ``{id, title, issuer, issuedOn,
  kind}``, plus ``file``/``url`` so the app can open the artifact) for
  ``GET /certificates``.
"""
from rest_framework import serializers

from certificates.models import Certificate


class CertificateSerializer(serializers.ModelSerializer):
    """Full record used by the admin issue/CRUD viewset."""

    class Meta:
        model = Certificate
        fields = [
            "id",
            "student",
            "title",
            "issuer",
            "issued_on",
            "kind",
            "file",
            "url",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class CertificateAppSerializer(serializers.ModelSerializer):
    """Matches ``types.ts`` ``Certificate`` (camelCase) + artifact links."""

    id = serializers.CharField(read_only=True)
    issuedOn = serializers.DateField(source="issued_on", read_only=True)
    fileUrl = serializers.SerializerMethodField()

    class Meta:
        model = Certificate
        fields = ["id", "title", "issuer", "issuedOn", "kind", "url", "fileUrl"]

    def get_fileUrl(self, obj):
        if not obj.file:
            return None
        request = self.context.get("request")
        url = obj.file.url
        return request.build_absolute_uri(url) if request else url
