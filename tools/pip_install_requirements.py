import pkg_resources
from pkg_resources import DistributionNotFound, VersionConflict

import sys
import subprocess
from status import status


if len(sys.argv) < 2:
    print('Usage: pip_install_requirements.py requirements.txt [requirements_other.txt]')
    sys.exit(0)

requirements = []
for req_file in sys.argv[1:]:
    with open(req_file, 'r') as f:
        requirements.extend(f.readlines())

try:
    with status('Verifying Python package dependencies'):
        pkg_resources.require(requirements)

except (DistributionNotFound, VersionConflict) as e:
    print(e.report())
    p = subprocess.Popen(['pip', 'install', '-r', req_file],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for line in iter(p.stdout.readline, b''):
        line = line.decode('utf-8')
        if line.startswith('Requirement already satisfied'):
            continue
        print(line, end='')
    sys.exit(p.wait())
