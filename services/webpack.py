# encoding: utf-8

from baselayer.app.env import load_env
import subprocess
import sys
import time

env, cfg = load_env()

if env.debug:
    print("[service/webpack]: debug mode detected, launching")
    p = subprocess.Popen(
        ['./node_modules/.bin/webpack', '--watch'],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    for line in p.stdout:
        print(line.decode(), end="")
        sys.stdout.flush()
else:
    print("[service/webpack]: not in debug mode, exiting")

    # Run for a few seconds so that supervisor knows the service was
    # successful
    time.sleep(3)
