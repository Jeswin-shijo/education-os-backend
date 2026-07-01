"""Background email tasks for the accounts app.

Defined as Celery tasks; if Celery isn't installed/wired yet they degrade to
plain callables so the request path and tests still work. Views/services should
enqueue via ``.delay(...)`` when a broker is available, else call directly.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)

try:  # pragma: no cover - depends on optional dependency
    from celery import shared_task
except Exception:  # pragma: no cover
    def shared_task(*dargs, **dkwargs):
        """Fallback decorator when Celery is unavailable."""

        def wrap(func):
            def _delay(*args, **kwargs):
                return func(*args, **kwargs)

            func.delay = _delay
            func.run = func
            return func

        # Support both @shared_task and @shared_task(...) usage.
        if len(dargs) == 1 and callable(dargs[0]) and not dkwargs:
            return wrap(dargs[0])
        return wrap


def _from_email() -> str:
    return getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@aicampus.os")


@shared_task(name="accounts.send_otp_email")
def send_otp_email(email: str, code: str, purpose: str = "password_reset") -> bool:
    """Email a one-time passcode to the user."""
    subject = "Your AI Campus OS verification code"
    body = (
        f"Your one-time code is: {code}\n\n"
        f"It is valid for a short time and can be used once ({purpose}).\n"
        "If you did not request this, you can ignore this email."
    )
    try:
        send_mail(subject, body, _from_email(), [email], fail_silently=True)
    except Exception:  # pragma: no cover - never block on email
        logger.exception("Failed to send OTP email to %s", email)
        return False
    return True


@shared_task(name="accounts.send_welcome_email")
def send_welcome_email(email: str, full_name: str = "") -> bool:
    """Welcome a newly registered user."""
    subject = "Welcome to AI Campus OS"
    greeting = f"Hi {full_name}," if full_name else "Hi,"
    body = (
        f"{greeting}\n\n"
        "Your AI Campus OS account has been created. "
        "You can now sign in with your email address."
    )
    try:
        send_mail(subject, body, _from_email(), [email], fail_silently=True)
    except Exception:  # pragma: no cover
        logger.exception("Failed to send welcome email to %s", email)
        return False
    return True
