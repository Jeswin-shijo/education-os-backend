"""Celery tasks for the analytics app.

Analytics is read-through-cached on demand (TTL 300s), so no background work is
required for correctness. This optional task pre-warms the institution-wide
Principal caches (e.g. from a nightly ``django-celery-beat`` schedule) so the
first dashboard hit after cache expiry is instant. HOD caches are per-user/dept
and warmed lazily on access.
"""
from celery import shared_task


@shared_task(name="analytics.warm_principal_caches")
def warm_principal_caches() -> dict:
    """Recompute + cache the Principal aggregations for a system actor.

    Runs with no request user (institution scope needs none). Returns a small
    summary so the task result is inspectable.
    """
    from analytics.services import PrincipalAnalyticsService

    class _SystemActor:
        id = "system"
        full_name = "System"
        email = "system@aicampusos.dev"
        role = "principal"
        avatar_color = "#13327F"
        phone = ""

    svc = PrincipalAnalyticsService(_SystemActor())
    svc.dashboard()
    svc.student_analytics()
    svc.faculty_analytics()
    svc.fee_analytics()
    svc.placement_analytics()
    svc.complaint_monitoring()
    svc.ai_insights()
    return {"warmed": True}
