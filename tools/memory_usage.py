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
# tools/zygote_launch.py writes the pid of its service to <launcher pid>.pid
ZYGOTE_PIDS = "run/zygote"


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


def forked_pid(launcher_pid):
    """Return the pid of the service that a zygote launcher stands in for, or None."""
    try:
        with open(pjoin(ZYGOTE_PIDS, f"{launcher_pid}.pid")) as f:
            return int(f.read())
    except (OSError, ValueError):
        return None


def service_memory(name, pid):
    """Return (process count, RSS, PSS, USS) in bytes for a supervisor service.

    A service forked from the zygote counts its launcher and its fork. The
    zygote counts only itself: its children are the forked services.
    """
    if name in ("supervisord", "zygote"):
        # supervisord's children are the services, which have their own rows
        return tree_memory(pid, recursive=False)

    total = tree_memory(pid)
    service = forked_pid(pid)
    fork = tree_memory(service) if service else (0, 0, 0, 0)
    if fork[0]:
        total = tuple(_add(a, b) for a, b in zip(total, fork))
    return total


def _add(a, b):
    return a + b if a is not None and b is not None else None


def tree_memory(pid, recursive=True):
    """Return (process count, RSS, PSS, USS) in bytes for `pid` and its descendants.

    RSS counts shared pages in each process, PSS divides them among the
    processes that share them, and USS leaves them out. PSS and USS are None
    where they cannot be read (e.g., PSS on macOS).
    """
    try:
        root = psutil.Process(pid)
        procs = [root] + (root.children(recursive=True) if recursive else [])
    except psutil.NoSuchProcess:
        return 0, 0, None, None

    count, rss, pss, uss = 0, 0, 0, 0
    for proc in procs:
        try:
            try:
                mem = proc.memory_full_info()
            except psutil.AccessDenied:
                mem = proc.memory_info()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        count += 1
        rss += mem.rss
        pss = _add(pss, getattr(mem, "pss", None))
        uss = _add(uss, getattr(mem, "uss", None))
    return count, rss, pss, uss


def _mb(n):
    return f"{n / 2**20:10.0f}" if n is not None else f"{'-':>10}"


def memory_table(pids):
    """Format the memory used by each service as a table, largest first."""
    rows = []
    for name, pid in pids.items():
        count, rss, pss, uss = service_memory(name, pid)
        if count:
            rows.append((name, count, rss, pss, uss))
    if not rows:
        # e.g., supervisord runs in a container or other PID namespace
        return "supervisord is running, but none of its processes are visible here"

    has_pss = all(r[3] is not None for r in rows)
    rows.sort(key=lambda r: r[3] if has_pss else r[2], reverse=True)
    totals = [sum(r[i] for r in rows) for i in (1, 2)]
    for i in (3, 4):
        values = [r[i] for r in rows]
        totals.append(None if None in values else sum(values))
    rows.append(("TOTAL", *totals))

    width = max(len(r[0]) for r in rows)
    header = f"{'SERVICE':<{width}}  {'PROCS':>5}" + "".join(
        f"  {c + ' (MB)':>10}" for c in ("RSS", "PSS", "USS")
    )
    lines = [header]
    for i, (name, count, *mem) in enumerate(rows):
        if i == len(rows) - 1:
            lines.append("-" * len(header))
        lines.append(
            f"{name:<{width}}  {count:>5}" + "".join(f"  {_mb(m)}" for m in mem)
        )
    lines += [
        "",
        "RSS counts shared pages once per process; PSS divides them among the sharers;",
        "USS counts only the pages that no other process uses.",
    ]
    if "zygote" in (r[0] for r in rows):
        lines.append(
            "Forked services share the zygote's RSS; their USS is what each one adds."
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
