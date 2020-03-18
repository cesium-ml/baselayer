import yaml
import time
import os
import subprocess


from baselayer.app.env import load_env
from baselayer.log import make_log


log = make_log('cron')

env, cfg = load_env()
jobs = cfg['cron'] or []


timestamp_file = '.jobs_timestamps.yaml'


class TimeCache:
    def __init__(self):
        if os.path.exists(timestamp_file):
            with open(timestamp_file) as f:
                timestamps = yaml.full_load(f)['timestamps']
        else:
            timestamps = {}

        self.ts = timestamps

    def should_run(self, key, interval):
        if not key in self.ts:
            self.reset(key)

        return (time.time() - self.ts[key]) > interval * 60

    def reset(self, key):
        self.ts[key] = time.time()
        self.cache_to_file()

    def cache_to_file(self):
        with open(timestamp_file, 'w') as f:
            yaml.dump({'timestamps': self.ts}, f)


log(f'Monitoring {len(jobs)} jobs')

tc = TimeCache()

while True:
    for job in jobs:
        interval = job['interval']
        script = job['script']

        key = f'{script}+{interval}'

        if tc.should_run(key, interval):
            log(f'Executing {script}')
            tc.reset(key)
            try:
                subprocess.Popen(script, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT)
            except Exception as e:
                log(f'Error executing {script}: {e}')

    time.sleep(60)
