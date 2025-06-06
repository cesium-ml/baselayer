#!/usr/bin/env python

import logging
import socket
from logging.handlers import SysLogHandler

from baselayer.app.env import load_env
from baselayer.log import make_log
from baselayer.tools.watch_logs import basedir, log_watcher, tail_f

env, cfg = load_env()
log = make_log("external_logging")


def is_int(x):
    try:
        int(x)
    except (ValueError, TypeError):
        return False
    else:
        return True


def check_config(config, service):
    if not config.get("enabled", True):
        log(f"Logging service {service} disabled")
        return False

    conditions = [(False, f"Unknown logging service: {service}")]

    if service == "papertrail":
        conditions = [
            ("url" not in config, "Warning: missing URL for papertrail logging."),
            ("port" not in config, "Warning: missing port for papertrail logging."),
            (
                config.get("url", "").find("papertrailapp.com") == -1,
                "Warning: incorrect URL for papertrail logging.",
            ),
            (
                not is_int(config["port"]),
                f"Warning: bad port [{config['port']}] for papertrail logging. Should be an integer.",
            ),
        ]

    for cond, msg in conditions:
        if cond:
            log(msg)

    valid = not any(check for (check, msg) in conditions)
    return valid


def external_logging_services():
    """Check 3rd party logging and make sure that it is set up properly

    TODO: This could eventually be done with a JSONschema

    """
    service_configs = cfg.get("external_logging", [])

    enabled_services = list(
        service
        for service in service_configs
        if check_config(service_configs[service], service)
    )

    for service in enabled_services:
        log(f"Enabling external logging to {service}.")

    if not enabled_services:
        log("No external logging services configured")

    return enabled_services


def get_papertrail_stream_logger():
    class ContextFilter(logging.Filter):
        hostname = socket.gethostname()

        def filter(self, record):
            record.hostname = ContextFilter.hostname
            return True

    syslog = SysLogHandler(
        address=(
            cfg["external_logging.papertrail.url"],
            cfg["external_logging.papertrail.port"],
        )
    )
    syslog.addFilter(ContextFilter())
    title = cfg["app"].get("title", basedir.split("/")[-1])
    format = f"%(asctime)s %(hostname)s {title}: %(message)s"
    formatter = logging.Formatter(format, datefmt="%b %d %H:%M:%S")
    syslog.setFormatter(formatter)
    logger = logging.getLogger()
    logger.addHandler(syslog)
    logger.setLevel(logging.INFO)
    return logger


enabled_services = external_logging_services()
printers = []

if "papertrail" in enabled_services:
    # logging set up: see
    # `https://documentation.solarwinds.com/en/Success_Center/papertrail/Content/kb/configuration/configuring-centralized-logging-from-python-apps.htm`

    stream_logger = get_papertrail_stream_logger()

    def papertrail_printer(logfile, **kwargs):
        excluded = cfg["external_logging.papertrail.excluded_log_files"]
        if logfile in excluded:
            return
        else:
            log(f"Streaming {logfile} to papertrail")
            stream_logger.info(f"-> {logfile}")
            for line in tail_f(logfile):
                stream_logger.info(line)

    printers.append(papertrail_printer)


log_watcher(printers)
