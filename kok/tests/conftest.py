"""
Shared test fixtures for Tayfa test suite.

- Unit/API tests: unaffected (they use httpx.AsyncClient, monkeypatch, tmp_path)
- E2E tests: auto-starts the Tayfa server, provides Playwright page via pytest-playwright

These fixtures only activate when E2E tests are collected.
"""
import os
import sys
import time
import socket
import subprocess

import pytest
import httpx


# ---------------------------------------------------------------------------
# Port helper
# ---------------------------------------------------------------------------

def _find_free_port(start: int = 9900, attempts: int = 20) -> int:
    """Find a free TCP port starting from `start`."""
    for offset in range(attempts):
        port = start + offset
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port found in range {start}-{start + attempts}")


# ---------------------------------------------------------------------------
# Server fixture (session-scoped) — only invoked for E2E tests
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def tayfa_server(tmp_path_factory):
    """
    Start the Tayfa orchestrator on a free port.
    Yields the base URL string (e.g. "http://127.0.0.1:9901").
    Kills the process on teardown.
    """
    port = _find_free_port()
    kok_dir = os.path.join(os.path.dirname(__file__), "..")
    app_py = os.path.join(kok_dir, "app.py")

    env = os.environ.copy()
    env["TAYFA_TEST_MODE"] = "1"
    env["TAYFA_TEST_PORT"] = str(port)

    # Create a temporary test project directory
    test_project_dir = str(tmp_path_factory.mktemp("tayfa_test_project"))

    creation_flags = 0
    if sys.platform == "win32":
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP

    proc = subprocess.Popen(
        [sys.executable, app_py, "--project", test_project_dir],
        cwd=kok_dir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=creation_flags,
    )

    base_url = f"http://127.0.0.1:{port}"

    # Wait for server readiness (max 30 seconds)
    deadline = time.time() + 30
    ready = False
    while time.time() < deadline:
        try:
            resp = httpx.get(f"{base_url}/api/health", timeout=2.0)
            if resp.status_code == 200:
                ready = True
                break
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout):
            pass
        time.sleep(0.5)

    if not ready:
        proc.terminate()
        stdout = proc.stdout.read().decode(errors="replace")
        stderr = proc.stderr.read().decode(errors="replace")
        raise RuntimeError(
            f"Tayfa server did not start within 30s on port {port}.\n"
            f"STDOUT:\n{stdout[:2000]}\nSTDERR:\n{stderr[:2000]}"
        )

    yield base_url

    # Teardown
    try:
        httpx.post(f"{base_url}/api/shutdown", timeout=5.0)
        proc.wait(timeout=10)
    except Exception:
        pass
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


# ---------------------------------------------------------------------------
# pytest-playwright integration
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Override pytest-playwright's default context args."""
    return {
        **browser_context_args,
        "viewport": {"width": 1280, "height": 720},
        "ignore_https_errors": True,
    }


@pytest.fixture(scope="session")
def base_url(tayfa_server):
    """
    Override pytest-playwright's base_url to point at the test server.
    Makes page.goto("/") resolve to the auto-started server URL.
    """
    return tayfa_server
