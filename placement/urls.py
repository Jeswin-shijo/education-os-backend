"""Placement URLs. ``config/urls.py`` mounts this under ``/api/v1/`` so the paths
resolve to:

* ``GET  /api/v1/placements``                    — app-shaped active openings
* ``POST /api/v1/placements/{id}/apply``         — student applies
* ``GET  /api/v1/placements/applications``       — requesting student's applications
* ``GET  /api/v1/placements/stats``              — admin/principal stats rollup
* ``GET/POST/PATCH/DELETE /api/v1/placements-admin/…`` — admin opening CRUD
* ``…/placement-applications/…``                 — admin application management

The app-facing collection reads (``applications``/``stats``) and the fixed
``{id}/apply`` route are bound as explicit paths so they match the mobile
contract exactly and never collide with the ``{id}`` detail route; the admin CRUD
resources live under distinct basenames.
"""
from django.urls import path
from rest_framework.routers import DefaultRouter

from placement.views import PlacementApplicationViewSet, PlacementOpeningViewSet

app_name = "placement"

router = DefaultRouter()
router.register("placements-admin", PlacementOpeningViewSet, basename="opening")
router.register(
    "placement-applications",
    PlacementApplicationViewSet,
    basename="application",
)

urlpatterns = [
    # Fixed collection routes first (before the {id} detail route below).
    path(
        "placements/applications",
        PlacementOpeningViewSet.as_view({"get": "applications"}),
        name="my-applications",
    ),
    path(
        "placements/stats",
        PlacementOpeningViewSet.as_view({"get": "stats"}),
        name="stats",
    ),
    path(
        "placements",
        PlacementOpeningViewSet.as_view({"get": "list"}),
        name="opening-app-list",
    ),
    path(
        "placements/<uuid:pk>",
        PlacementOpeningViewSet.as_view({"get": "retrieve"}),
        name="opening-app-detail",
    ),
    path(
        "placements/<uuid:pk>/apply",
        PlacementOpeningViewSet.as_view({"post": "apply"}),
        name="apply",
    ),
    *router.urls,
]
