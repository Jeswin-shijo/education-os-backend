"""Optional base viewset that wires service + repository + envelope + RBAC so
domain modules stay thin. Modules may subclass this or roll their own using the
core primitives directly."""
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from core.permissions import RoleModelPermission


class BaseModelViewSet(viewsets.ModelViewSet):
    """ModelViewSet pre-wired for AI Campus OS conventions.

    Subclasses set ``queryset``/``serializer_class`` and optionally
    ``service_class`` and ``permission_matrix``. Writes flow through the service
    so audit + cache-invalidation happen automatically; the standard pagination
    and envelope renderer are applied globally via settings.
    """

    permission_classes = [IsAuthenticated, RoleModelPermission]
    service_class = None
    permission_matrix: dict = {}

    def get_service(self):
        if self.service_class is None:
            return None
        return self.service_class(
            actor=self.request.user,
            ip=self._client_ip(),
        )

    def _client_ip(self):
        xff = self.request.META.get("HTTP_X_FORWARDED_FOR")
        if xff:
            return xff.split(",")[0].strip()
        return self.request.META.get("REMOTE_ADDR")

    # -- service-backed writes -------------------------------------------
    def perform_create(self, serializer):
        service = self.get_service()
        if service is None:
            return super().perform_create(serializer)
        instance = service.create(**serializer.validated_data)
        serializer.instance = instance

    def perform_update(self, serializer):
        service = self.get_service()
        if service is None:
            return super().perform_update(serializer)
        instance = service.update(serializer.instance, **serializer.validated_data)
        serializer.instance = instance

    def perform_destroy(self, instance):
        service = self.get_service()
        if service is None:
            return super().perform_destroy(instance)
        service.delete(instance)
