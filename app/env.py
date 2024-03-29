"""
Parse environment flags, and load the app configuration.
"""

import argparse
import textwrap

from .config import load_config

# Cache loading of environment
_cache = {}

parser = argparse.ArgumentParser(description="Launch web app")
parser.add_argument("-C", "--config", action="append")
parser.add_argument("--debug", action="store_true")


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
        env, unknown = parser.parse_known_args()
        cfg = load_config(config_files=env.config or [])

        _cache.update({"file": env.config, "env": env, "cfg": cfg})

        # Prohibit more arguments from being added on after config has
        # been loaded
        def no_more_args(cls, *args, **kwargs):
            raise RuntimeError(
                textwrap.dedent(
                    """
                Trying to add argument after `load_env` has already been called.
                This typically happens when one of your imports calls
                `load_env`.  To avoid this error, move your imports until after
                adding new arguments to the parser.
            """
                )
            )

        parser.add_argument = no_more_args

    return _cache["env"], _cache["cfg"]
