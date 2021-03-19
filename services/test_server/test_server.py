import importlib.util
from pathlib import Path

import tornado.ioloop
import tornado.httpserver

from baselayer.app.env import load_env
from baselayer.log import make_log


if __name__ == "__main__":
    env, cfg = load_env()
    log = make_log("testserver")

    if "test_server" in cfg:
        # Resolve server module path
        path = Path(cfg["test_server.path"])
        if not path.is_absolute():
            path = path.resolve()
        log(f"Loading test server app from {path}")
        # Load in a configurable test server
        spec = importlib.util.spec_from_file_location(
            cfg["test_server.module"], path
        )
        test_server = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(test_server)
        # The test server module must provide a Tornado Application
        # returned by a function called "make_app".

        app = test_server.make_app()
        server = tornado.httpserver.HTTPServer(app)
        port = cfg["ports.test_server"]
        server.listen(port)

        log(f"Listening for test HTTP requests on port {port}")
        tornado.ioloop.IOLoop.current().start()
