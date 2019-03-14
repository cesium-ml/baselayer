#!/usr/bin/env python

import re
import os
from status import status

from baselayer.app.env import load_env
from baselayer.log import make_log

log = make_log('baselayer')

def fill_config_file_values(template_paths):
    log('Compiling configuration templates')
    env, cfg = load_env()
    for template_path in template_paths:
        with status(template_path):
            with open(template_path) as f:
                data = f.read()
            data_compiled = re.sub('\$\$\{\{([a-zA-Z_]+)?\}\}', '{\\1}',
                                   data.replace('{', '{{').replace('}', '}}'))
            with open(os.path.splitext(template_path)[0], 'w') as f:
                f.write(data_compiled.format(**cfg['ports']))


if __name__ == '__main__':
    from argparse import ArgumentParser
    parser = ArgumentParser(description='Fill config file templates')
    parser.add_argument('template_paths', nargs='+')
    args, _ = parser.parse_known_args()
    fill_config_file_values(args.template_paths)
