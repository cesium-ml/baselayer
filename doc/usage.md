# Usage

The premiere application of `baselayer` is
[SkyPortal](https://skyportal.io).  Several pieces of functionality
have been implemented there, but have not been backported to
`baselayer` yet.  Please refer to the SkyPortal documentation, and if
you see a feature you'd like to use, file an issue so we can bring it
in.

## Permissions

Access to resources in Skyportal is controlled in two ways:
- *Roles* are sets of site-wide permissions (*ACLs*) that allow a user to perform certain actions: e.g, create a new user, upload spectra, post comments, etc.
- *Groups* are sets of sources that are accessible to members of that group
    - Members can also be made an *admin* of the group, which gives them group-specific permissions to add new users, etc.
    - The same source source can belong to multiple groups


## Microservices

Baselayer uses stand-alone micro-services whenever possible.  These
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
```

For example, the `cron` microservice lives in
`./baselayer/services/cron`.  In that directory, there is a
`supervisor.conf` file and any other files that implement the
microservice (in this case, `cron.py`).

A microservice is loaded by injecting the `supervisor.conf` into the
`supervisor.conf` file used by the entire system.

By default, all discovered microservices are loaded, but this can be
customized through the `services.enabled` and `services.disabled`
configuration keys. `services.disabled` can be set to `'*'` to disable
all services.  E.g., to only load the `cron` service, you would do:

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
launching.  See, e.g., `services/dask`.
