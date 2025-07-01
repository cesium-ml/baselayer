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

The external service will then be initialized and registered in `supervisor` alongside other services, provided it is correctly configured and compatible with the application.
Compatibility can be enforced via version constraints declared in the service’s optional pyproject.toml. See [External Service Requirements](#external-service-requirements) for details.

### External Service Requirements

To work correctly with the application, external services should follow these conventions:

#### Entry Point

- The service should include a `main.py` file as its entry point. In that case, providing a `supervisor.conf` can be omitted and will be auto-generated, referring to `main.py`.
- If the entry point differs, a `supervisord.conf` must be provided in the repository, pointing to the correct entry point.

#### Project Metadata and Compatibility

External services may include a `pyproject.toml` file to provide metadata and compatibility information. This is especially important when multiple applications (or versions) are built on top of Baselayer.

In this file:

- The name of the service must be specified, matching the external service name in `config.yaml`.

- It should define a [tool.`<application-name>`] section, where `<application-name>` is the name of the application you are adding the external microservice to. This section may include a `version` field to declare which versions of the application the service is compatible with. If the version requirement is not met, the external service will not be registered.

For example, an external service's `pyproject.toml` may look like:

```toml
[project]
name = "my_service"
version = "0.1.0"
description = "A micro-service to add to an application built on top of baselayer"
authors = [
  { name = "John Doe", email = "john.doe@example.com" }
]

[tool.myapp]
version = ">=1.2.0, <2.0.0"
```

#### Default Configuration

A `config.yaml.defaults` file can be provided, which is helpful if the service needs to be configured and expects parameters to be specified in `config.yaml`. It also serves as an example of how to integrate the service into an application:
```yaml
services:
    external: 
        my_service:
            version: v0.1.0
            params:
                endpoint: "https://api.example.com"
```
