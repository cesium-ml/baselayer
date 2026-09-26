"""Tests for the status page served in place of the app while it is down.

Run from the directory holding `baselayer`, e.g. ``pytest baselayer/test``.
"""

import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

BASELAYER = Path(__file__).resolve().parents[1]


def free_ports(count):
    sockets = [socket.socket() for _ in range(count)]
    for sock in sockets:
        sock.bind(("127.0.0.1", 0))
    ports = [sock.getsockname()[1] for sock in sockets]
    for sock in sockets:
        sock.close()
    return ports


class Migrated(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"migrated": true}')

    def log_message(self, *args):
        pass


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
def status_server(tmp_path):
    """Start the status server in a given situation; returns its port."""
    processes, managers = [], []

    def start(migration_manager_up=False, maintenance=None):
        status_port, manager_port = free_ports(2)
        (tmp_path / "run").mkdir(exist_ok=True)
        if maintenance is not None:
            (tmp_path / "run/maintenance").write_text(maintenance)
        (tmp_path / "config.yaml").write_text(
            "app:\n"
            "  title: Example\n"
            "ports:\n"
            f"  status: {status_port}\n"
            f"  migration_manager: {manager_port}\n"
        )
        if migration_manager_up:
            manager = HTTPServer(("127.0.0.1", manager_port), Migrated)
            threading.Thread(target=manager.serve_forever, daemon=True).start()
            managers.append(manager)

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
    for manager in managers:
        manager.shutdown()


def test_starting_while_the_migration_manager_is_not_listening(status_server):
    port = status_server()

    status, headers, body = fetch(port, "/source/ZTF21abc")
    assert status == 503
    assert headers["Retry-After"] == "30"
    assert "Example is starting up" in body
    assert 'http-equiv="refresh"' in body


def test_unavailable_once_the_database_is_migrated(status_server):
    port = status_server(migration_manager_up=True)

    status, _, body = fetch(port, "/")
    assert status == 503
    assert "Example is temporarily unavailable" in body


def test_maintenance_shows_the_escaped_operator_note(status_server):
    port = status_server(migration_manager_up=True, maintenance="Back at <18:00>")

    _, _, body = fetch(port, "/")
    assert "Example is down for maintenance" in body
    assert "Back at &lt;18:00&gt;" in body


def test_api_requests_get_json_whatever_the_method(status_server):
    port = status_server(migration_manager_up=True)

    for method in ("GET", "POST", "DELETE"):
        status, headers, body = fetch(port, "/api/sources", method=method)
        assert status == 503, method
        assert headers["Content-Type"].startswith("application/json")
        payload = json.loads(body)
        assert payload["status"] == "error"
        assert payload["data"] == {"state": "unavailable"}


def test_head_has_no_body(status_server):
    port = status_server()

    status, headers, body = fetch(port, "/", method="HEAD")
    assert status == 503
    assert headers["Retry-After"] == "30"
    assert body == ""
