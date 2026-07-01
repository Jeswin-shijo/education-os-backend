"""Response envelope renderer.

Wraps every successful response body in the standard envelope
``{success, message, data, errors, meta}``. Paginated payloads (from
:class:`core.pagination.StandardPagination`) have their pagination block lifted
into ``meta``. Already-enveloped payloads and error bodies (shaped by
:func:`core.exceptions.envelope_exception_handler`) pass through untouched.
"""
from rest_framework.renderers import JSONRenderer

ENVELOPE_KEYS = {"success", "message", "data", "errors", "meta"}


class EnvelopeJSONRenderer(JSONRenderer):
    """DRF renderer that emits the standard response envelope."""

    def render(self, data, accepted_media_type=None, renderer_context=None):
        renderer_context = renderer_context or {}
        response = renderer_context.get("response")
        status_code = getattr(response, "status_code", 200)

        payload = self._build_envelope(data, status_code, renderer_context)
        return super().render(payload, accepted_media_type, renderer_context)

    # ------------------------------------------------------------------
    def _build_envelope(self, data, status_code, renderer_context):
        # Pass through if already an envelope (e.g. from the exception handler
        # or a view that built one deliberately).
        if isinstance(data, dict) and ENVELOPE_KEYS.issubset(data.keys()):
            return data

        success = status_code < 400
        meta: dict = {}
        errors: list = []

        # Lift pagination info emitted by StandardPagination into meta.
        if isinstance(data, dict) and "results" in data and "pagination" in data:
            meta["pagination"] = data.get("pagination")
            data = data.get("results")

        if not success:
            # Errors are normally shaped by the exception handler; this is a
            # fallback for raw error bodies that reach the renderer.
            errors = self._coerce_errors(data)
            return {
                "success": False,
                "message": self._default_message(status_code),
                "data": None,
                "errors": errors,
                "meta": meta,
            }

        message = self._default_message(status_code)
        if isinstance(data, dict) and "detail" in data and len(data) == 1:
            message = str(data["detail"])
            data = None

        return {
            "success": True,
            "message": message,
            "data": data,
            "errors": errors,
            "meta": meta,
        }

    @staticmethod
    def _coerce_errors(data):
        if data is None:
            return []
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [{"field": k, "messages": v if isinstance(v, list) else [v]} for k, v in data.items()]
        return [{"detail": str(data)}]

    @staticmethod
    def _default_message(status_code):
        if 200 <= status_code < 300:
            return "Success"
        if 400 <= status_code < 500:
            return "Request failed"
        return "Server error"
