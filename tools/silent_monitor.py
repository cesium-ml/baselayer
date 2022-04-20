#!/usr/bin/env python

import shlex
import subprocess
import sys

if len(sys.argv) < 2:
    print("Usage: silent_monitor.py <cmd to execute>")
    sys.exit()

cmd = " ".join(sys.argv[1:])

tag = f"Silently executing: {cmd}"
print(f"[·] {tag}", end="")
sys.stdout.flush()

p = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE)

err = p.wait()
stdout, stderr = p.stderr.read().strip(), p.stdout.read().strip()

if err == 0:
    print(f"\r[✓] {tag}")
else:
    print(f"\r[✗] {tag}")
    print(f"\n! Failure (exit code {err}).")

    if stdout:
        print("--- stdout ---")
        print(stdout.decode("utf-8"))

    if stderr:
        print("--- stderr ---")
        print(stderr.decode("utf-8"))

    if stdout or stderr:
        print("--- end ---")

    sys.exit(err)
