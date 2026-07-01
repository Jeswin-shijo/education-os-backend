"""Redis cache helpers with the documented key convention and TTLs.

Key convention: ``"<entity>:<scope>:<id>"`` built via :func:`cache_key`.
Services read through :func:`cache_get_or_set` and invalidate on writes via
:func:`invalidate` / :func:`invalidate_prefix`.
"""
from __future__ import annotations

from typing import Any, Callable

from django.core.cache import cache

# --- Documented TTLs (seconds) ----------------------------------------------
TTL_DASHBOARD = 300
TTL_ANALYTICS = 300
TTL_TIMETABLE = 3600
TTL_SUBJECTS = 3600
TTL_ATTENDANCE = 300
TTL_NOTIFICATIONS = 60
TTL_LIBRARY = 600
TTL_REPORTS = 900

# Convenience lookup by domain name.
TTLS = {
    "dashboard": TTL_DASHBOARD,
    "analytics": TTL_ANALYTICS,
    "timetable": TTL_TIMETABLE,
    "subjects": TTL_SUBJECTS,
    "attendance": TTL_ATTENDANCE,
    "notifications": TTL_NOTIFICATIONS,
    "library": TTL_LIBRARY,
    "reports": TTL_REPORTS,
}

DEFAULT_TTL = 300

# Registry of key prefixes so ``invalidate_prefix`` works on any cache backend
# (LocMemCache has no key-pattern scan). Prefixed keys are tracked here.
_PREFIX_INDEX_KEY = "__prefix_index__"


def cache_key(*parts: Any) -> str:
    """Build a cache key from parts using the ``a:b:c`` convention."""
    return ":".join(str(p) for p in parts if p is not None and p != "")


def _register_prefix(key: str) -> None:
    prefix = key.split(":", 1)[0] if ":" in key else key
    index = cache.get(_PREFIX_INDEX_KEY, {})
    keys = index.get(prefix)
    if keys is None:
        keys = set()
    else:
        keys = set(keys)
    keys.add(key)
    index[prefix] = list(keys)
    cache.set(_PREFIX_INDEX_KEY, index, None)


def cache_get_or_set(key: str, ttl: int, producer: Callable[[], Any]) -> Any:
    """Return cached value for ``key`` or compute, store (with ``ttl``) and return it."""
    sentinel = object()
    value = cache.get(key, sentinel)
    if value is sentinel:
        value = producer()
        cache.set(key, value, ttl)
        _register_prefix(key)
    return value


def cache_set(key: str, value: Any, ttl: int = DEFAULT_TTL) -> None:
    cache.set(key, value, ttl)
    _register_prefix(key)


def cache_get(key: str, default: Any = None) -> Any:
    return cache.get(key, default)


def invalidate(*keys: str) -> None:
    """Delete one or more exact cache keys."""
    for key in keys:
        cache.delete(key)


def invalidate_prefix(prefix: str) -> None:
    """Delete every tracked key beginning with ``prefix``.

    Uses ``delete_pattern`` when the backend (django-redis) supports it,
    otherwise falls back to the in-process prefix index.
    """
    delete_pattern = getattr(cache, "delete_pattern", None)
    if callable(delete_pattern):
        try:
            delete_pattern(f"{prefix}*")
            return
        except Exception:  # pragma: no cover - backend without pattern support
            pass
    index = cache.get(_PREFIX_INDEX_KEY, {})
    keys = index.get(prefix, [])
    for key in keys:
        cache.delete(key)
    if prefix in index:
        del index[prefix]
        cache.set(_PREFIX_INDEX_KEY, index, None)
