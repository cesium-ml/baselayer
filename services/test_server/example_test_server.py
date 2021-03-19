import tornado.web
import tornado.wsgi
from tornado.web import RequestHandler

from spyne.application import Application
from spyne.decorator import srpc
from spyne.service import ServiceBase
from spyne.server.wsgi import WsgiApplication
from spyne.model.complex import Iterable
from spyne.model.primitive import UnsignedInteger
from spyne.model.primitive import String
from spyne.protocol.soap import Soap11


class HelloWorldService(ServiceBase):
    """
    This is a simple example WSDL-based SOAP service to be included
    in the example test server. It can be used to mock responses from
    an external SOAP server for testing.
    """

    @srpc(String, UnsignedInteger, _returns=Iterable(String))
    def say_hello(name, times):
        for i in range(times):
            yield "Hello, %s" % name


class TestRouteHandler(RequestHandler):
    """
    This is a simple example REST API service to be included
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
    app = Application(
        [HelloWorldService],
        "spyne.examples.hello.http",
        in_protocol=Soap11(validator="lxml"),
        out_protocol=Soap11(),
    )
    wsgi_app = tornado.wsgi.WSGIContainer(WsgiApplication(app))
    return tornado.web.Application(
        [
            ("/api/hello", TestRouteHandler),
            (
                "/wsdl/hello",
                tornado.web.FallbackHandler,
                dict(fallback=wsgi_app),
            ),
        ]
    )
