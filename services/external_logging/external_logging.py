#!/usr/bin/env python
# -*- coding: utf-8 -*-

import threading
import logging
import socket
from logging.handlers import SysLogHandler

from baselayer.log import make_log
from baselayer.app.env import load_env
from baselayer.tools.watch_logs import (
    basedir, watched, tail_f
)

env, cfg = load_env()
log = make_log("external_logging")


def check_external_logging():
    """
    Check 3rd party logging, if enabled, and make sure that
    it is set up properly

    TODO: This could eventually be done with a JSONschema
    """
    enabled_services = []
    external_logging_enabled = False

    if not cfg.get('external_logging'):
        return external_logging_enabled, enabled_services

    external_logging_enabled = cfg['external_logging']["enabled"]
    if not external_logging_enabled:
        return external_logging_enabled, enabled_services

    print(cfg['external_logging'])
    for service, config in cfg['external_logging']["services"].items():
        if service == 'papertrail':
            if not config["enabled"]:
                break
            try:
                if config["url"].find("papertrailapp.com") == -1:
                    log("Warning: incorrect URL for papertrail logging.")
                    break
            except AttributeError:
                log("Warning: missing URL for papertrail logging.")
                break
            try:
                int(config["port"])
            except (ValueError, TypeError):
                log(
                    "Warning: bad port"
                    f" ({config['port']}) for papertrail logging."
                    " Should be an integer."
                )
                break
        log(f"Enabling external logging to {service}.")
        enabled_services.append(service)

    return external_logging_enabled, enabled_services


def get_papertrail_stream_logger():

    class ContextFilter(logging.Filter):
        hostname = socket.gethostname()

        def filter(self, record):
            record.hostname = ContextFilter.hostname
            return True

    syslog = SysLogHandler(address=(
        cfg['external_logging']["services"]["papertrail"]["url"],
        cfg['external_logging']["services"]["papertrail"]["port"]
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


def stream_log(filename, stream_logger):
    stream_logger.info('-> ' + filename)
    for line in tail_f(filename):
        stream_logger.info(line)


external_logging_enabled, enabled_services = check_external_logging()

if external_logging_enabled:
    # logging set up: see `https://documentation.solarwinds.com/en/
    #   Success_Center/papertrail/Content/kb/configuration/
    #   configuring-centralized-logging-from-python-apps.htm`
    if "papertrail" in enabled_services:
        stream_logger = get_papertrail_stream_logger()
        excluded = cfg['external_logging']["services"]["papertrail"]["excluded_log_files"]
        threads = [
            threading.Thread(target=stream_log, args=(logfile, stream_logger))
            for logfile in watched if logfile not in excluded
        ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
else:
    log("External logging disabled.")
