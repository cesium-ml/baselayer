# encoding: utf-8

from baselayer.app.env import load_env
import subprocess
import sys
import time
import os
from pathlib import Path

env, cfg = load_env()

bundle = Path(os.path.dirname(__file__))/'../../static/build/bundle.js'

def run(cmd):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    for line in p.stdout:
        print(f'[service/webpack] {line.decode()}', end="")
        sys.stdout.flush()
    return p

if env.debug:
    print("[service/webpack]: debug mode detected, launching webpack monitor")
    p = run(['./node_modules/.bin/webpack', '--watch'])
    sys.exit(p.returncode)

elif bundle.is_file():
    print("[service/webpack]: bundle.js already built, exiting")
    # Run for a few seconds so that supervisor knows the service was
    # successful
    time.sleep(3)
    sys.exit(0)

else:
    print("[service/webpack]: bundle.js not found, building")
    p = run(['./node_modules/.bin/webpack'])
    time.sleep(1)
    sys.exit(p.returncode)
