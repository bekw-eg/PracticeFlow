"""Worker identity helper for structured logs and job leases."""
from __future__ import annotations

import os
import socket


def default_worker_id() -> str:
    # This value stays in job leases and structured worker logs, never metrics labels.
    return f"{socket.gethostname()}-{os.getpid()}"
