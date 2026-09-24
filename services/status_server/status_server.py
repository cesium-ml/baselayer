import html
import os
import time

import tornado.ioloop
import tornado.web
from tornado.httpclient import AsyncHTTPClient

from baselayer.app.env import load_env

env, cfg = load_env()

MAINTENANCE_FILE = "run/maintenance"
RETRY_AFTER = 30
STATE_CACHE_SECONDS = 5

HEADLINES = {
    "maintenance": "is down for maintenance",
    "starting": "is starting up",
    "unavailable": "is temporarily unavailable",
}
DETAILS = {
    "maintenance": "Please check back later.",
    "starting": "It should be back within a few minutes.",
    "unavailable": "It should be back shortly.",
}

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="{retry_after}">
<title>{title}</title>
<style>
body {{ margin: 0; min-height: 100vh; display: grid; place-items: center;
  font-family: system-ui, sans-serif; color: #222; background: #f5f5f5; }}
main {{ max-width: 32rem; padding: 2rem; text-align: center; }}
p {{ color: #555; }}
</style>
</head>
<body>
<main>
<h1>{title} {headline}</h1>
<p>{detail}</p>
<p>This page reloads itself every {retry_after} seconds.</p>
</main>
</body>
</html>
"""

_state = {"checked_at": float("-inf"), "value": None}


async def current_state():
    """Why the app is not answering, and an optional operator note."""
    if time.monotonic() - _state["checked_at"] < STATE_CACHE_SECONDS:
        return _state["value"]

    if os.path.exists(MAINTENANCE_FILE):
        with open(MAINTENANCE_FILE) as f:
            value = ("maintenance", f.read().strip())
    else:
        # The migration manager only starts listening once migrations are done.
        try:
            await AsyncHTTPClient().fetch(
                f"http://localhost:{cfg['ports.migration_manager']}",
                request_timeout=1,
                raise_error=False,
            )
            value = ("unavailable", "")
        except Exception:
            value = ("starting", "")

    _state.update(checked_at=time.monotonic(), value=value)
    return value


class StatusHandler(tornado.web.RequestHandler):
    async def prepare(self):
        state, note = await current_state()
        title = cfg["app.title"]
        detail = note or DETAILS[state]

        self.set_status(503)
        self.set_header("Retry-After", str(RETRY_AFTER))
        self.set_header("Cache-Control", "no-store")

        path = self.request.path
        if self.request.method == "HEAD":
            pass
        elif path == "/api" or path.startswith("/api/"):
            self.write(
                {
                    "status": "error",
                    "message": f"{title} {HEADLINES[state]}. {detail}",
                    "data": {"state": state},
                }
            )
        else:
            self.write(
                PAGE.format(
                    title=html.escape(title),
                    headline=HEADLINES[state],
                    detail=html.escape(detail),
                    retry_after=RETRY_AFTER,
                )
            )
        self.finish()


def make_app():
    return tornado.web.Application([(r".*", StatusHandler)])


if __name__ == "__main__":
    app = make_app()
    app.listen(cfg["ports.status"])
    tornado.ioloop.IOLoop.current().start()
