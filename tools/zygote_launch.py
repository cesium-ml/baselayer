"""Run a Python service script as a fork of the zygote, standing in for it.

Usage: zygote_launch.py SCRIPT [ARGS...]

supervisord runs this in place of `python SCRIPT ARGS...`. The zygote forks
the service with this process's stdio, argv, working directory and
environment; signals sent here are forwarded to the service, and this
process exits as the service did. While the service runs, its pid is kept in
`run/zygote/<launcher pid>.pid`. Only the standard library is imported, so
that each launcher stays small.
"""

import json
import os
import signal
import socket
import sys
import time

SOCKET = "run/zygote.sock"
PIDS = "run/zygote"
CONNECT_TIMEOUT = 300
FORWARDED = (
    signal.SIGTERM,
    signal.SIGINT,
    signal.SIGHUP,
    signal.SIGQUIT,
    signal.SIGUSR1,
    signal.SIGUSR2,
)


def connect():
    deadline = time.monotonic() + CONNECT_TIMEOUT
    while True:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(SOCKET)
            return sock
        except OSError:
            sock.close()
            if time.monotonic() > deadline:
                sys.exit(f"zygote_launch: no zygote listening on {SOCKET}")
            time.sleep(0.5)


def main():
    request = json.dumps(
        {"argv": sys.argv[1:], "cwd": os.getcwd(), "env": dict(os.environ)}
    ).encode()
    sock = connect()
    socket.send_fds(sock, [len(request).to_bytes(4, "big") + request], [0, 1, 2])

    replies = sock.makefile("r")
    pid = json.loads(replies.readline())["pid"]
    os.makedirs(PIDS, exist_ok=True)
    pidfile = os.path.join(PIDS, f"{os.getpid()}.pid")
    with open(pidfile, "w") as f:
        f.write(str(pid))

    def forward(signum, frame):
        try:
            os.killpg(pid, signum)
        except ProcessLookupError:
            pass

    for signum in FORWARDED:
        signal.signal(signum, forward)

    try:
        line = replies.readline()
    finally:
        os.unlink(pidfile)
    if not line:
        sys.exit("zygote_launch: lost the zygote")
    code = json.loads(line)["exit"]
    if code < 0:
        # Die of the same signal, so that supervisord sees what the service saw
        signal.signal(-code, signal.SIG_DFL)
        os.kill(os.getpid(), -code)
    sys.exit(code)


if __name__ == "__main__":
    main()
