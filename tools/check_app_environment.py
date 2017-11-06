#!/usr/bin/env python
from status import status

import os
import sys
import subprocess
import textwrap


def output(cmd):
    p = subprocess.Popen(cmd,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = p.communicate()
    success = p.returncode == 0
    return success, out, err

deps = {
    'nginx': ['nginx', '-v'],
    'supervisord': ['supervisord', '-v'],
    'psql': ['psql', '--version'],
    'node (npm)': ['npm', '-v']
}

print('Checking system dependencies:')

fail = []

for dep, cmd in deps.items():
    try:
        with status(dep):
            success, out, err = output(cmd)
    except:
        fail.append(dep)

if fail:
    print()
    print('[!] Some system dependencies seem to be unsatisfied')
    print()
    print('    The failed checks were:')
    print()
    for pkg in fail:
        print(f'    - {pkg}: `{" ".join(deps[pkg])}`')
    print()
    print('    Please refer to https://cesium-ml.org/baselayer')
    print('      for installation instructions.')
    print()
    sys.exit(-1)

print()
try:
    with status('Baselayer installed inside of app'):
        if not (os.path.exists('../config.yaml') or
                os.path.exists('../config.yaml.defaults')):
            raise RuntimeError()
except:
    print(textwrap.dedent('''
          It does not look as though baselayer is deployed as
          part of an application.

          Please see

            https://github.com/cesium-ml/baselayer_template_app

          for an example application.
    '''))
    sys.exit(-1)

print('-' * 20)
