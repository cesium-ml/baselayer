import yaml
import os
from pathlib import Path
import collections


def recursive_update(d, u):
    # Based on https://stackoverflow.com/a/3233356/214686
    for k, v in u.items():
        if isinstance(v, collections.Mapping):
            r = recursive_update(d.get(k, {}) or {}, v)
            d[k] = r
        else:
            d[k] = u[k]
    return d


class Config(dict):
    def __init__(self, config_files=None):
        dict.__init__(self)
        if config_files is not None:
            cwd = os.getcwd()
            config_names = [Path(c).relative_to(cwd) for c in config_files]
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
        keys = key.split(':')

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
    basedir = Path(os.path.dirname(__file__))/'..'
    missing = [cfg for cfg in config_files if not os.path.isfile(cfg)]
    if missing:
        raise RuntimeError(f"[Baselayer] Missing config files: {missing}")

    # Always load the default configuration values first, and override
    # with values in user configuration files
    all_configs = [Path(basedir/'config.yaml.defaults'),
                   Path(basedir/'../config.yaml.defaults')] + config_files
    all_configs = [cfg for cfg in all_configs if os.path.isfile(cfg)]
    all_configs = [os.path.abspath(Path(c).absolute()) for c in all_configs]

    cfg = Config(all_configs)

    return cfg
