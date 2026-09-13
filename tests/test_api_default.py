"""Tests exercising the JSON API through the real default provider over loopback."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager

from poly_alpha.api.server import create_server

JSON_ROUTES = (
    "/health",
    "/markets",
    "/research",
    "/risk",
    "/compare",
    "/overview",
    "/validation",
    "/curves",
    "/calibration",
    "/stress",
    "/allocate",
    "/run",
)

SIMULATED_ROUTES = (
    "/research",
    "/risk",
    "/compare",
    "/overview",
    "/curves",
    "/calibration",
    "/stress",
    "/allocate",
    "/run",
)


@contextmanager
def _served() -> Iterator[int]:
    """Serve the default provider on a loopback ephemeral port until the block exits."""
    server = create_server(port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
