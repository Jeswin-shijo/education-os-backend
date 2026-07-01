from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from django.views.generic import RedirectView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView


def health(request):
    """Liveness probe — plain JSON, no auth, no envelope."""
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    # --- API v1 ---
    path("api/v1/auth/", include("accounts.urls")),
    path("api/v1/", include("academics.urls")),
    path("api/v1/", include("students.urls")),
    path("api/v1/", include("faculty.urls")),
    path("api/v1/", include("guardians.urls")),
    path("api/v1/", include("attendance.urls")),
    path("api/v1/", include("assignments.urls")),
    path("api/v1/", include("exams.urls")),
    path("api/v1/", include("fees.urls")),
    path("api/v1/", include("library.urls")),
    path("api/v1/", include("hostel.urls")),
    path("api/v1/", include("transport.urls")),
    path("api/v1/", include("materials.urls")),
    path("api/v1/", include("quizzes.urls")),
    path("api/v1/", include("placement.urls")),
    path("api/v1/", include("notifications.urls")),
    path("api/v1/", include("events.urls")),
    path("api/v1/", include("complaints.urls")),
    path("api/v1/", include("leave.urls")),
    path("api/v1/", include("certificates.urls")),
    path("api/v1/", include("chat.urls")),
    path("api/v1/", include("ai.urls")),
    path("api/v1/", include("analytics.urls")),
    path("api/v1/", include("dashboards.urls")),
    path("api/v1/", include("administration.urls")),
    # --- OpenAPI schema & docs ---
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    # --- Ops ---
    path("health/", health, name="health"),
    # Root -> interactive docs.
    path("", RedirectView.as_view(pattern_name="swagger-ui", permanent=False)),
]
