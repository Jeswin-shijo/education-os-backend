"""Chat URLs. ``config/urls.py`` mounts this under ``/api/v1/`` so the router
paths resolve to:

- ``/api/v1/chat/threads/``               (list)
- ``/api/v1/chat/threads/{id}/``          (retrieve)
- ``/api/v1/chat/threads/{id}/messages/`` (POST send)
- ``/api/v1/chat/threads/{id}/read/``     (POST mark-read)
"""
from rest_framework.routers import DefaultRouter

from chat.views import ChatThreadViewSet

app_name = "chat"

router = DefaultRouter()
router.register("chat/threads", ChatThreadViewSet, basename="chat-threads")

urlpatterns = router.urls
