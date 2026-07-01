"""Celery tasks for the attendance app.

Attendance take is synchronous (a faculty saves a session inline), so there are
no request-blocking long jobs here today. This module hosts optional background
work such as low-attendance reminder notifications, kept thin and idempotent so
it can be scheduled via ``django-celery-beat`` later.
"""
from __future__ import annotations

from celery import shared_task

from core.cache import invalidate_prefix

from attendance.services import ATTENDANCE_PREFIX


@shared_task(name="attendance.invalidate_cache")
def invalidate_attendance_cache() -> str:
    """Bust all cached attendance views (e.g. after a bulk import)."""
    invalidate_prefix(ATTENDANCE_PREFIX)
    return "attendance cache invalidated"
