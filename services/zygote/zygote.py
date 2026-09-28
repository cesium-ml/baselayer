"""Import the application once, then fork services from it on request.

`tools/zygote_launch.py` asks for a service over `run/zygote.sock`, passing
its stdio, argv, working directory and environment. Forked services share
the preloaded modules copy-on-write.
"""

import ctypes
import gc
import importlib
import json
import os
import runpy
import selectors
import signal
import socket
import sys
import traceback

from baselayer.app import env as baselayer_env
from baselayer.app.env import load_env
from baselayer.log import make_log

SOCKET = "run/zygote.sock"
PR_SET_NAME = 15
PR_SET_PDEATHSIG = 1

env, cfg = load_env()
log = make_log("zygote")


def preload():
    modules = cfg["zygote.preload"] or [cfg["app.factory"].rsplit(".", 1)[0]]
    for module in modules:
        importlib.import_module(module)
    log(f"Preloaded {', '.join(modules)} ({len(sys.modules)} modules)")


def receive_request(conn):
    data, fds, _, _ = socket.recv_fds(conn, 65536, 3)
    if len(fds) != 3:
        raise ValueError("expected stdin, stdout and stderr")
    size = int.from_bytes(data[:4], "big")
    data = data[4:]
    while len(data) < size:
        chunk = conn.recv(size - len(data))
        if not chunk:
            raise EOFError("launcher closed during request")
        data += chunk
    return json.loads(data), fds


def prctl(option, arg):
    try:
        ctypes.CDLL(None, use_errno=True).prctl(option, arg)
    except (OSError, AttributeError):
        pass  # not Linux


def die_with_parent(parent):
    prctl(PR_SET_PDEATHSIG, signal.SIGTERM)
    if os.getppid() != parent:
        os._exit(1)


def run_service(request, fds):
    """Become the service, as `python SCRIPT ARGS...` would; never return."""
    code = 1
    try:
        os.setpgid(0, 0)
        for signum in (signal.SIGTERM, signal.SIGHUP, signal.SIGCHLD):
            signal.signal(signum, signal.SIG_DFL)
        signal.signal(signal.SIGINT, signal.default_int_handler)
        for target, fd in zip((0, 1, 2), fds):
            os.dup2(fd, target)
            os.close(fd)

        os.chdir(request["cwd"])
        os.environ.clear()
        os.environ.update(request["env"])
        sys.argv = request["argv"]
        # Shown by top and `ps -o comm`, which otherwise show the zygote
        name = os.environ.get("SUPERVISOR_PROCESS_NAME") or os.path.basename(
            sys.argv[0]
        )
        prctl(PR_SET_NAME, ctypes.create_string_buffer(name.encode()[:15]))
        sys.path[0] = os.path.dirname(os.path.abspath(sys.argv[0]))
        for path in reversed(os.environ.get("PYTHONPATH", "").split(os.pathsep)):
            if path and os.path.abspath(path) not in map(os.path.abspath, sys.path):
                sys.path.insert(1, path)
        if os.environ.get("PYTHONUNBUFFERED"):
            sys.stdout.reconfigure(line_buffering=True, write_through=True)
            sys.stderr.reconfigure(line_buffering=True, write_through=True)

        # Let the service add its own arguments and parse its own argv
        baselayer_env._cache.clear()
        vars(baselayer_env.parser).pop("add_argument", None)

        runpy.run_path(sys.argv[0], run_name="__main__")
        code = 0
    except SystemExit as e:
        if e.code is None or isinstance(e.code, int):
            code = e.code or 0
        else:
            print(e.code, file=sys.stderr)
    except BaseException:
        traceback.print_exc()
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(code)


def serve():
    if os.path.exists(SOCKET):
        os.unlink(SOCKET)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(SOCKET)
    os.chmod(SOCKET, 0o600)
    server.listen(64)

    selector = selectors.DefaultSelector()
    selector.register(server, selectors.EVENT_READ)
    children = {}  # pid -> launcher connection
    zygote = os.getpid()

    def shutdown(signum, frame):
        for pid in children:
            try:
                os.killpg(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    log(f"Listening on {SOCKET}")

    while True:
        for key, _ in selector.select(timeout=0.5):
            if key.fileobj is server:
                conn, _ = server.accept()
                try:
                    request, fds = receive_request(conn)
                except (OSError, ValueError, EOFError) as e:
                    log(f"Bad request: {e}")
                    conn.close()
                    continue
                sys.stdout.flush()
                sys.stderr.flush()
                pid = os.fork()
                if pid == 0:
                    selector.close()
                    server.close()
                    for other in children.values():
                        other.close()
                    conn.close()
                    die_with_parent(zygote)
                    run_service(request, fds)
                for fd in fds:
                    os.close(fd)
                children[pid] = conn
                conn.sendall(json.dumps({"pid": pid}).encode() + b"\n")
                selector.register(conn, selectors.EVENT_READ, pid)
                log(f"Forked {' '.join(request['argv'])} as {pid}")
            else:
                # A launcher never sends more after its request, so this is EOF
                pid = key.data
                selector.unregister(key.fileobj)
                if pid in children:
                    log(f"Launcher of {pid} went away; stopping it")
                    try:
                        os.killpg(pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass

        while children:
            try:
                pid, status = os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                break
            if pid == 0:
                break
            conn = children.pop(pid, None)
            if conn is None:
                continue
            code = os.waitstatus_to_exitcode(status)
            try:
                conn.sendall(json.dumps({"exit": code}).encode() + b"\n")
            except OSError:
                pass
            try:
                selector.unregister(conn)
            except (KeyError, ValueError):
                pass
            conn.close()


preload()
gc.collect()
gc.freeze()
serve()
