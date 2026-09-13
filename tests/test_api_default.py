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
    "/experiments",
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
    "/experiments",
)


@contextmanager
def _served() -> Iterator[int]:
    """Serve the default provider on a loopback ephemeral port until the block exits."""
    server = create_server(port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _get(port: int, path: str) -> tuple[int, object]:
    """GET a path and return the HTTP status with the decoded JSON body."""
    url = f"http://127.0.0.1:{port}{path}"
    with urllib.request.urlopen(url, timeout=5) as response:
        return response.status, json.loads(response.read())


def test_default_provider_all_json_routes_return_200() -> None:
    """Every JSON route returns 200 with a JSON body under the real provider."""
    with _served() as port:
        for path in JSON_ROUTES:
            status, body = _get(port, path)
            assert status == 200
            assert isinstance(body, dict)
            if path == "/markets":
                assert body["count"] >= 1
            if path == "/research":
                assert body["count"] >= 1
            if path == "/run":
                assert body["data"]["caveat"]


def test_default_provider_root_serves_dashboard() -> None:
    """The root route serves the research dashboard HTML."""
    with _served() as port:
        url = f"http://127.0.0.1:{port}/"
        with urllib.request.urlopen(url, timeout=5) as response:
            status = response.status
            body = response.read().decode("utf-8")
    assert status == 200
    assert "Poly-Alpha Research" in body
    assert "not investment advice" in body.lower()


def test_default_provider_simulated_flags() -> None:
    """Every simulated route labels its payload as simulated."""
    with _served() as port:
        for path in SIMULATED_ROUTES:
            _, body = _get(port, path)
            assert isinstance(body, dict)
            assert body["simulated"] is True


def test_default_provider_unknown_path_404() -> None:
    """An unknown path raises an HTTP 404 error."""
    with _served() as port:
        try:
            _get(port, "/nope")
        except urllib.error.HTTPError as exc:
            assert exc.code == 404
        else:
            raise AssertionError("expected HTTPError 404")


def test_health_lists_capabilities() -> None:
    """The health route reports the capability list and a version string."""
    with _served() as port:
        _, body = _get(port, "/health")
    assert isinstance(body, dict)
    capabilities = body["capabilities"]
    assert "run" in capabilities
    assert "allocate" in capabilities
    assert "experiments" in capabilities
    assert isinstance(body["version"], str)


def test_experiments_route_reports_recorded_count() -> None:
    """The experiments route returns the recorded list and its count."""
    with _served() as port:
        _, body = _get(port, "/experiments")
    assert isinstance(body, dict)
    assert body["simulated"] is True
    assert isinstance(body["count"], int)
    assert isinstance(body["data"], list)
