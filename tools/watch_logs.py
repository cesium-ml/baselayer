#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import glob
from os.path import join as pjoin
import contextlib
import io
import time
import threading
from baselayer.log import colorize


@contextlib.contextmanager
def nostdout():
    save_stdout = sys.stdout
    sys.stdout = io.StringIO()
    yield
    sys.stdout = save_stdout


basedir = pjoin(os.path.dirname(__file__), '..')
logdir = '../log'

sys.path.insert(0, basedir)


def tail_f(filename, interval=1.0):
    f = None

    while not f:
        try:
            f = open(filename, 'r')
            break
        except IOError:
            time.sleep(1)

    # Find the size of the file and move to the end
    st_results = os.stat(filename)
    st_size = st_results[6]
    f.seek(st_size)

    while True:
        where = f.tell()
        line = f.readline()
        if not line:
            time.sleep(interval)
            f.seek(where)
        else:
            yield line.rstrip('\n')


def print_log(filename, color='default', stream=None):
    """
    Print log to stdout; stream is ignored.
    """
    def print_col(line):
        print(colorize(line, fg=color))

    print_col(f'-> {filename}')

    for line in tail_f(filename):
        print_col(line)


def log_watcher(printers=None):
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
    # Start with a short discovery interval, then back off
    # until that interval is 60s
    interval = 1

    if printers is None:
        printers = [print_log]

    colors = ['default', 'green', 'yellow', 'blue', 'magenta', 'cyan', 'red']
    watched = set()

    color = 0
    while True:
        all_logs = set(glob.glob('log/*.log'))
        new_logs = all_logs - watched

        for logfile in sorted(new_logs):
            color = (color + 1) % len(colors)
            for printer in printers:
                thread = threading.Thread(
                    target=printer,
                    args=(logfile,),
                    kwargs={'color': colors[color]}
                )
                thread.start()

        watched = all_logs

        time.sleep(interval)
        interval = max(interval * 2, 60)


if __name__ == "__main__":
    log_watcher()
