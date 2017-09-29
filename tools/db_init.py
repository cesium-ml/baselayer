#!/usr/bin/env python

import subprocess
import sys
import glob
import os
import argparse
import textwrap
from baselayer.app.config import load_config

from status import status


parser = argparse.ArgumentParser(description='Create or re-create the database.')
parser.add_argument('-f', '--force', action='store_true',
                    help='recreate the db, even if it already exists')
args = parser.parse_args()


cfg = load_config()

db = cfg['database:database']
all_dbs = (db, db + '_test')

user = cfg['database:user'] or db
host = cfg['database:host']
port = cfg['database:port']

flags = f'-U {user}'

if host:
    flags += f' -h {host}'

if port:
    flags += f' -p {port}'


def run(cmd):
    return subprocess.run(cmd,
                          stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE,
                          shell=True)

def test_db(database):
    test_cmd = f"psql {flags} -c 'SELECT 0;' {database}"
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
    print('Configuring MacOS postgres')
    sudo = ''
else:
    print('Configuring Linux postgres')
    sudo = 'sudo -u postgres'

with status(f'Creating user {user}'):
    run(f'{sudo} createuser {user}')

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
              {current_db}')

test_db(db)
