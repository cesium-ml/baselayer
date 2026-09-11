#!/usr/bin/env python

import glob
import os
import threading
import time
from itertools import cycle
from os.path import join as pjoin

from baselayer.log import colorize

basedir = pjoin(os.path.dirname(__file__), "..")

_print_lock = threading.Lock()


def tail_f(filename, interval=1.0):
    while True:
        try:
            f = open(filename)
            break
        except OSError:
            time.sleep(1)

    f.seek(0, os.SEEK_END)

    while True:
        where = f.tell()
        line = f.readline()
        if not line:
            time.sleep(interval)
            f.seek(where)
        else:
            yield line.rstrip("\n")


def print_log(filename, color="default"):
    def print_col(line):
        with _print_lock:
            print(colorize(line, fg=color))

    print_col(f"-> {filename}")

    for line in tail_f(filename):
        print_col(line)


def log_watcher(printers: list | None = None):
    """Watch for new logs, and start following them.

    Parameters
    ----------
    printers : list of callables
        Functions of form `f(logfile, color=None)` used to print the
        tailed log file.  By default, logs are sent to stdout.  Note
        that the printer is also responsible for following (tailing)
        the log file

    See Also
    --------
    print_log : the default stdout printer

    """
    if printers is None:
        printers = [print_log]

    colors = cycle(["green", "yellow", "blue", "magenta", "cyan", "red", "default"])
    watched = set()
    interval = 1

    while True:
        all_logs = set(glob.glob("log/*.log"))

        for logfile in sorted(all_logs - watched):
            color = next(colors)
            for printer in printers:
                threading.Thread(
                    target=printer, args=(logfile,), kwargs={"color": color}
                ).start()

        watched = all_logs

        time.sleep(interval)
        interval = max(interval * 2, 60)


if __name__ == "__main__":
    log_watcher()
