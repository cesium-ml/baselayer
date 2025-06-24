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

## Adding external services

External services are microservices that you can pull from GitHub and run as part of your application. This is useful for integrating third-party services or custom scripts.

If you want to add external services to your application,
you can do so by adding them to the `config.yaml` file under the `services.external` key. This allows baselayer to pull the external service from a GitHub repository.

The configuration in the `config.yaml` file should look like this:

```
services:
  external:
    my_service:
        url: "https://github.com/my_service.git"
        branch: main
        sha: specific_commit_sha
        params: {}
    another_service:
        url: "https://github.com/another_service.git"
        version: v0.1.0
        params: {}
```

You must provide the `url` of the GitHub repository. To target a specific version of the service, you can optionally include both the `branch` and `sha`, or use the `version` field to refer to a particular release. Additional configuration options can be passed through the `params` dictionary, which the service may use during setup.

The external service will then be initialized and registered in supervisor, alongside other services, provided it is correctly configured and compatible with the application.
