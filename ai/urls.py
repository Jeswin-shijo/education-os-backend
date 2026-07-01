"""AI URLs. ``config/urls.py`` mounts this under ``/api/v1/`` so the paths
resolve to ``/api/v1/ai/...``.

The endpoints are feature-keyed and non-CRUD, so instead of a router we bind the
:class:`ai.views.AIViewSet` actions explicitly. Ordering matters: the more
specific ``threads/<feature>/messages`` route is declared before the shorter
``threads/<feature>`` so it wins the match.
"""
from django.urls import path

from ai.views import AIViewSet

app_name = "ai"

# Feature keys are lowercase words; keep the converter simple/greedy-safe.
FEATURE = "<str:feature>"

urlpatterns = [
    # GET /ai/threads
    path("ai/threads", AIViewSet.as_view({"get": "threads"}), name="threads"),
    # POST /ai/threads/{feature}/messages  (before the shorter thread route)
    path(
        f"ai/threads/{FEATURE}/messages",
        AIViewSet.as_view({"post": "send_message"}),
        name="thread-messages",
    ),
    # GET /ai/threads/{feature}
    path(
        f"ai/threads/{FEATURE}",
        AIViewSet.as_view({"get": "thread_by_feature"}),
        name="thread-by-feature",
    ),
    # GET /ai/suggestions/{feature}
    path(
        f"ai/suggestions/{FEATURE}",
        AIViewSet.as_view({"get": "suggestions"}),
        name="suggestions",
    ),
    # POST /ai/{feature}/respond
    path(
        f"ai/{FEATURE}/respond",
        AIViewSet.as_view({"post": "respond"}),
        name="respond",
    ),
]
