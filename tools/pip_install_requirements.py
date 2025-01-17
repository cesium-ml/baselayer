import subprocess
import sys

from packaging.requirements import Requirement
import importlib
import importlib.metadata

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


class IncompatibleVersionError(Exception):
    pass

try:
    with status("Verifying Python package dependencies"):
        for rspec in requirements:
            req = Requirement(rspec.strip().split("#egg=")[-1].replace('==', '~='))
            name = req.name
            version_specifier = req.specifier
            version_installed = importlib.metadata.version(name)

            if not version_specifier.contains(version_installed):
                raise IncompatibleVersionError(f'Need {name} {version_specifier} but found {version_installed}')

except importlib.metadata.PackageNotFoundError: #
    print(f'[!] Package `{name}` not found; refreshing dependencies')
except IncompatibleVersionError as e:
    print(f'[!] {e}')
else:
    sys.exit(0)

pip(all_req_files)
