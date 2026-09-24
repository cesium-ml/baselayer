#!/usr/bin/env python
"""Print the memory used by each supervisor service, including its child processes."""

import argparse
import os
import shutil
import sys
import time
from datetime import datetime
from os.path import join as pjoin

import psutil
from supervisor.options import ClientOptions

base_dir = os.path.abspath(pjoin(os.path.dirname(__file__), "../.."))
SUPERVISORD_CFG = "baselayer/conf/supervisor/supervisor.conf"


def service_pids(config=SUPERVISORD_CFG):
    """Return {service name: pid} for supervisord and each running service."""
    options = ClientOptions()
    options.realize(["-c", config])
    supervisor = options.getServerProxy().supervisor

    pids = {"supervisord": supervisor.getPID()}
    for p in supervisor.getAllProcessInfo():
        if p["pid"]:
            name = p["name"] if p["group"] == p["name"] else f"{p['group']}:{p['name']}"
            pids[name] = p["pid"]
    return pids


def tree_memory(pid, recursive=True):
    """Return (process count, RSS, PSS) in bytes for `pid` and its descendants.

    PSS is None where the platform does not report it (e.g., macOS).
    """
    try:
        root = psutil.Process(pid)
        procs = [root] + (root.children(recursive=True) if recursive else [])
    except psutil.NoSuchProcess:
        return 0, 0, None

    count, rss, pss = 0, 0, 0
    for proc in procs:
        try:
            mem = proc.memory_full_info()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        count += 1
        rss += mem.rss
        if pss is not None:
            pss = pss + mem.pss if hasattr(mem, "pss") else None
    return count, rss, pss


def _mb(n):
    return f"{n / 2**20:10.0f}" if n is not None else f"{'-':>10}"


def memory_table(pids):
    """Format the memory used by each service as a table, largest first."""
    rows = []
    for name, pid in pids.items():
        # supervisord's children are the services, which have their own rows
        count, rss, pss = tree_memory(pid, recursive=(name != "supervisord"))
        if count:
            rows.append((name, count, rss, pss))
    if not rows:
        # e.g., supervisord runs in a container or other PID namespace
        return "supervisord is running, but none of its processes are visible here"

    has_pss = all(pss is not None for *_, pss in rows)
    rows.sort(key=lambda r: r[3] if has_pss else r[2], reverse=True)
    rows.append(
        (
            "TOTAL",
            sum(r[1] for r in rows),
            sum(r[2] for r in rows),
            sum(r[3] for r in rows) if has_pss else None,
        )
    )

    width = max(len(r[0]) for r in rows)
    lines = [f"{'SERVICE':<{width}}  {'PROCS':>5}  {'RSS (MB)':>10}  {'PSS (MB)':>10}"]
    for i, (name, count, rss, pss) in enumerate(rows):
        if i == len(rows) - 1:
            lines.append("-" * len(lines[0]))
        lines.append(f"{name:<{width}}  {count:>5}  {_mb(rss)}  {_mb(pss)}")
    lines.append("")
    lines.append(
        "RSS counts shared pages once per process; PSS divides them among the sharers."
    )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-w", "--watch", action="store_true", help="refresh the table until Ctrl-C"
    )
    parser.add_argument(
        "-n",
        "--interval",
        type=float,
        default=2,
        help="seconds between refreshes with --watch (default: 2)",
    )
    args = parser.parse_args()

    os.chdir(base_dir)
    if args.watch:
        watch(args.interval)
    else:
        print(current_table())


def current_table():
    try:
        return memory_table(service_pids())
    except OSError:
        sys.exit("supervisord is not running; start the app with `make run`")


def watch(interval):
    """Redraw the table in place, on the terminal's alternate screen, until Ctrl-C."""
    out = sys.stdout
    out.write("\033[?1049h\033[?25l")  # enter alternate screen, hide cursor
    try:
        while True:
            lines = [
                f"{datetime.now():%H:%M:%S}, every {interval:g}s (Ctrl-C to quit)",
                "",
                *current_table().splitlines(),
            ]
            lines = lines[: shutil.get_terminal_size().lines - 1]
            # Overwrite each line in place, then clear whatever is below
            out.write(
                "\033[H" + "".join(f"{line}\033[K\n" for line in lines) + "\033[J"
            )
            out.flush()
            time.sleep(interval)
    except KeyboardInterrupt:
        pass
    finally:
        out.write("\033[?25h\033[?1049l")  # show cursor, leave alternate screen
        out.flush()


if __name__ == "__main__":
    main()
