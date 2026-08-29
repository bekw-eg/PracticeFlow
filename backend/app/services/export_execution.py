"""Bound export execution time without changing the HTTP export contract."""
from __future__ import annotations

import asyncio
from collections.abc import Callable

from fastapi import HTTPException, status


async def run_export_with_timeout(operation: Callable[[], bytes], timeout_seconds: int) -> bytes:
    """Run one synchronous renderer under the request's configured deadline.

    DOCX/PDF libraries are synchronous.  Running them in the API process keeps
    the requested architecture (no queue or worker process) while allowing the
    HTTP request to stop waiting at a bounded deadline.  Redis slot TTLs are
    configured to the same deadline, so a process crash or a renderer that
    cannot be interrupted by Python is never able to reserve a slot forever.
    """
    try:
        return await asyncio.wait_for(asyncio.to_thread(operation), timeout=timeout_seconds)
    except TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Export took too long and was stopped for this request.",
        ) from None
