"""Fees URLs. ``config/urls.py`` mounts this under ``/api/v1/`` so the router
paths resolve to ``/api/v1/fees/``, ``/api/v1/fees/total-due/``,
``/api/v1/fees/{id}/pay/`` and ``/api/v1/fees/{id}/``.

The router registers the list-route ``total-due`` action ahead of the ``{pk}``
detail route, so ``/fees/total-due/`` never collides with a UUID lookup.
"""
from rest_framework.routers import DefaultRouter

from fees.views import FeeInvoiceViewSet

app_name = "fees"

router = DefaultRouter()
router.register("fees", FeeInvoiceViewSet, basename="fee")

urlpatterns = router.urls
