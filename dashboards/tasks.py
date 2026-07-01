"""Celery tasks for the dashboards app.

Dashboards are computed on-demand and cached with a short TTL, so there is no
required background work. This optional task lets an operator (or a source app's
signal) pre-warm or refresh a role's dashboard cache off the request path — e.g.
after a large attendance/marks import — so the next read is instant rather than
recomputed inline.
"""
from __future__ import annotations

from celery import shared_task

from dashboards.services import (
    invalidate_all_dashboards,
    invalidate_faculty_dashboard,
    invalidate_parent_dashboards,
    invalidate_student_dashboard,
)


@shared_task(name="dashboards.invalidate_student_dashboard")
def invalidate_student_dashboard_task(student_id: str) -> None:
    """Bust one student's cached dashboard (async)."""
    invalidate_student_dashboard(student_id)


@shared_task(name="dashboards.invalidate_parent_dashboards")
def invalidate_parent_dashboards_task(parent_user_ids: list[str]) -> None:
    """Bust the cached dashboards of the given parent user id(s) (async)."""
    invalidate_parent_dashboards(parent_user_ids)


@shared_task(name="dashboards.invalidate_faculty_dashboard")
def invalidate_faculty_dashboard_task(faculty_profile_id: str) -> None:
    """Bust one faculty member's cached dashboard (async)."""
    invalidate_faculty_dashboard(faculty_profile_id)


@shared_task(name="dashboards.invalidate_all_dashboards")
def invalidate_all_dashboards_task() -> None:
    """Bust every cached dashboard (async coarse signal)."""
    invalidate_all_dashboards()
