import os
from os.path import join as pjoin
import time
import sys

from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler

from baselayer.log import make_log
from baselayer.tools.fill_conf_values import fill_config_file_values
from baselayer.app.env import load_env

log = make_log('template_watch')
env, cfg = load_env()

if not env.debug:
    log('Watcher only used in debug mode; exiting')
    sys.exit(0)

# Baselayer parent project path
watchpath = os.path.abspath(pjoin(os.path.dirname(__file__), '../../..'))


class EventHandler(PatternMatchingEventHandler):
    def __init__(self):
        PatternMatchingEventHandler.__init__(self, patterns=['*.template'])

    def on_modified(self, event):
        fill_config_file_values([event.src_path])


if __name__ == "__main__":
    event_handler = EventHandler()

    observer = Observer()
    observer.schedule(event_handler, watchpath, recursive=True)
    observer.start()

    log(f'Watching for template file changes in {watchpath}')

    try:
        while True:
            time.sleep(3)
    finally:
        observer.stop()
        observer.join()
