#!/usr/bin/env python
import os
import sys

from baselayer.app.env import load_env

env, cfg = load_env()
db = cfg["database.database"]

user = cfg["database.user"] or db
host = cfg["database.host"]
port = cfg["database.port"]
password = cfg["database.password"]

flags = f"-U {user}"

if password:
    psql_cmd = f'PGPASSWORD="{password}" {psql_cmd}'
flags += " --no-password"

if host:
    flags += f" -h {host}"

if port:
    flags += f" -p {port}"

cmd = f'psql {flags}'.split()
return_code = os.spawnvpe(os.P_WAIT, cmd[0], cmd, os.environ)
if return_code == 127:
    sys.stderr.write(f'{cmd[0]}: command not found\n')

sys.exit(return_code)
