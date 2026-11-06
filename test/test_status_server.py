"""Tests for the status page served in place of the app while it is down.

Run from the directory holding `baselayer`, e.g. ``pytest baselayer/test``.
"""

import json
import os
import socket
import socketserver
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from xmlrpc.server import SimpleXMLRPCDispatcher, SimpleXMLRPCRequestHandler

import pytest

BASELAYER = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class UnixRequestHandler(SimpleXMLRPCRequestHandler):
    disable_nagle_algorithm = False


class FakeSupervisor(socketserver.UnixStreamServer, SimpleXMLRPCDispatcher):
    def __init__(self, path, processes):
        socketserver.UnixStreamServer.__init__(self, path, UnixRequestHandler)
        SimpleXMLRPCDispatcher.__init__(self)
        self.logRequests = False
        self.register_function(lambda: processes, "supervisor.getAllProcessInfo")


def fetch(port, path, method="GET"):
    data = b"{}" if method == "POST" else None
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=data, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.headers, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.headers, error.read().decode()


@pytest.fixture
def status_server(tmp_path, monkeypatch):
    """Start the status server with the given app process stop times; returns its port."""
    # tmp_path is too long for a unix socket path on macOS.
    monkeypatch.chdir(tmp_path)
    (tmp_path / "run").mkdir()
    processes, supervisors = [], []

    def start(app_stops):
        supervisor = FakeSupervisor(
            "run/supervisor.sock",
            [{"group": "app", "stop": stop} for stop in app_stops],
        )
        threading.Thread(target=supervisor.serve_forever, daemon=True).start()
        supervisors.append(supervisor)

        status_port = free_port()
        (tmp_path / "config.yaml").write_text(
            f"app:\n  title: Example\nports:\n  status: {status_port}\n"
        )
        processes.append(
            subprocess.Popen(
                [
                    sys.executable,
                    str(BASELAYER / "services/status_server/status_server.py"),
                    "--config=config.yaml",
                ],
                cwd=tmp_path,
                env=os.environ | {"PYTHONPATH": str(BASELAYER.parent)},
            )
        )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                fetch(status_port, "/")
                return status_port
            except OSError:
                time.sleep(0.2)
        pytest.fail("the status server did not start")

    yield start

    for process in processes:
        process.terminate()
        process.wait(timeout=10)
    for supervisor in supervisors:
        supervisor.shutdown()
        supervisor.server_close()


def test_starting_until_an_app_process_has_exited(status_server):
    port = status_server(app_stops=[0, 0])

    status, headers, body = fetch(port, "/source/ZTF21abc")
    assert status == 503
    assert headers["Retry-After"] == "30"
    assert "Example is starting up" in body
    assert 'http-equiv="refresh"' in body


def test_unavailable_once_an_app_process_has_exited(status_server):
    port = status_server(app_stops=[0, 1790000000])

    for method in ("GET", "POST", "DELETE"):
        status, headers, body = fetch(port, "/api/sources", method=method)
        assert status == 503, method
        assert headers["Content-Type"].startswith("application/json")
        payload = json.loads(body)
        assert payload["status"] == "error"
        assert payload["data"] == {"state": "unavailable"}
