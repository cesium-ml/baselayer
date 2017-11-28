#!/usr/bin/env python

import os
from os.path import join as pjoin
import pathlib
import requests
import sys
import signal
import socket
import subprocess
import time

sys.path.insert(0, pjoin(os.path.dirname(__file__), '../..'))  # noqa

from baselayer.tools.supervisor_status import supervisor_status

from baselayer.app.model_util import clear_tables

try:
    import pytest_randomly  # noqa
    RAND_ARGS = '--randomly-seed=1'
except ImportError:
    RAND_ARGS = ''

TEST_CONFIG = 'test_config.yaml'


def all_services_running():
    """Check that all webservices were started successfully.

    All webservices controlled by `supervisor` must be currently running
    (RUNNING) or have finished successfully (EXITED). Returns `False` if any
    other statuses (STARTING, STOPPED, etc.) are present.
    """
    return all(['RUNNING' in line or 'EXITED' in line
                for line in supervisor_status()])


def verify_server_availability(url, timeout=60):
    """Raise exception if webservices fail to launch or connection to `url` is not
    available.
    """
    for i in range(timeout):
        try:
            assert all_services_running(), ("Webservice(s) failed to launch:\n"
                                            + '\n'.join(supervisor_status()))
            response = requests.get(url)
            assert response.status_code == 200, ("Expected status 200, got"
                                                 f" {response.status_code}"
                                                 f" for URL {url}.")
            response = requests.get(url + '/static/build/bundle.js')
            assert response.status_code == 200, ("Javascript bundle not found,"
                                                 " did Webpack fail?")
            return  # all checks passed
        except Exception as e:
            if i == max(range(timeout)):  # last iteration
                raise ConnectionError(str(e)) from None
        time.sleep(1)


if __name__ == '__main__':
    # Initialize the test database connection
    from baselayer.app.models import init_db
    from baselayer.app.config import load_config
    basedir = pathlib.Path(os.path.dirname(__file__))/'..'/'..'
    cfg = load_config([basedir/TEST_CONFIG])
    init_db(**cfg['database'])

    if len(sys.argv) > 1:
        test_spec = sys.argv[1]
    else:
        app_name = cfg['app:factory'].split('.')[0]
        test_spec = basedir/app_name/'tests'

    clear_tables()

    web_client = subprocess.Popen(['make', 'run_testing'],
                                  cwd=basedir, preexec_fn=os.setsid)

    print('[test_frontend] Waiting for supervisord to launch all server '
          'processes...')

    try:
        verify_server_availability(f"http://localhost:{cfg['ports:app']}")
        print('[test_frontend] Verified server availability')
        print('[test_frontend] Launching pytest on {}...'.format(test_spec))
        status = subprocess.run(f'python -m pytest -v {test_spec} {RAND_ARGS}',
                                shell=True, check=True)
    except Exception as e:
        print('[test_frontend] Could not launch server processes; '
              'terminating')
        print(e)
        raise
    finally:
        print('[test_frontend] Terminating supervisord...')
        os.killpg(os.getpgid(web_client.pid), signal.SIGTERM)
