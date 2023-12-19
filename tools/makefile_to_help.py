"""
Convert any ## style comments after a Makefile target into help text.

Usage: makefile_to_help.py <MAKEFILE0> <MAKEFILE1> ...

The Makefile can also be preceded by a category, e.g.

  makefile_to_help.py Main:Makefile External:submodule/Makefile

in which case the category names are printed as a heading before the targets.

"""

import re
import sys

if not sys.argv:
    print("Usage: makefile_to_help.py <MAKEFILE0> <MAKEFILE1> ...")
    sys.exit(0)


def describe_targets(lines):
    matches = [re.match(r"^([\w-]+): +##(.*)", line) for line in lines]
    groups = [m.groups(0) for m in matches if m]
    targets = {target: desc for (target, desc) in groups}

    N = max(len(target) for (target, desc) in targets.items())

    for target, desc in targets.items():
        print(f"{target:{N}} {desc}")


for source in sys.argv[1:]:
    if ":" in source:
        category, fname = source.split(":")
        print(f'\n{category}\n{"-" * len(category)}')
    else:
        fname = source

    describe_targets(open(fname).readlines())
