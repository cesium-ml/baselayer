#!/usr/bin/env python


import argparse
import sys
from collections import defaultdict
from xml.etree import ElementTree as ET

from baselayer.log import colorize


def etree_to_dict(t):
    d = {t.tag: {} if t.attrib else None}
    children = list(t)
    if children:
        dd = defaultdict(list)
        for dc in map(etree_to_dict, children):
            for k, v in dc.items():
                dd[k].append(v)
        d = {t.tag: {k: v[0] if len(v) == 1 else v for k, v in dd.items()}}
    if t.attrib:
        d[t.tag].update(("@" + k, v) for k, v in t.attrib.items())
    if t.text:
        text = t.text.strip()
        if children or t.attrib:
            if text:
                d[t.tag]["#text"] = text
        else:
            d[t.tag] = text
    return d


parser = argparse.ArgumentParser(description="Generate a failure report from JUnitXML")
parser.add_argument("filename", help="JUnit XML file to parse (produced by pytest)")
args = parser.parse_args()


try:
    data = open(args.filename).read()
except FileNotFoundError:
    print(f"Could not open JUnitXML file [{args.filename}]")
    sys.exit(-1)

xml = ET.XML(data)
json = etree_to_dict(xml)

tests = json["testsuites"]["testsuite"]["testcase"]

for test in tests:
    if "failure" in test:
        message = test["failure"]["@message"]
        text = test["failure"]["#text"]

        filename = test["@classname"].replace(".", "/") + ".py"
        test_name = test["@name"]

        first_error = []
        for line in text.split("\n"):
            if line.startswith("_ _ _ _"):
                break
            first_error.append(line)

        error_line = next(
            n for (n, line) in enumerate(first_error) if line.startswith(">")
        )
        N = 3
        cmin = max(0, error_line - N)
        cmax = error_line + N
        first_error_context = first_error[cmin:cmax]
        lineno = first_error[-1].split(":")[-2]

        print("-" * 80)
        print(colorize("FAIL: ", fg="yellow", bold=True), end="")
        print(colorize(f"{filename}:{lineno}", fg="red"), end="")
        print(" in ", end="")
        print(colorize(test_name, fg="red", bold=True))
        print()
        print("\n".join(first_error_context))

        print()
        print(
            colorize("EDIT:", fg="green"),
        )
        print(f"  $EDITOR +{lineno} {filename}")
        print("-" * 80)
