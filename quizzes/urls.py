"""Quizzes URLs. ``config/urls.py`` mounts this under ``/api/v1/`` so the router
paths resolve to ``/api/v1/quizzes/`` and ``/api/v1/quizzes/{id}/``.
"""
from rest_framework.routers import DefaultRouter

from quizzes.views import QuizViewSet

app_name = "quizzes"

router = DefaultRouter()
router.register("quizzes", QuizViewSet, basename="quizzes")

urlpatterns = router.urls
