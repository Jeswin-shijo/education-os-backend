"""Celery tasks for the transport app.

Transport route/live reads are cached (TTL 600s). This task lets an operator
proactively bust those caches (e.g. after a bulk route import or an out-of-band
live-status update) so the next reads recompute fresh. The realtime WebSocket
consumer added later will push live updates directly; this is a REST-side helper.
"""
from celery import shared_task

from core.cache import invalidate_prefix

from transport.services import TRANSPORT_PREFIX


@shared_task(name="transport.warm_transport_cache")
def warm_transport_cache():
    """Bust the transport cache so the next route/live reads recompute fresh."""
    invalidate_prefix(TRANSPORT_PREFIX)
    return {"invalidated": [TRANSPORT_PREFIX]}
