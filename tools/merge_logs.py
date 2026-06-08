#!/usr/bin/env python
#
# Blend log files, keeping events in order.
#

import sys
import re
from datetime import datetime


if len(sys.argv) < 2:
    print("Usage: log_parse.py filename0.log filename1.log ...")
    sys.exit(1)


# 7-bit C1 ANSI sequences
# https://stackoverflow.com/a/14693789
ansi_escape = re.compile(r'''
    \x1B  # ESC
    (?:   # 7-bit C1 Fe (except CSI)
        [@-Z\\-_]
    |     # or [ for CSI, followed by a control sequence
        \[
        [0-?]*  # Parameter bytes
        [ -/]*  # Intermediate bytes
        [@-~]   # Final byte
    )
''', re.VERBOSE)

RE = '\[(?P<time>[0-9]{2}:[0-9]{2}:[0-9]{2}) (?P<name>.*?)\] (?P<message>.*)'

def parse(f):
    for line in f:
        line = ansi_escape.sub('', line)
        m = re.match(RE, line)
        if m:
            fields = m.groupdict()
            fields['time'] = datetime.strptime(fields['time'], '%H:%M:%S')
            yield fields


all_events = []
for fn in sys.argv[1:]:
    with open(fn, 'r') as f:
        all_events.extend(list(parse(f)))

all_events = sorted(all_events, key=lambda fields: fields['time'])
for event in all_events:
    print(f"[{event['time'].strftime('%H:%M:%S')} {event['name']}] {event['message']}")
