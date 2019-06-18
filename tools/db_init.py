#!/usr/bin/env python

import subprocess
import sys
import argparse
import textwrap
import requests
import tempfile
import tarfile
from pathlib import Path
import os

from uuid import uuid4
from baselayer.app.env import load_env


from status import status


parser = argparse.ArgumentParser(
    description='Create or re-create the database.'
)
parser.add_argument('-f', '--force', action='store_true',
                    help='recreate the db, even if it already exists')
args, unknown = parser.parse_known_args()

env, cfg = load_env()

db = cfg['database:database']
all_dbs = (db, db + '_test')

user = cfg['database:user'] or db
host = cfg['database:host']
port = cfg['database:port']
password = cfg['database:password']

psql_cmd = 'psql'
flags = f'-U {user}'

if password:
    psql_cmd = f'PGPASSWORD="{password}" {psql_cmd}'
flags += f' --no-password'

if host:
    flags += f' -h {host}'

if port:
    flags += f' -p {port}'


def run(cmd, check=False):
    return subprocess.run(cmd,
                          stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE,
                          shell=True, check=check)


def test_db(database):
    test_cmd = f"{psql_cmd} {flags} -c 'SELECT 0;' {database}"
    p = run(test_cmd)

    try:
        with status('Testing database connection'):
            if not p.returncode == 0:
                raise RuntimeError()
    except:
        print(textwrap.dedent(
            f'''
             !!! Error accessing database:

             The most common cause of database connection errors is a
             misconfigured `pg_hba.conf`.

             We tried to connect to the database with the following parameters:

               database: {db}
               username: {user}
               host:     {host}
               port:     {port}

             The postgres client exited with the following error message:

             {'-' * 78}
             {p.stderr.decode('utf-8').strip()}
             {'-' * 78}

             Please modify your `pg_hba.conf`, and use the following command to
             check your connection:

               {test_cmd}
            '''))

        sys.exit(1)


plat = run('uname').stdout
if b'Darwin' in plat:
    print('* Configuring MacOS postgres')
    sudo = ''
else:
    print('* Configuring Linux postgres [may ask for sudo password]')
    sudo = 'sudo -u postgres'

# Ask for sudo password here so that it is printed on its own line
# (better than inside a `with status` section)
run(f'{sudo} echo -n')

with status(f'Creating user {user}'):
    run(f'{sudo} createuser --superuser {user}')

if args.force:
    try:
        with status('Removing existing databases'):
            for current_db in all_dbs:
                p = run(f'{sudo} dropdb {current_db}')
                if p.returncode != 0:
                    raise RuntimeError()
    except:
        print('Could not delete database: \n\n'
              f'{textwrap.indent(p.stderr.decode("utf-8").strip(), prefix="  ")}\n')
        sys.exit(1)

with status(f'Creating databases'):


    for current_db in all_dbs:
        run(f'{sudo} createdb -w {current_db}')
        run(f'{sudo} createdb -w {current_db}')
        run(f'psql {flags}\
              -c "GRANT ALL PRIVILEGES ON DATABASE {current_db} TO {user};"\
              {current_db}', check=True)

        # check if q3c is installed
        result = run(f'{sudo} psql {flags} -c "\dx"')
        out = str(result.stdout)
        q3c_installed = 'q3c' in out

        if not q3c_installed:
            r = requests.get('https://github.com/segasai/q3c/archive/v1.8.0.tar.gz')

            with tempfile.NamedTemporaryFile() as f:
                f.write(r.content)
                f.seek(0)
                q3cpath = Path(f'/tmp/{uuid4().hex}')
                q3cpath.mkdir(exist_ok=True, parents=True)

                with tarfile.open(f.name) as tar:
                    tar.extractall(q3cpath)

                pwd = os.getcwd()
                os.chdir(q3cpath / 'q3c-1.8.0')
                run(f'{sudo} make', check=True)
                run(f'{sudo} make install', check=True)
                os.chdir(pwd)

                run(f'psql {flags} -c "CREATE EXTENSION Q3C"', check=True)


test_db(db)
