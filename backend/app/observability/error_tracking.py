"""Optional, privacy-preserving Sentry integration.

No DSN means no import, no network traffic, and no change to normal request or
worker behaviour. If enabled, events are stripped to exception type and SDK
metadata before leaving the process.
"""
from __future__ import annotations

import logging
from typing import Any


log = logging.getLogger("practiceflow.error_tracking")
_enabled = False
_sdk: Any | None = None


def _before_send(event: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any]:
    event.pop("request", None)
    event.pop("user", None)
    event.pop("extra", None)
    event.pop("contexts", None)
    event["breadcrumbs"] = {"values": []}
    for value in event.get("exception", {}).get("values", []):
        value.pop("value", None)
        value.pop("stacktrace", None)
    return event


def configure_error_tracking(dsn: str | None, environment: str, *, sentry_sdk_module: Any | None = None) -> bool:
    """Initialise Sentry only when explicitly configured; return enabled state."""
    global _enabled, _sdk
    if not dsn:
        _enabled = False
        _sdk = None
        return False
    if sentry_sdk_module is None:
        import sentry_sdk  # type: ignore[import-not-found]

        sentry_sdk_module = sentry_sdk
    sentry_sdk_module.init(
        dsn=dsn,
        environment=environment,
        send_default_pii=False,
        traces_sample_rate=0.0,
        before_send=_before_send,
    )
    _sdk = sentry_sdk_module
    _enabled = True
    log.info("error_tracking_enabled", extra={"component": "sentry"})
    return True


def capture_exception(exception: BaseException) -> None:
    if _enabled and _sdk is not None:
        try:
            _sdk.capture_exception(exception)
        except Exception:
            # Error telemetry must never become an application failure path.
            log.warning("error_tracking_capture_failed", extra={"component": "sentry"})
