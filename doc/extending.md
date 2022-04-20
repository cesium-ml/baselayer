# Extending baselayer

## Modifying the Tornado application

A Python function can be specified in the configuration as
`app.factory`, that will be used to create the Tornado
application. This is often needed to add additional routes, or do
certain setup procedures before the application is run.

The function should have the following argument signature:

```
def make_app(config, baselayer_handlers, baselayer_settings)
```

The configuration is passed in as the first parameter, followed by
baselayer-handlers (those should be appended to your Tornado handlers,
to put in place system endpoints such as logging in). The last
argument contains baselayer-specific Tornado configuration.

A typical `make_app` could be:

```
from baselayer.app.app_server import MainPageHandler

def make_app(config, baselayer_handlers, baselayer_settings):
       handlers = baselayer_handlers + [
           (r'/my_page', MyPageHandler),
           (r'/.*', MainPageHandler)
       ]

       settings = baselayer_settings
       settings.update({
           'tornado_config_key': 'tornado_config_value'
       })  # Specify any additional settings here

       app = tornado.web.Application(handlers, **settings)
       return app
```

## Templating

Often, values inside your JavaScript code or engineering configuration
files (nginx, supervisor, etc.) depend on settings inside
`config.yaml`. To simplify propagating these values, `baselayer`
provides templating functionality, applied to files named
`*.template`, before running the application. The template engine used
is [Jinja2](https://jinja.palletsprojects.com).

The configuration file is injected into the template, so you can
include their values as follows:

```
The database port is {{ database.port }}.
```

When you launch the `run` or `run_production` targets for baselayer,
it will automatically fill out all template files. Alternatively, you
can run the templating manually:

```
./baselayer/tools/fill_conf_values.py --config="config.yaml" static/js/component.jsx.template
```
