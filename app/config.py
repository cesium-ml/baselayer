import os
from pathlib import Path
import collections.abc as collections
from deepdiff import DeepDiff
import yaml
from pprint import pprint

from ..log import make_log

log = make_log('baselayer')


def ensure_yaml_routes_matches_defaults(config_path, defaults_config_path):
    # Borrowed from https://github.com/dmitryduev/kowalski/blob/master/kowalski.py
    # check contents of config WRT config.yaml.defaults
    with open(defaults_config_path) as defaults_yaml:
        config_defaults = yaml.load(defaults_yaml, Loader=yaml.FullLoader)
    with open(config_path) as config_yaml:
        config_wildcard = yaml.load(config_yaml, Loader=yaml.FullLoader)
    routesmatch = True
    if ( 'app' in config_wildcard ) and ( 'routes' in config_wildcard['app'] ):
        # In python 3.8+, we should just be able to do
        #   config_wildcard['app']['routes'] == config_defaults['app']['routes']
        difference = DeepDiff( config_wildcard['app']['routes'],
                               config_defaults['app']['routes'],
                               ignore_order=True)
        if difference:
            routesmatch = False
    if not routesmatch:
        print("  config.yaml app.routes differs from config.yaml.defaults:")
        pprint(difference)
        raise KeyError("Fix config.yaml before proceeding")
    print("config.yaml app.routes matches that of config.yaml.defaults")


def recursive_update(d, u):
    # Based on https://stackoverflow.com/a/3233356/214686
    for k, v in u.items():
        if isinstance(v, collections.Mapping):
            r = recursive_update(d.get(k, {}) or {}, v)
            d[k] = r
        else:
            d[k] = u[k]
    return d


def relative_to(path, root):
    p = Path(path)
    try:
        return p.relative_to(root)
    except ValueError:
        return p


class Config(dict):
    """To simplify access, the configuration allows fetching nested
    keys separated by a period `.`, e.g.:

    >>> cfg['app.db']

    is equivalent to

    >>> cfg['app']['db']

    """

    def __init__(self, config_files=None):
        dict.__init__(self)
        if config_files is not None:
            cwd = os.getcwd()
            config_names = [relative_to(c, cwd) for c in config_files]
            print(f'  Config files: {config_names[0]}')
            for f in config_names[1:]:
                print(f'                {f}')
            self['config_files'] = config_files
            for f in config_files:
                self.update_from(f)

    def update_from(self, filename):
        """Update configuration from YAML file"""
        if os.path.isfile(filename):
            more_cfg = yaml.full_load(open(filename))
            recursive_update(self, more_cfg)

    def __getitem__(self, key):
        keys = key.split('.')

        val = self
        for key in keys:
            val = val.get(key)
            if val is None:
                return None

        return val

    def show(self):
        """Print configuration"""
        print()
        print("=" * 78)
        print("Configuration")
        for key in self:
            print("-" * 78)
            print(key)

            if isinstance(self[key], dict):
                for key, val in self[key].items():
                    print('  ', key.ljust(30), val)

        print("=" * 78)


def load_config(config_files=[]):
    basedir = Path(os.path.dirname(__file__)) / '..'
    missing = [cfg for cfg in config_files if not os.path.isfile(cfg)]
    if missing:
        log(f'Missing config files: {", ".join(missing)}; continuing.')
    if 'config.yaml' in missing:
        log(
            "Warning: You are running on the default configuration. To configure your system, "
            "please copy `config.yaml.defaults` to `config.yaml` and modify it as you see fit."
        )
    elif os.path.exists(basedir / "../config.yaml"):
        ensure_yaml_routes_matches_defaults(
            basedir / "../config.yaml", basedir / "../config.yaml.defaults",
        )

    # Always load the default configuration values first, and override
    # with values in user configuration files
    all_configs = [
        Path(basedir / 'config.yaml.defaults'),
        Path(basedir / '../config.yaml.defaults'),
    ] + config_files
    all_configs = [cfg for cfg in all_configs if os.path.isfile(cfg)]
    all_configs = [os.path.abspath(Path(c).absolute()) for c in all_configs]

    cfg = Config(all_configs)

    return cfg
