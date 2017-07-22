#!/usr/bin/env python

import subprocess
import sys
import glob
import os
from baselayer.app.config import load_config

cfg = load_config()

db = cfg['database:database']
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


plat = run('uname').stdout
if b'Darwin' in plat:
    print('Configuring MacOS postgres')
    sudo = ''
else:
    print('Configuring Linux postgres')
    sudo = 'sudo -u postgres'

run(f'{sudo} createuser {user}')

for current_db in (db, db + '_test'):
    run(f'{sudo} createdb -w {current_db}')
    run(f'{sudo} createdb -w {current_db}')
    run(f'psql {flags}\
          -c "GRANT ALL PRIVILEGES ON DATABASE {current_db} TO {user};"')

print('Testing database connection...', end='')
test_cmd = f"psql {flags} -c 'SELECT 0;'"
p = run(test_cmd)

if p.returncode != 0:
    print(f'''failed.

!!! Error accessing database:

The most common cause of database connection errors is a misconfigured
`pg_hba.conf`.

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
''')
else:
    print('OK')
