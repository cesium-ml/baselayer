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

for line in lines:
    match = re.match('^(\w+): +##(.*)', line)
    if match:
        target, desc = match.groups()
        print(f'{target:15} {desc}')
