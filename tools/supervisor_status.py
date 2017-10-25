#!/usr/bin/env python

import subprocess
import os
import sys
from os.path import join as pjoin

base_dir = os.path.abspath(pjoin(os.path.dirname(__file__), '../..'))


def supervisor_status():
    result = subprocess.run(
        'supervisorctl -c baselayer/conf/supervisor/supervisor.conf status',
        shell=True, cwd=base_dir, check=True,
        stdout=subprocess.PIPE
    )
    return result.stdout.decode().split('\n')[:-1]


if __name__ == '__main__':
    print('\n'.join(supervisor_status()))
