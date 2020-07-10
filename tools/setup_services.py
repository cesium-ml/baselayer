import re
import os
from os.path import join as pjoin
from collections import Counter

from baselayer.app.env import load_env
from baselayer.log import make_log


log = make_log('baselayer')


def copy_supervisor_configs():
    env, cfg = load_env()

    services = {}
    for path in cfg['services.paths']:
        if os.path.exists(path):
            path_services = [d for d in os.listdir(path)
                             if os.path.isdir(pjoin(path, d))]
            services.update({s: pjoin(path, s) for s in path_services})

    duplicates = [k for k, v in Counter(services.keys()).items() if v > 1]
    if duplicates:
        raise RuntimeError(f'Duplicate service definitions found for {duplicates}')

    log(f'Discovered {len(services)} services')

    disabled = cfg['services.disabled'] or []
    enabled = cfg['services.enabled'] or []

    both = set().union(disabled).intersection(enabled)
    if both:
        raise RuntimeError(
            f'Invalid service specification: {both} in both enabled and disabled'
        )

    if disabled == '*':
        disabled = services.keys()
    if enabled == '*':
        enabled = []

    services_to_run = set(services.keys()).difference(disabled).union(enabled)
    log(f'Enabling {len(services_to_run)} services')

    supervisor_configs = []
    for service in services_to_run:
        path = services[service]
        supervisor_conf = pjoin(path, 'supervisor.conf')

        if os.path.exists(supervisor_conf):
            with open(supervisor_conf, 'r') as f:
                supervisor_configs.append(f.read())

    with open('baselayer/conf/supervisor/supervisor.conf', 'a') as f:
        f.write('\n\n'.join(supervisor_configs))


if __name__ == '__main__':
    copy_supervisor_configs()
