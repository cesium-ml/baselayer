# encoding: utf-8

import subprocess
import sys

from baselayer.app.env import load_env, parser
from baselayer.log import make_log

parser.description = 'Launch TypeScript compiler microservice'

env, cfg = load_env()

log = make_log('service/tsc')


def run(cmd):
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    for line in proc.stdout:
        log(f'{line.decode().strip()}')
    return proc


if env.debug:
    log("debug mode detected, launching tsc in watch mode")
    p = run(['npx', 'tsc', '--watch'])
    sys.exit(p.returncode)
else:
    log("Transpiling TypeScript sources")
    p = run(['npx', 'tsc'])
    sys.exit(p.returncode)
