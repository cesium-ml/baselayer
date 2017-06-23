#!/usr/bin/env python

import subprocess
import sys
import glob
import os
from baselayer.app.config import load_config

cfg = load_config()
db = cfg['database:database']
user = cfg['database:user']


print(f'$ ./baselayer/tools/db_init.sh {db} {user}')
p = subprocess.run(['./baselayer/tools/db_init.sh', db, user],
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)

print('--- stdout ---')
print(p.stdout.decode('utf-8').strip())
print('--- stderr ---')
print(p.stderr.decode('utf-8').strip())
sys.exit(p.returncode)
