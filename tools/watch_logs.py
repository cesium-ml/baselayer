#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
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


def logs_from_config(supervisor_conf):
    watched = []

    with open(supervisor_conf) as f:
        for line in f:
            if '_logfile=' in line:
                _, logfile = line.strip().split('=')
                watched.append(logfile)

    return watched


basedir = pjoin(os.path.dirname(__file__), '..')
logdir = '../log'
watched = logs_from_config(pjoin(basedir, 'conf/supervisor/supervisor.conf'))

sys.path.insert(0, basedir)

watched.append('log/error.log')
watched.append('log/nginx-bad-access.log')
watched.append('log/nginx-error.log')
watched.append('log/fake_oauth2.log')
watched.append('log/app.log')


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


def print_log(filename, color):
    def print_col(line):
        print(colorize(line, fg=color))

    print_col('-> ' + filename)

    for line in tail_f(filename):
        print_col(line)


colors = ['default', 'green', 'yellow', 'blue', 'magenta', 'cyan', 'red']
threads = [
    threading.Thread(target=print_log, args=(logfile, colors[n % len(colors)]))
    for (n, logfile) in enumerate(watched)
]

for t in threads:
    t.start()
for t in threads:
    t.join()
