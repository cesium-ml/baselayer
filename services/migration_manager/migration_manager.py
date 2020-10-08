import subprocess
import os
import time

import tornado.ioloop
import tornado.web

from baselayer.app.env import load_env
from baselayer.log import make_log

env, cfg = load_env()
log = make_log('migration_manager')


conf_file = env.config[0]
conf_flags = ['-x', f'config={conf_file}'] if conf_file else []


class timeout_cache:
    def __init__(self, timeout):
        self.timeout = timeout
        self.lastrun = 0
        self.cache = None
        self.func = None

    def __call__(self, f):
        self.func = f
        return self.wrapped

    def wrapped(self, *args, **kwargs):
        tic = self.lastrun
        toc = time.time()
        if (toc - tic) > self.timeout or self.cache is None:
            self.lastrun = toc
            self.cache = self.func(*args, **kwargs)

        return self.cache


def migrations_exist():
    return os.path.isdir('./alembic/versions')


def migrate():
    path_env = os.environ.copy()
    path_env['PYTHONPATH'] = '.'

    cmd = ['alembic'] + conf_flags + ['upgrade', 'head']
    log(f'Attempting migration: {" ".join(cmd)}')
    p = subprocess.Popen(
        cmd,
        stderr=subprocess.PIPE,
        env=path_env
    )

    output, error = p.communicate()
    for line in error.decode('utf-8').split('\n'):
        log(line)

    if p.returncode != 0:
        log('Migration failed')
    else:
        log('Migration succeeded')


@timeout_cache(timeout=10)
def migration_status():
    if not migrations_exist():
        # No migrations present, continue as usual
        log('No migrations found; proceeding')
        return True

    path_env = os.environ.copy()
    path_env['PYTHONPATH'] = '.'

    p = subprocess.Popen(
        ['alembic'] + conf_flags + ['current'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=path_env
    )
    output, error = p.communicate()

    status = output.decode('utf-8').strip().split('\n')[-1]
    if p.returncode == 0 and '(head)' in status:
        log('Database is up to date')
        return True

    log('Database is not migrated')
    return False


class MainHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Content-Type", 'application/json')

    def get(self):
        self.write({'migrated': migration_status()})


def make_app():
    return tornado.web.Application([
        (r"/", MainHandler),
    ])


if __name__ == "__main__":
    if migrations_exist() and not migration_status():
        # Attempt migration on startup
        migrate()

    app = make_app()
    port = cfg['ports.migration_manager']
    app.listen(port)
    log(f'Listening on port {port}')
    tornado.ioloop.IOLoop.current().start()
