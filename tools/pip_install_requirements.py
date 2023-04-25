import subprocess
import sys

import pkg_resources
from pkg_resources import DistributionNotFound, Requirement, VersionConflict
from pkg_resources.extern.packaging.requirements import InvalidRequirement
from status import status

if len(sys.argv) < 2:
    print(
        "Usage: pip_install_requirements.py requirements.txt [requirements_other.txt]"
    )
    sys.exit(0)

requirements = []
all_req_files = sys.argv[1:]
for req_file in all_req_files:
    with open(req_file) as f:
        requirements.extend(f.readlines())


def pip(req_files):
    args = ["pip", "install"]
    for req_file in req_files:
        args.extend(["-r", req_file])
    p = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    for line in iter(p.stdout.readline, b""):
        line = line.decode("utf-8")
        if line.startswith("Requirement already satisfied"):
            continue
        print(line, end="")

    retcode = p.wait()
    if retcode != 0:
        sys.exit(retcode)


try:
    with status("Verifying Python package dependencies"):
        parsed_requirements = []
        for r in requirements:
            try:
                parsed_requirements.append(Requirement.parse(r))
            except InvalidRequirement:
                print(f"\r[?] Ensure {r} is installed")
        pkg_resources.working_set.resolve(parsed_requirements)

except (DistributionNotFound, VersionConflict) as e:
    print(e.report())
    pip(all_req_files)
