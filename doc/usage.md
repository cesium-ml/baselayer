# Usage

The premiere application of `baselayer` is
[SkyPortal](https://skyportal.io). Several pieces of functionality
have been implemented there, but have not been backported to
`baselayer` yet. Please refer to the SkyPortal documentation, and if
you see a feature you'd like to use, file an issue so we can bring it
in.

## Permissions

Access to resources in Skyportal is controlled in two ways:

- _Roles_ are sets of site-wide permissions (_ACLs_) that allow a user to perform certain actions: e.g, create a new user, upload spectra, post comments, etc.
- _Groups_ are sets of sources that are accessible to members of that group
  - Members can also be made an _admin_ of the group, which gives them group-specific permissions to add new users, etc.
  - The same source source can belong to multiple groups

## Microservices

Baselayer uses stand-alone micro-services whenever possible. These
services are monitored by supervisord, and by default include nginx, the web
app, a cron-job handler, the websocket server, etc.

Services are configured in the `config.yaml` file (defaults in
`config.yaml.defaults`), and are discovered by path:

```
services:
    paths:
      - ./baselayer/services
      - ./services
    enabled:
    disabled:
    external:
```

For example, the `cron` microservice lives in
`./baselayer/services/cron`. In that directory, there is a
`supervisor.conf` file and any other files that implement the
microservice (in this case, `cron.py`).

A microservice is loaded by injecting the `supervisor.conf` into the
`supervisor.conf` file used by the entire system.

By default, all discovered microservices are loaded, but this can be
customized through the `services.enabled` and `services.disabled`
configuration keys. `services.disabled` can be set to `'*'` to disable
all services. E.g., to only load the `cron` service, you would do:

```
services:
    paths:
      - ./baselayer/services
      - ./services
    enabled:
      - cron
    disabled: '*'
```

Sometimes, the supervisor configuration needs information from the
configuration file, therefore `supervisor.conf` can instead be
provided as `supervisor.conf.template`, which will be compiled before
launching. See, e.g., `services/dask`.

"External" micro-services can be used to extend the capabilities of any application relying on `baselayer`.

These are added to `services.external` section of the configuration, and need to provide: service name, GitHub repo URL, branch+sha or tagged version of the repo where the external service is hosted, along with optional service-specific parameters. For example:

```
services:
  paths:
    - ./baselayer/services
    - ./services
  enabled:
    - cron
  disabled: '*'
  external:
    my_external_service:
      url: https://github.com/my_external_service.git
      version: v0.1.0
      params: {}
```

External services are imported in the last location mentioned in services.paths. To know more about external services, please refer to the [External Services documentation](extending.md#adding-external-services).

## Web Application

Baselayer comes with a microservice capable of bundling a web application. A great example of this is given in the [template application](https://github.com/cesium-ml/baselayer_template_app). When building your own application on top of baselayer, you'll need to add your own `static` directory at the root of your project, as well as a `rspack.config.js` file to bundle your application. The `rspack.config.js` from the template application is a good starting point, and will be sufficient for most use cases. Instead of using the very popular [webpack](https://webpack.js.org/), we use [rspack](https://rspack.dev/) as a 1:1 replacement. It covers all the features needed by baselayer, but offers much faster build times in development and production modes. We've noticed a x2 speedup on average when building a complex & heavy web app such as [SkyPortal](https://github.com/skyportal/skyportal), and at least a x5 speedup when re-building the app in watch mode, which we use to update the web app in real-time when developing.
