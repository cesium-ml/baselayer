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
import logging
import socket
from logging.handlers import SysLogHandler

from app.env import load_env

env, cfg = load_env()


# check 3rd party logging, if enabled, and make sure that
# it is set up properly
if cfg.get('external_logging'):
    external_logging_enabled = cfg['external_logging']["enabled"]
    if external_logging_enabled:
        if cfg['external_logging']['service_name'] != 'papertrail':
            # we do not know how to do this yet
            print(
                "Warning: we only know how to use papertrail"
                " for external logging"
            )
            external_logging_enabled = False
        try:
            if cfg['external_logging']["url"].find("papertrailapp.com") == -1:
                print("Warning: incorrect URL for papertrail logging")
                external_logging_enabled = False
        except AttributeError:
            print("Warning: missing URL for papertrail logging")
            external_logging_enabled = False
        try:
            int(cfg['external_logging']["port"])
        except (ValueError, TypeError):
            print(
                "Warning: bad port"
                f" ({cfg['external_logging']['port']}) for papertrail logging"
            )
            external_logging_enabled = False
else:
    external_logging_enabled = False


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
                if '%' in logfile:
                    watched.extend(glob.glob(logfile.split('%')[0] + '*'))
                else:
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


def get_stream_logger():

    class ContextFilter(logging.Filter):
        hostname = socket.gethostname()

        def filter(self, record):
            record.hostname = ContextFilter.hostname
            return True

    syslog = SysLogHandler(address=(
        cfg['external_logging']["url"], cfg['external_logging']["port"]
    ))
    syslog.addFilter(ContextFilter())
    title = cfg['app'].get("title", basedir.split("/")[-1])
    format = f'%(asctime)s %(hostname)s {title}: %(message)s'
    formatter = logging.Formatter(format, datefmt='%b %d %H:%M:%S')
    syslog.setFormatter(formatter)
    logger = logging.getLogger()
    logger.addHandler(syslog)
    logger.setLevel(logging.INFO)
    return logger


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


def stream_log(filename, stream_logger):
    stream_logger.info('-> ' + filename)
    for line in tail_f(filename):
        stream_logger.info(line)


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

if external_logging_enabled:
    # logging set up: see `https://documentation.solarwinds.com/en/
    #   Success_Center/papertrail/Content/kb/configuration/
    #   configuring-centralized-logging-from-python-apps.htm`
    stream_logger = get_stream_logger()
    threads.extend([
        threading.Thread(target=stream_log, args=(logfile, stream_logger))
        for logfile in watched if watched not in cfg['external_logging']["excluded_log_files"]
    ])
else:
    print("External logging disabled.")

for t in threads:
    t.start()
for t in threads:
    t.join()
