#!/usr/bin/env python

import subprocess
import sys
import glob
import os
from baselayer.app.config import load_config

cfg = load_config()
db = cfg['database:database']
user = cfg.get('database:user', db)

plat = subprocess.run('uname', stdout=subprocess.PIPE).stdout
if b'Darwin' in plat:
    print('Configuring OSX postgres')
    sudo = ''
else:
    print('Configuring Linux postgres')
    sudo = 'sudo -u postgres'

subprocess.run(f'{sudo} createdb -w {db} && createdb -w {db}_test', shell=True)
subprocess.run(f'{sudo} createuser {user}', shell=True)
subprocess.run(f'{sudo} psql -U {user} -c '
               f'"GRANT ALL PRIVILEGES ON DATABASE {db} TO {user}; '
               f'GRANT ALL PRIVILEGES ON DATABASE {db}_test TO {user}";',
               shell=True)
