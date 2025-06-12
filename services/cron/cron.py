import os
import subprocess
import sys
import time
from datetime import datetime

import yaml
from baselayer.app.env import load_env
from baselayer.app.models import CronJobRun, DBSession, init_db
from baselayer.log import make_log
from dateutil.parser import parse as parse_time

log = make_log("cron")

env, cfg = load_env()
jobs = cfg.get("cron") or []

init_db(**cfg["database"])

timestamp_file = ".jobs_timestamps.yaml"


class TimeCache:
    def __init__(self):
        if os.path.exists(timestamp_file):
            with open(timestamp_file) as f:
                timestamps = yaml.full_load(f)["timestamps"]
        else:
            timestamps = {}

        self.ts = timestamps

    def should_run(self, key, interval, limit=None):
        """Determine whether job should run.

        Parameters
        ----------
        key : str
            A key for the job, made up of `script_name+interval`.
        interval : int
            Interval, in minutes, at which to execute the job.
        limit : tuple of two time strings, optional
            Limit the execution of the job to this bracket.

        """
        if limit is not None:
            limit_start, limit_end = (parse_time(t) for t in limit)
            now = datetime.now()
            if not (limit_start < now < limit_end):
                return False

        if key not in self.ts:
            self.reset(key)

        return (time.time() - self.ts[key]) > interval * 60

    def reset(self, key):
        self.ts[key] = time.time()
        self.cache_to_file()

    def cache_to_file(self):
        with open(timestamp_file, "w") as f:
            yaml.dump({"timestamps": self.ts}, f)


log(f"Monitoring {len(jobs)} jobs")

tc = TimeCache()

while True:
    for job in jobs:
        if job.get("interval") is None:
            continue
        interval = job["interval"]
        script = job["script"]
        limit = job.get("limit")

        key = f"{script}+{interval}"

        if tc.should_run(key, interval, limit=limit):
            log(f"Executing {script}")
            tc.reset(key)
            try:
                proc = subprocess.Popen(
                    [script, *sys.argv[1:]],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                )
                output, _ = proc.communicate()
            except Exception as e:
                log(f"Error executing {script}: {e}")
                DBSession().add(CronJobRun(script=script, exit_status=1, output=str(e)))
            else:
                DBSession().add(
                    CronJobRun(
                        script=script,
                        exit_status=proc.returncode,
                        output=output.decode("utf-8").strip(),
                    )
                )
            finally:
                DBSession().commit()

    time.sleep(60)
