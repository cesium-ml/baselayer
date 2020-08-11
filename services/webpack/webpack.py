# encoding: utf-8

import subprocess
import sys
import time
import os
from pathlib import Path

from baselayer.app.env import load_env
from baselayer.log import make_log

env, cfg = load_env()

bundle = Path(os.path.dirname(__file__)) / '../../static/build/main.bundle.js'

log = make_log('service/webpack')


def run(cmd):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    for line in p.stdout:
        log(f'{line.decode().strip()}')
    return p


if env.debug:
    log("debug mode detected, launching webpack monitor")
    p = run(['npx', 'webpack', '--watch'])
    sys.exit(p.returncode)

elif bundle.is_file():
    log("main.bundle.js already built, exiting")
    # Run for a few seconds so that supervisor knows the service was
    # successful
    time.sleep(3)
    sys.exit(0)

else:
    log("main.bundle.js not found, building")
    p = run(['npx', 'webpack'])
    time.sleep(1)
    sys.exit(p.returncode)
