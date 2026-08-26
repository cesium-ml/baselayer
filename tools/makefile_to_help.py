"""
Convert any ## style comments after a Makefile target into help text.

Usage: makefile_to_help.py <MAKEFILE0> <MAKEFILE1> ...

The Makefile can also be preceded by a category, e.g.

  makefile_to_help.py Main:Makefile External:submodule/Makefile

in which case the category names are printed as a heading before the targets.

A target described in several makefiles is listed once, with the description of
the last one that defines it, under its own heading named after that last
category, e.g. "App-overrides".

"""

import re
import sys
from collections import Counter


def parse_targets(fname):
    with open(fname) as f:
        matches = (re.match(r"^([\w-]+): +##(.*)", line) for line in f)
        return {m[1]: m[2] for m in matches if m}


sections = []
for source in sys.argv[1:]:
    category, fname = source.split(":") if ":" in source else (None, source)
    sections.append((category, parse_targets(fname)))

counts = Counter(target for _, targets in sections for target in targets)
kept, overrides = [], {}
for category, targets in sections:
    kept.append((category, {t: d for t, d in targets.items() if counts[t] == 1}))
    overrides.update({t: d for t, d in targets.items() if counts[t] > 1})

if overrides:
    category = sections[-1][0]
    kept.insert(1, (f"{category}-overrides" if category else "Overrides", overrides))

width = max((len(target) for _, targets in kept for target in targets), default=0)

for category, targets in kept:
    if category:
        print(f"\n{category}\n{'-' * len(category)}")
    for target, desc in targets.items():
        print(f"{target:{width}} {desc}")
