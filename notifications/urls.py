"""Notifications URLs. ``config/urls.py`` mounts this under ``/api/v1/`` so the
router paths resolve to ``/api/v1/notifications/``,
``/api/v1/notifications/{id}/read/``, ``/api/v1/notifications/read-all/``,
``/api/v1/notifications/unread-count/``, ``/api/v1/notifications/broadcast/``.
"""
from rest_framework.routers import DefaultRouter

from notifications.views import NotificationViewSet

app_name = "notifications"

router = DefaultRouter()
router.register("notifications", NotificationViewSet, basename="notification")

urlpatterns = router.urls
