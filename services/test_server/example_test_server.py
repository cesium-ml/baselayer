import tornado.web


class TestRouteHandler(tornado.web.RequestHandler):
    """
    This is a very simple example REST API service to be included
    in the example test server. It can be used to mock responses from
    an external REST server for testing.
    """

    def get(self):
        self.set_status(200)
        self.write("Hello from REST server!")


def make_app():
    """
    This function generates a Tornado Application to be run as a test server
    to run test calls to external services against. This function is imported
    and called by the test_server.py supervisord service.
    """
    return tornado.web.Application(
        [
            ("/api/hello", TestRouteHandler),
        ]
    )
