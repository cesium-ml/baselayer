"""
Convert any ## style comments after a Makefile target into help text.
"""

import sys
import re

if not sys.argv:
    print("Usage: makefile_to_help.py <MAKEFILE0> <MAKEFILE1> ...")
    sys.exit(0)

lines = []
for fname in sys.argv[1:]:
    with open(fname) as f:
        lines.extend(f.readlines())

matches = [re.match('^([\w-]+): +##(.*)', line) for line in lines]
groups = [m.groups(0) for m in matches if m]
targets = {target: desc for (target, desc) in groups}

N = max(len(target) for (target, desc) in targets.items())

for (target, desc) in targets.items():
    print(f'{target:{N}} {desc}')
