"""Envelope exception handler.

Runs DRF's default handler, then reshapes any error response into the standard
envelope ``{success:false, message, data:null, errors:[...], meta:{}}`` while
preserving the original HTTP status code.
"""
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import status as http_status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


def _flatten_errors(detail) -> list:
    """Turn a DRF error detail structure into a flat list of error objects."""
    errors: list = []

    if isinstance(detail, dict):
        for field, messages in detail.items():
            if isinstance(messages, (list, tuple)):
                for msg in messages:
                    if isinstance(msg, (dict, list)):
                        errors.extend(_flatten_errors(msg))
                    else:
                        errors.append({"field": field, "message": str(msg)})
            elif isinstance(messages, dict):
                nested = _flatten_errors(messages)
                for item in nested:
                    item["field"] = f"{field}.{item.get('field', '')}".rstrip(".")
                    errors.append(item)
            else:
                errors.append({"field": field, "message": str(messages)})
    elif isinstance(detail, (list, tuple)):
        for msg in detail:
            if isinstance(msg, (dict, list)):
                errors.extend(_flatten_errors(msg))
            else:
                errors.append({"field": None, "message": str(msg)})
    else:
        errors.append({"field": None, "message": str(detail)})

    return errors


def _primary_message(errors: list, default: str) -> str:
    if errors:
        first = errors[0]
        return first.get("message") or default
    return default


def envelope_exception_handler(exc, context):
    """DRF ``EXCEPTION_HANDLER`` producing the standard error envelope."""
    # Normalize a couple of Django-native exceptions DRF doesn't handle by default.
    if isinstance(exc, Http404):
        exc = APIException(detail="Not found.")
        exc.status_code = http_status.HTTP_404_NOT_FOUND
    elif isinstance(exc, DjangoPermissionDenied):
        exc = APIException(detail="Permission denied.")
        exc.status_code = http_status.HTTP_403_FORBIDDEN

    response = drf_exception_handler(exc, context)

    if response is None:
        # Unhandled exception -> generic 500 envelope.
        return Response(
            {
                "success": False,
                "message": "Internal server error.",
                "data": None,
                "errors": [{"field": None, "message": "Internal server error."}],
                "meta": {},
            },
            status=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    detail = response.data
    errors = _flatten_errors(detail)
    message = _primary_message(errors, _default_message(response.status_code))

    response.data = {
        "success": False,
        "message": message,
        "data": None,
        "errors": errors,
        "meta": {},
    }
    return response


def _default_message(status_code: int) -> str:
    mapping = {
        400: "Validation failed.",
        401: "Authentication required.",
        403: "Permission denied.",
        404: "Not found.",
        405: "Method not allowed.",
        429: "Too many requests.",
    }
    return mapping.get(status_code, "Request failed.")
