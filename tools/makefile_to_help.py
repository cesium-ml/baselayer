"""
Convert any ## style comments after a Makefile target into help text.

Usage: makefile_to_help.py <MAKEFILE0> <MAKEFILE1> ...

The Makefile can also be preceded by a category, e.g.

  makefile_to_help.py Main:Makefile External:submodule/Makefile

in which case the category names are printed as a heading before the targets.

A target described in several makefiles is listed once, under the last category
that defines it.

"""

import re
import sys


def parse_targets(fname):
    with open(fname) as f:
        matches = (re.match(r"^([\w-]+): +##(.*)", line) for line in f)
        return {m[1]: m[2] for m in matches if m}


sections = []
for source in sys.argv[1:]:
    category, fname = source.split(":") if ":" in source else (None, source)
    sections.append((category, parse_targets(fname)))

seen = set()
for _, targets in reversed(sections):
    for target in seen.intersection(targets):
        del targets[target]
    seen.update(targets)

width = max((len(target) for _, targets in sections for target in targets), default=0)

for category, targets in sections:
    if category:
        print(f"\n{category}\n{'-' * len(category)}")
    for target, desc in targets.items():
        print(f"{target:{width}} {desc}")
