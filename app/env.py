"""
Parse environment flags, and load the app configuration.
"""

import argparse

from .config import load_config

# Cache loading of environment
_cache = {}


def load_env():
    """Parse environment and load configuration.

    The configuration is loaded only once per session.  When invoked a
    second time, it returns a cached result.

    Environment variables supported:

    --config  Additional configuration files to load, over and above the
              default  `baselayer/config.yaml.defaults`
              and `./config.yaml.defaults`).  Can be specified multiple times.

    --debug   In Debug mode:
              a) Tornado reloads files automatically that change from disk.
              b) SQLAlchemy logs more verbosely to the logs.

    """
    if not _cache:
        parser = argparse.ArgumentParser(description='Launch web app')
        parser.add_argument('-C', '--config', action='append')
        parser.add_argument('--debug', action='store_true')

        env, unknown = parser.parse_known_args()
        cfg = load_config(config_files=env.config or [])

        _cache.update({'file': env.config, 'env': env, 'cfg': cfg})

    return _cache['env'], _cache['cfg']
