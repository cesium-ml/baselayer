#!/usr/bin/env python

import os
from os.path import join as pjoin
import pathlib
import sys
import signal
import socket
import subprocess
import time

sys.path.insert(0, pjoin(os.path.dirname(__file__), '../..'))  # noqa

from baselayer.tools.supervisor_status import supervisor_status
try:
    import http.client as http
except ImportError:
    import httplib as http

from baselayer.app.model_util import clear_tables

try:
    import pytest_randomly  # noqa
    RAND_ARGS = '--randomly-seed=1'
except ImportError:
    RAND_ARGS = ''

TEST_CONFIG = 'test_config.yaml'


if __name__ == '__main__':
    # Initialize the test database connection
    from baselayer.app.models import init_db
    from baselayer.app.config import load_config
    basedir = pathlib.Path(os.path.dirname(__file__))/'..'/'..'
    cfg = load_config([basedir/'config.yaml.defaults', basedir/TEST_CONFIG])
    init_db(**cfg['database'])

    if len(sys.argv) > 1:
        test_spec = sys.argv[1]
    else:
        app_name = cfg['app:factory'].split('.')[0]
        test_spec = basedir/app_name/'tests'

    clear_tables()

    web_client = subprocess.Popen(['make', '-C', 'baselayer', 'run_testing'],
                                  cwd=basedir, preexec_fn=os.setsid)

    print('[test_frontend] Waiting for supervisord to launch all server '
          'processes...')

    def all_services_running():
        return all([b'RUNNING' in line for line in supervisor_status()])

    try:
        timeout = 0
        while (timeout < 30) and not all_services_running():
            time.sleep(1)
            timeout += 1

        if timeout == 10:
            print('[test_frontend] Could not launch server processes; '
                  'terminating')
            sys.exit(-1)

        for timeout in range(10):
            conn = http.HTTPConnection("localhost", cfg['ports:app'])
            try:
                conn.request('HEAD', '/')
                status = conn.getresponse().status
                if status == 200:
                    break
            except socket.error:
                pass
            time.sleep(1)
        else:
            raise socket.error("Could not connect to "
                               f"localhost:{cfg['ports:app']}.")

        if status != 200:
            print('[test_frontend] Server status is {} instead of 200'.format(
                status))
            sys.exit(-1)
        else:
            print('[test_frontend] Verified server availability')

        print('[test_frontend] Launching pytest on {}...'.format(test_spec))

        status = subprocess.run(f'python -m pytest -v {test_spec} {RAND_ARGS}',
                                shell=True, check=True)
    except:
        raise
    finally:
        print('[test_frontend] Terminating supervisord...')
        os.killpg(os.getpgid(web_client.pid), signal.SIGTERM)
