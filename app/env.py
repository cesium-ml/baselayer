"""
Parse environment flags, and load the app configuration.
"""

import argparse

from .config import load_config


def load_env():
    """Parse environment and load configuration.

    Environment variables supported:

    --config  Additional configuration files to load, over and above the
              default  `baselayer/config.yaml.defaults`
              and `./config.yaml.defaults`).  Can be specified multiple times.

    --debug   In Debug mode:
              a) Tornado reloads files automatically that change from disk.
              b) SQLAlchemy logs more verbosely to the logs.
    """
    parser = argparse.ArgumentParser(description='Launch web app')
    parser.add_argument('-C', '--config', action='append')
    parser.add_argument('--debug', action='store_true')

    env, unknown = parser.parse_known_args()
    cfg = load_config(config_files=env.config or [])

    return env, cfg
