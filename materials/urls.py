"""Materials URLs. ``config/urls.py`` mounts this under ``/api/v1/`` so the
router paths resolve to ``/api/v1/materials/``, ``/api/v1/materials/{id}/``, and
``/api/v1/materials/faculty/``.
"""
from rest_framework.routers import DefaultRouter

from materials.views import MaterialViewSet

app_name = "materials"

router = DefaultRouter()
router.register("materials", MaterialViewSet, basename="materials")

urlpatterns = router.urls
