#!/usr/bin/env python

import os
import pathlib
import signal
import subprocess
import sys
import time
from os.path import join as pjoin

import requests

sys.path.insert(0, pjoin(os.path.dirname(__file__), "../.."))  # noqa

from baselayer.app.model_util import clear_tables  # noqa: E402
from baselayer.log import make_log  # noqa: E402
from baselayer.tools.supervisor_status import supervisor_status  # noqa: E402

log = make_log("test_frontend")


try:
    import pytest_randomly  # noqa

    RAND_ARGS = "--randomly-seed=1"
except ImportError:
    RAND_ARGS = ""

TEST_CONFIG = "test_config.yaml"


def all_services_running():
    """Check that all webservices were started successfully.

    All webservices controlled by `supervisor` must be currently running
    (RUNNING) or have finished successfully (EXITED). Returns `False` if any
    other statuses (STARTING, STOPPED, etc.) are present.
    """
    valid_states = ("RUNNING", "EXITED")
    supervisor_output, return_code = supervisor_status()
    running = all(
        [any(state in line for state in valid_states) for line in supervisor_output]
    )

    # Return 3 is associated with a service exiting normally
    return running if return_code in (0, 3) else False


def verify_server_availability(url, timeout=180):
    """Raise exception if webservices fail to launch or connection to `url` is not
    available.
    """
    for i in range(timeout):
        if not os.path.exists("baselayer/conf/supervisor/supervisor.conf"):
            time.sleep(1)
            continue
        try:
            statuses, errcode = supervisor_status()
            assert (
                all_services_running()
            ), "Webservice(s) failed to launch:\n" + "\n".join(statuses)
            response = requests.get(url)
            assert response.status_code == 200, (
                "Expected status 200, got" f" {response.status_code}" f" for URL {url}."
            )
            response = requests.get(url + "/static/build/main.bundle.js")
            assert response.status_code == 200, (
                "Javascript bundle not found," " did Webpack fail?"
            )
            return  # all checks passed
        except Exception as e:
            if i == timeout - 1:  # last iteration
                raise ConnectionError(str(e)) from None
        time.sleep(1)


if __name__ == "__main__":
    from argparse import ArgumentParser

    parser = ArgumentParser()
    parser.add_argument(
        "test_spec",
        nargs="?",
        default=None,
        help="""Test spec. Example:
    test_frontend.py skyportal/tests/api
""",
    )
    parser.add_argument(
        "--xml",
        action="store_true",
        help="Save JUnit xml output to `test-results/junit.xml`",
    )
    parser.add_argument(
        "--headless", action="store_true", help="Run browser headlessly"
    )
    args = parser.parse_args()

    # Initialize the test database connection
    log("Connecting to test database")
    from baselayer.app.config import load_config
    from baselayer.app.models import init_db

    basedir = pathlib.Path(os.path.dirname(__file__)) / ".." / ".."
    cfg = load_config([basedir / TEST_CONFIG])
    app_name = cfg["app.factory"].split(".")[0]
    engine = init_db(**cfg["database"])
    engine.connect()

    if args.test_spec is not None:
        test_spec = args.test_spec
    else:
        test_spec = basedir / app_name / "tests"

    if args.xml:
        test_outdir = basedir / "test-results"
        if not test_outdir.exists():
            test_outdir.mkdir()
        xml = f"--junitxml={test_outdir}/junit.xml"
    else:
        xml = ""

    if args.headless:
        os.environ["BASELAYER_TEST_HEADLESS"] = "1"

    log("Clearing test database...")
    clear_tables()

    web_client = subprocess.Popen(
        ["make", "run_testing"], cwd=basedir, preexec_fn=os.setsid
    )

    server_url = f"http://localhost:{cfg['ports.app']}"
    print()
    log(f"Waiting for server to appear at {server_url}...")

    exit_status = (0, "OK")
    try:
        verify_server_availability(server_url)

        log(f"Launching pytest on {test_spec}...\n")
        p = subprocess.run(
            f"python -m pytest -s -v {xml} {test_spec} " f"{RAND_ARGS}",
            shell=True,
        )
        if p.returncode != 0:
            exit_status = (-1, "Test run failed")

            p = subprocess.run(
                ["make", "-f", "baselayer/Makefile", "test_report"], cwd=basedir
            )

    except Exception as e:
        log("Could not launch server processes; terminating")
        print(e)
        exit_status = (-1, "Failed to launch pytest")
    finally:
        log("Terminating supervisord...")
        os.killpg(os.getpgid(web_client.pid), signal.SIGTERM)

    code, msg = exit_status
    log(msg)
    sys.exit(code)
