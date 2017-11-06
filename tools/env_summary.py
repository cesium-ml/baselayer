#!/usr/bin/env python

from baselayer.app.env import load_env

env, cfg = load_env()

print('=' * 50)
print(f"Server at: http://localhost:{cfg['ports:app']}")
print(f"Database at: \
{cfg['database:host']}:{cfg['database:port']} ({cfg['database:database']})")
print(f"Fake OAuth: \
{'enabled' if cfg['server:auth:debug_login'] else 'disabled'}")
print(f"Debug mode: \
{'enabled' if env.debug else 'disabled'}")

print('=' * 50)
