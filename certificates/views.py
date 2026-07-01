"""HTTP layer for the certificates app.

``CertificateViewSet`` serves two audiences:

* the mobile app's ``GET /certificates`` (the requesting student's own
  certificates) via the ``mine`` custom action, and
* admins' full issue/CRUD over the certificate table via the standard
  ModelViewSet actions.

All writes flow through :class:`CertificateService` (audit + cache-invalidate).
"""
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import NotFound
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from core.viewsets import BaseModelViewSet

from certificates.models import Certificate
from certificates.permissions import CERTIFICATE_MATRIX
from certificates.serializers import (
    CertificateAppSerializer,
    CertificateSerializer,
)
from certificates.services import CertificateService
from students.models import Student


class CertificateViewSet(BaseModelViewSet):
    queryset = Certificate.objects.select_related("student").all()
    serializer_class = CertificateSerializer
    service_class = CertificateService
    permission_matrix = CERTIFICATE_MATRIX
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["student", "kind", "issuer"]
    search_fields = ["title", "issuer"]
    ordering_fields = ["issued_on", "title", "created_at"]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    # -- GET /certificates (requesting student's own certificates) --------
    def _resolve_student(self, request):
        """The Student profile linked to the requesting user (or 404)."""
        student = Student.objects.filter(user=request.user).first()
        if student is None:
            raise NotFound("No student profile is linked to this account.")
        return student

    @extend_schema(responses={200: CertificateAppSerializer(many=True)})
    def mine(self, request):
        student = self._resolve_student(request)
        qs = (
            Certificate.objects.filter(student=student)
            .order_by("-issued_on", "-created_at")
        )
        return Response(
            CertificateAppSerializer(
                qs, many=True, context={"request": request}
            ).data
        )
