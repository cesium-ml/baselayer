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

External services are [microservices](usage.md#microservices) that you can pull from GitHub and run as part of your application. Their behavior is similar, they just live in remote repositories. This is useful for integrating third-party services or custom scripts.

If you want to add external services to your application,
you can do so by adding them to the `config.yaml` file under the `services.external` key. This allows baselayer to pull the external service from a GitHub repository.

The configuration in the `config.yaml` file would look like this:

```
services:
  external:
    my_service:
        url: "https://github.com/my_service.git"
        branch: main
        sha: specific_commit_sha
    another_service:
        url: "https://github.com/another_service.git"
        version: v0.1.0
        params:
            endpoint: "https://api.example.com"
```

You must provide the `url` of the GitHub repository, as well as a version of the service. To specify the version, you are required to either:

- Provide both the `branch` and `sha`,
  **or**
- Use the `version` field to reference a specific release.

Additional configuration options can be passed through the `params` dictionary, which the service uses.

The external service will then be started and managed by `supervisord` alongside other services.

### External Service Requirements

To work correctly with the application, external services should follow these conventions:

#### Entry Point

- The service should include a `main.py` file as its entry point.
- If the entry point differs, a `supervisord.conf` must be provided in the repository, pointing to the correct entry point.

#### Project Metadata and Compatibility

External services may include a `pyproject.toml` file to provide metadata and compatibility information. This is especially important when multiple applications (or versions) are built on top of Baselayer.

In this file:

- The name of the service must be specified, matching the external service name in `config.yaml`.

- It should define a [tool.compatibility] section including a `compatible-with` field. This field would specify which applications (and versions) the service is compatible with. If the version requirement is not met, the external service will not be registered.

For example, an external service's `pyproject.toml` may look like:

```toml
[project]
name = "my_service"
version = "0.1.0"
description = "A micro-service to add to an application built on top of baselayer"
authors = [
  { name = "John Doe", email = "john.doe@example.com" }
]

[tool.compatibility]
compatible-with = [
  { name = "skyportal", version = ">=1.4.0" }
]
```

#### Default Configuration

A `config.yaml.defaults` file can be provided to set service configuration defaults.
These values can be overridden in the app's `config.yaml` under the `services.external.<name-of-this-service>.config` keys:

```yaml
services:
  external:
    my_service:
      version: v0.1.0
      params:
        endpoint: "https://api.example.com"
```
