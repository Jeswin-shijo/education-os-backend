"""Events URLs. ``config/urls.py`` mounts this under ``/api/v1/`` so the paths
resolve to:

* ``GET  /api/v1/events``                    — app-shaped event list
* ``POST /api/v1/events/{id}/register``      — toggle the requesting user's registration
* ``GET/POST/PATCH/DELETE /api/v1/events-admin/…`` — admin event CRUD

The app-facing ``events`` list and ``register`` toggle are bound as explicit
routes so their paths match the mobile contract exactly; the admin CRUD resource
lives under a distinct basename to avoid colliding with those fixed paths.
"""
from django.urls import path
from rest_framework.routers import DefaultRouter

from events.views import EventViewSet

app_name = "events"

router = DefaultRouter()
router.register("events-admin", EventViewSet, basename="event-admin")

urlpatterns = [
    path(
        "events",
        EventViewSet.as_view({"get": "events"}),
        name="event-list",
    ),
    path(
        "events/<uuid:pk>/register",
        EventViewSet.as_view({"post": "register"}),
        name="event-register",
    ),
    *router.urls,
]
