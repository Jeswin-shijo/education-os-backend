"""Celery tasks for the academics app.

Timetable and subject reads are cached (TTL 3600s). This task lets an operator
proactively rebuild/warm those caches (e.g. after a bulk import) instead of
paying the first-request cost. It is intentionally light — the source of truth is
always the DB and the service layer already invalidates on writes.
"""
from celery import shared_task

from core.cache import invalidate_prefix

from academics.services import SUBJECTS_PREFIX, TIMETABLE_PREFIX


@shared_task(name="academics.warm_timetable_cache")
def warm_timetable_cache():
    """Bust the timetable/subject caches so the next reads recompute fresh."""
    invalidate_prefix(TIMETABLE_PREFIX)
    invalidate_prefix(SUBJECTS_PREFIX)
    return {"invalidated": [TIMETABLE_PREFIX, SUBJECTS_PREFIX]}
