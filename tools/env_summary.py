#!/usr/bin/env python

from baselayer.app.env import load_env
from baselayer.log import colorize


def config_print(field, value):
    print(colorize(field + ":", bold=True), value)


env, cfg = load_env()

print("=" * 50)
config_print("Server at", f"http://localhost:{cfg['ports.app']}")
config_print(
    "Database at",
    f"{cfg['database.host']}:{cfg['database.port']} ({cfg['database.database']})",
)
config_print("Fake OAuth", "enabled" if cfg["server.auth.debug_login"] else "disabled")
config_print("Debug mode", "enabled" if env.debug else "disabled")
print("=" * 50)
