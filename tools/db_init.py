#!/usr/bin/env python

import subprocess
import sys
import argparse
import textwrap
from baselayer.app.env import load_env

from status import status


parser = argparse.ArgumentParser(description='Create or re-create the database.')
parser.add_argument(
    '-f',
    '--force',
    action='store_true',
    help='recreate the db, even if it already exists',
)
parser.add_argument(
    '--no-sudo',
    action='store_true',
    help='Do not use `sudo -U username` when accessing the database'
)
args, unknown = parser.parse_known_args()

env, cfg = load_env()

db = cfg['database.database']
all_dbs = (db, db + '_test')

user = cfg['database.user'] or db
host = cfg['database.host']
port = cfg['database.port']
password = cfg['database.password']

psql_cmd = 'psql'
flags = f'-U {user}'

if password:
    psql_cmd = f'PGPASSWORD="{password}" {psql_cmd}'
flags += f' --no-password'

if host:
    flags += f' -h {host}'

if port:
    flags += f' -p {port}'

test_cmd = f"{psql_cmd} {flags} -c 'SELECT 0;' "


def run(cmd):
    return subprocess.run(cmd,
                          capture_output=True,
                          shell=True)


def test_db(database):
    p = run(test_cmd + database)
    return (p.returncode == 0)


if not args.no_sudo:
    sudo = 'sudo -u postgres'
    print('\nUsing `sudo` by default. You will be prompted for your password.')
    print('  Run with `--no-sudo` to disable.\n')
else:
    sudo = ''

# Ask for sudo password here so that it is printed on its own line
# (better than inside a `with status` section)
run(f'{sudo} echo -n')

with status(f'Creating user {user}'):
    run(f'{sudo} createuser {user}')

if args.force:
    try:
        with status('Removing existing databases'):
            for current_db in all_dbs:
                p = run(f'{sudo} dropdb {current_db}')
                if p.returncode != 0:
                    raise RuntimeError()
    except RuntimeError:
        print('Could not delete database: \n\n'
              f'{textwrap.indent(p.stderr.decode("utf-8").strip(), prefix="  ")}\n')
        sys.exit(1)

with status(f'Creating databases'):
    for current_db in all_dbs:
        # We allow this to fail, because oftentimes because of complicated db setups
        # users want to create their own databases

        if test_db(current_db):
            continue

        p = run(f'{sudo} createdb -w {current_db}')
        if p.returncode == 0:
            run(f'{psql_cmd} {flags}\
              -c "GRANT ALL PRIVILEGES ON DATABASE {current_db} TO {user};"\
              {current_db}')
        else:
            print()
            print(f'Warning: could not create db {current_db}')
            print()
            print('\n'.join(line for line in p.stderr.decode('utf-8').split('\n') if 'ERROR' in line))
            print()
            print('  You should create it manually by invoking `createdb`.')
            print('  Then, execute:')
            print()
            print(f'    {psql_cmd} {flags}'
                  f' -c "GRANT ALL PRIVILEGES ON DATABASE {current_db} TO {user};"'
                  f' {current_db}')
            print()

try:
    with status('Testing database connection'):
        if not test_db(db):
            raise RuntimeError()
except RuntimeError:
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

           {test_cmd + db}
        '''))
    sys.exit(1)
