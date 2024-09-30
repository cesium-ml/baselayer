#!/usr/bin/env python

import os
import subprocess
from os.path import join as pjoin

base_dir = os.path.abspath(pjoin(os.path.dirname(__file__), "../.."))


def supervisor_status():
    """Check status of all services.

    Returns
    -------
    list
        The output lines from ``supervisorctl``.
    int
        Return code of ``supervisorctl``.  This will be 0 for all
        services running, or 3 if one of them exited (note: this is
        expected when, e.g., rspack exits normally).
    """
    result = subprocess.run(
        "python -m supervisor.supervisorctl -c baselayer/conf/supervisor/supervisor.conf status",
        shell=True,
        cwd=base_dir,
        stdout=subprocess.PIPE,
    )
    return result.stdout.decode().split("\n")[:-1], result.returncode


if __name__ == "__main__":
    supervisor_output, _ = supervisor_status()
    print("\n".join(supervisor_output))
