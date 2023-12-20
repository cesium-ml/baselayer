#!/usr/bin/env python
import os
import subprocess
import sys
import textwrap
from distutils.version import LooseVersion as Version

from status import status


def output(cmd):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out, err = p.communicate()
    success = p.returncode == 0
    return success, out


deps = {
    "nginx": (
        # Command to get version
        ["nginx", "-v"],
        # Extract *only* the version number
        lambda v: v.split()[2].split("/")[1],
        # It must be >= 1.7
        "1.7",
    ),
    "psql": (
        ["psql", "--version"],
        lambda v: v.split("\n")[-1].split()[2],
        "12.0",
    ),
    "npm": (["npm", "-v"], lambda v: v, "8.3.2"),
    "node": (["node", "-v"], lambda v: v[1:], "16.14.0"),
    "python": (["python", "--version"], lambda v: v.split()[1], "3.8"),
}

print("Checking system dependencies:")

fail = []

for dep, (cmd, get_version, min_version) in deps.items():
    try:
        query = f"{dep} >= {min_version}"
        with status(query):
            success, out = output(cmd)
            try:
                version = get_version(out.decode("utf-8").strip())
                print(f"[{version.rjust(8)}]".rjust(40 - len(query)), end="")
            except:  # noqa: E722
                raise ValueError("Could not parse version")

            if not (Version(version) >= Version(min_version)):
                raise RuntimeError(f"Required {min_version}, found {version}")
    except ValueError:
        print(
            f"\n[!] Sorry, but our script could not parse the output of "
            f'`{" ".join(cmd)}`; please file a bug, or see '
            f"`check_app_environment.py`\n"
        )
        raise
    except Exception as e:
        fail.append((dep, e))

if fail:
    print()
    print("[!] Some system dependencies seem to be unsatisfied")
    print()
    print("    The failed checks were:")
    print()
    for pkg, exc in fail:
        cmd, get_version, min_version = deps[pkg]
        print(f'    - {pkg}: `{" ".join(cmd)}`')
        print("     ", exc)
    print()
    print(
        "    Please refer to https://cesium-ml.org/baselayer "
        "for installation instructions."
    )
    print()
    sys.exit(-1)

print()
try:
    with status("Baselayer installed inside of app"):
        if not (
            os.path.exists("config.yaml") or os.path.exists("config.yaml.defaults")
        ):
            raise RuntimeError()
except RuntimeError:
    print(
        textwrap.dedent(
            """
          It does not look as though baselayer is deployed as
          part of an application.

          Please see

            https://github.com/cesium-ml/baselayer_template_app

          for an example application.
    """
        )
    )
    sys.exit(-1)

print("-" * 20)
