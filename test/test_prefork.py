"""Tests for the preforking app server.

Run from the directory holding `baselayer`, e.g. ``pytest baselayer/test``.
"""

import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

BASELAYER = Path(__file__).resolve().parents[1]
PROCESSES = 3

STUB_APP = """
import os

import tornado.web


class Pid(tornado.web.RequestHandler):
    def get(self):
        self.write(str(os.getpid()))


def make_app(cfg, handlers, settings, process=None, env=None):
    return tornado.web.Application([(r"/pid", Pid)])
"""

MIGRATION_MANAGER = """
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer


class Migrated(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"migrated": true}')

    def log_message(self, *args):
        pass


HTTPServer(("127.0.0.1", int(sys.argv[1])), Migrated).serve_forever()
"""


def free_ports(count):
    """A base port with `count` consecutive free ports after it."""
    for _ in range(50):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            base = probe.getsockname()[1]
        try:
            held = [socket.socket() for _ in range(count)]
            for offset, sock in enumerate(held):
                sock.bind(("127.0.0.1", base + offset))
        except OSError:
            continue
        finally:
            for sock in held:
                sock.close()
        return base
    raise RuntimeError("no free port range")


def worker_pid(port, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/pid", timeout=1
            ) as response:
                return int(response.read())
        except OSError:
            time.sleep(0.2)
    return None


@pytest.fixture
def prefork(tmp_path):
    (tmp_path / "log").mkdir()
    (tmp_path / "stub_app.py").write_text(STUB_APP)
    (tmp_path / "migration_manager.py").write_text(MIGRATION_MANAGER)

    app_port = free_ports(PROCESSES + 1)
    manager_port = app_port + PROCESSES
    (tmp_path / "config.yaml").write_text(
        f"app:\n"
        f"  factory: stub_app.make_app\n"
        f"server:\n"
        f"  prefork: true\n"
        f"  processes: {PROCESSES}\n"
        f"ports:\n"
        f"  app_internal: {app_port}\n"
        f"  migration_manager: {manager_port}\n"
    )

    env = os.environ | {
        "PYTHONPATH": f"{tmp_path}{os.pathsep}{BASELAYER.parent}",
        "PYTHONUNBUFFERED": "1",
    }
    manager = subprocess.Popen(
        [sys.executable, "migration_manager.py", str(manager_port)],
        cwd=tmp_path,
        env=env,
    )
    parent = subprocess.Popen(
        [
            sys.executable,
            str(BASELAYER / "services/app/app.py"),
            "--config=config.yaml",
        ],
        cwd=tmp_path,
        env=env,
        start_new_session=True,
    )
    try:
        yield parent, app_port, tmp_path
    finally:
        for process in (parent, manager):
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


def test_every_worker_gets_its_own_port_and_log(prefork):
    _, app_port, tmp_path = prefork

    pids = [worker_pid(app_port + process) for process in range(PROCESSES)]
    assert None not in pids
    assert len(set(pids)) == PROCESSES

    for process in range(PROCESSES):
        logged = (tmp_path / f"log/app_{process:02d}.log").read_text()
        assert f"Listening on 127.0.0.1:{app_port + process}" in logged


def test_a_dead_worker_is_replaced(prefork):
    _, app_port, _ = prefork

    killed = worker_pid(app_port + 1)
    assert killed is not None
    os.kill(killed, signal.SIGTERM)

    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        replacement = worker_pid(app_port + 1, timeout=5)
        if replacement is not None and replacement != killed:
            return
    pytest.fail("the worker was not restarted")


def test_terminating_the_parent_stops_the_workers(prefork):
    parent, app_port, _ = prefork

    pids = [worker_pid(app_port + process) for process in range(PROCESSES)]
    assert None not in pids

    parent.terminate()
    parent.wait(timeout=30)

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if all(not _alive(pid) for pid in pids):
            return
        time.sleep(0.2)
    pytest.fail("a worker outlived its parent")


def _alive(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True
