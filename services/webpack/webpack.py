# encoding: utf-8

import subprocess
import sys
import time
import os
from pathlib import Path

from baselayer.app.env import load_env, parser
from baselayer.log import make_log

parser.description = "Launch webpack microservice"

env, cfg = load_env()

log = make_log("service/webpack")


def run(cmd):
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    for line in proc.stdout:
        log(f"{line.decode().strip()}")
    return proc


if env.debug:
    log("debug mode detected, launching webpack monitor")
    p = run(["npx", "webpack", "--watch"])
    sys.exit(p.returncode)
else:
    log("Rebuilding main JavaScript bundle")
    p = run(["npx", "webpack", "--mode=production"])
    sys.exit(p.returncode)
