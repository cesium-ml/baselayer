"""Tests for the zygote, which forks services from one preloaded process.

Run from the directory holding `baselayer`, e.g. ``pytest baselayer/test``.
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

BASELAYER = Path(__file__).resolve().parents[1]

PRELOADED = """
import os

with open("imported_by", "w") as f:
    f.write(str(os.getpid()))
"""

SLEEPER = """
import os
import time

with open("service_pid", "w") as f:
    f.write(str(os.getpid()))
time.sleep(600)
"""


@pytest.fixture
def zygote(tmp_path):
    (tmp_path / "run").mkdir()
    (tmp_path / "preloaded.py").write_text(PRELOADED)
    (tmp_path / "config.yaml").write_text("zygote:\n  preload: [preloaded]\n")
    env = os.environ | {
        "PYTHONPATH": f"{tmp_path}{os.pathsep}{BASELAYER.parent}",
        "PYTHONUNBUFFERED": "1",
    }
    process = subprocess.Popen(
        [
            sys.executable,
            str(BASELAYER / "services/zygote/zygote.py"),
            "--config=config.yaml",
        ],
        cwd=tmp_path,
        env=env,
    )
    socket_path = tmp_path / "run/zygote.sock"
    deadline = time.monotonic() + 60
    while not socket_path.exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    assert socket_path.exists(), "the zygote did not start listening"
    try:
        yield process, tmp_path, env
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


def launch(zygote, script, *args, **popen_args):
    _, tmp_path, env = zygote
    (tmp_path / "service.py").write_text(script)
    return subprocess.Popen(
        [
            sys.executable,
            str(BASELAYER / "tools/zygote_launch.py"),
            "service.py",
            *args,
        ],
        cwd=tmp_path,
        env=env,
        **popen_args,
    )


def wait_for_file(path, timeout=30):
    deadline = time.monotonic() + timeout
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    return path.read_text()


def _alive(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def wait_until_dead(pid, timeout=30):
    deadline = time.monotonic() + timeout
    while _alive(pid) and time.monotonic() < deadline:
        time.sleep(0.1)
    return not _alive(pid)


def test_a_service_is_a_fork_of_the_preloaded_zygote(zygote):
    process, tmp_path, _ = zygote
    script = (
        "import os, sys\nprint(os.getppid(), 'preloaded' in sys.modules)\nsys.exit(3)\n"
    )

    launcher = launch(zygote, script, stdout=subprocess.PIPE, text=True)
    out, _ = launcher.communicate(timeout=60)

    assert launcher.returncode == 3
    assert out.split() == [str(process.pid), "True"]
    assert (tmp_path / "imported_by").read_text() == str(process.pid)


def test_a_service_parses_its_own_arguments(zygote):
    script = (
        "from baselayer.app.env import load_env, parser\n"
        "parser.add_argument('--process', type=int)\n"
        "env, cfg = load_env()\n"
        "print(env.process, cfg['zygote.preload'])\n"
    )

    launcher = launch(
        zygote,
        script,
        "--config=config.yaml",
        "--process=7",
        stdout=subprocess.PIPE,
        text=True,
    )
    out, _ = launcher.communicate(timeout=60)

    assert launcher.returncode == 0
    assert out.splitlines()[-1] == "7 ['preloaded']"


def test_a_signal_to_the_launcher_reaches_the_service(zygote):
    _, tmp_path, _ = zygote
    launcher = launch(zygote, SLEEPER)
    service = int(wait_for_file(tmp_path / "service_pid"))

    launcher.send_signal(signal.SIGTERM)

    assert launcher.wait(timeout=30) == -signal.SIGTERM
    assert wait_until_dead(service)


def test_the_service_stops_when_its_launcher_is_killed(zygote):
    _, tmp_path, _ = zygote
    launcher = launch(zygote, SLEEPER)
    service = int(wait_for_file(tmp_path / "service_pid"))

    launcher.kill()

    assert wait_until_dead(service)


@pytest.mark.skipif(sys.platform != "linux", reason="needs PR_SET_NAME")
def test_a_service_is_named_after_its_program(zygote):
    _, tmp_path, env = zygote
    script = "print(open('/proc/self/comm').read().strip())\n"
    (tmp_path / "service.py").write_text(script)

    out = subprocess.run(
        [sys.executable, str(BASELAYER / "tools/zygote_launch.py"), "service.py"],
        cwd=tmp_path,
        env=env | {"SUPERVISOR_PROCESS_NAME": "thumbnail_queue_extra"},
        capture_output=True,
        text=True,
        timeout=60,
    ).stdout

    assert out.strip() == "thumbnail_queue"


@pytest.mark.skipif(sys.platform != "linux", reason="needs PR_SET_PDEATHSIG")
def test_services_stop_when_the_zygote_dies(zygote):
    process, tmp_path, _ = zygote
    launcher = launch(zygote, SLEEPER)
    service = int(wait_for_file(tmp_path / "service_pid"))

    process.kill()

    assert wait_until_dead(service)
    assert launcher.wait(timeout=30) != 0


def test_only_python_commands_are_sent_through_the_zygote():
    from baselayer.tools.setup_services import fork_from_zygote

    conf = (
        "[program:a]\n"
        "command=/usr/bin/env python services/a/a.py %(ENV_FLAGS)s\n"
        "[program:nginx]\n"
        "command=nginx -c baselayer/services/nginx/nginx.conf\n"
    )

    forked = fork_from_zygote(conf)

    assert (
        "command=/usr/bin/env python baselayer/tools/zygote_launch.py"
        " services/a/a.py %(ENV_FLAGS)s" in forked
    )
    assert "command=nginx -c" in forked
    assert fork_from_zygote(forked) == forked
