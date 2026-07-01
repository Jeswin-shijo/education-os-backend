"""Certificate URLs. ``config/urls.py`` mounts this under ``/api/v1/`` so the
paths resolve to:

* ``GET  /api/v1/certificates``                      — requesting student's own
  certificates (mobile contract, app-shaped)
* ``GET/POST/PATCH/DELETE /api/v1/certificates-admin/…`` — admin issue/CRUD

The app-facing read is bound as an explicit collection route so its path matches
the mobile contract exactly; the admin CRUD resource lives under a distinct
basename to avoid colliding with that fixed path.
"""
from django.urls import path
from rest_framework.routers import DefaultRouter

from certificates.views import CertificateViewSet

app_name = "certificates"

router = DefaultRouter()
router.register("certificates-admin", CertificateViewSet, basename="certificate")

urlpatterns = [
    path(
        "certificates",
        CertificateViewSet.as_view({"get": "mine"}),
        name="certificate-mine",
    ),
    *router.urls,
]
