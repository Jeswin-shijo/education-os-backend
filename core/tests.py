"""Smoke tests for core primitives (envelope, pagination meta, cache helpers)."""
from django.test import TestCase

from core.cache import cache_get_or_set, cache_key, invalidate
from core.renderers import EnvelopeJSONRenderer


class CacheHelperTests(TestCase):
    def test_cache_key_joins_parts(self):
        self.assertEqual(cache_key("dashboard", "student", "42"), "dashboard:student:42")

    def test_get_or_set_computes_once(self):
        calls = {"n": 0}

        def producer():
            calls["n"] += 1
            return "value"

        key = cache_key("test", "once")
        self.assertEqual(cache_get_or_set(key, 60, producer), "value")
        self.assertEqual(cache_get_or_set(key, 60, producer), "value")
        self.assertEqual(calls["n"], 1)
        invalidate(key)


class EnvelopeRendererTests(TestCase):
    def _render(self, data, status_code=200):
        renderer = EnvelopeJSONRenderer()

        class _Resp:
            pass

        resp = _Resp()
        resp.status_code = status_code
        return renderer._build_envelope(data, status_code, {"response": resp})

    def test_wraps_success(self):
        env = self._render({"x": 1})
        self.assertTrue(env["success"])
        self.assertEqual(env["data"], {"x": 1})
        self.assertEqual(env["errors"], [])

    def test_lifts_pagination_into_meta(self):
        env = self._render({"results": [1, 2], "pagination": {"count": 2}})
        self.assertEqual(env["data"], [1, 2])
        self.assertEqual(env["meta"]["pagination"], {"count": 2})
