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
launching. See, e.g., `services/app`.

"External" micro-services can be used to extend the capabilities of any application relying on `baselayer`.

These are added to `services.external` section of the configuration, and need to provide: service name, GitHub repo URL, revision (branch, sha, or tag), along with optional service-specific parameters. For example:

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
      repo: https://github.com/my_external_service.git
      rev: v0.1.0
      params: {}
```

External services are imported in the last location mentioned in `services.paths`.
To learn more about external services, please refer to the [External Services documentation](extending.md#adding-external-services).

## Sharing memory between services (zygote)

Each Python service usually imports the application by itself, so each
process holds its own copy of the same modules. The zygote prevents
this. The zygote is a service that imports the modules one time. It then
starts the other Python services as forks of itself. A forked service
shares the memory pages of the zygote until it writes to them
(copy-on-write).

The zygote is off by default. To fork all Python services from it:

```
zygote:
  services: '*'
```

The configuration keys are:

- `zygote.services`: the services to fork from the zygote, as a list of
  service names (directory names), or `'*'` for all services.
- `zygote.exclude`: the services to start by themselves, for example when
  `zygote.services` is `'*'`. The default is `[rspack]`: rspack runs in
  Node.js, so forking its Python starter shares nothing. If you set this
  list, include `rspack` in it.
- `zygote.preload`: the modules that the zygote imports. If the list is
  empty, the zygote imports the module of `app.factory`.

### How the zygote starts a service

supervisord keeps one program for each service. For a forked service,
`baselayer/tools/setup_services.py` changes the supervisor command from
`/usr/bin/env python SCRIPT ARGS` to
`/usr/bin/env python baselayer/tools/zygote_launch.py SCRIPT ARGS`.
Commands that do not start with `/usr/bin/env python`, such as the nginx
command, do not change.

The launcher is a small process that imports only the standard library.
It sends its standard input and output, arguments, working directory, and
environment to the zygote over `run/zygote.sock`. The zygote forks, and
the fork runs `SCRIPT` as `python SCRIPT ARGS` would. The launcher then:

- sends the signals that it receives to the service;
- writes the process ID of the service to `run/zygote/<launcher PID>.pid`,
  because supervisord shows the process ID of the launcher;
- stops with the exit status of the service.

A forked service has the name of its supervisor program, so `top` and
`ps -o comm` show that name. If the zygote stops, its services also stop.

### Rules for preloaded modules

The zygote imports the preloaded modules before it forks. Each service
gets a copy of everything that these modules create at import time.
Functions, classes, and data can be shared in this way, but threads and
connections cannot:

- **Threads.** A forked process has only the thread that called `fork()`.
  A thread started at import time does not run in the services. If that
  thread held a lock during the fork, the lock stays held in each
  service, and code that waits for it hangs.
- **Connections and sockets.** A database connection or socket opened at
  import time becomes one connection that all services share. One service
  can then receive a reply meant for another.

Start threads and open connections in the service, after the fork.

Also:

- The zygote uses one thread for OpenBLAS, MKL, and OpenMP, and Arrow's
  jemalloc does not start a background thread.
- The zygote does not see changes to the preloaded modules. Restart the
  app to load them.
- In debug mode, Tornado restarts a service when one of its files changes.
  The restarted service imports its modules again, and no longer shares
  memory with the zygote.

On macOS, baselayer ignores `zygote.services` and starts each service by
itself, because macOS system libraries can crash in a forked process.

## Web Application

Baselayer comes with a microservice capable of bundling a web application. A great example of this is given in the [template application](https://github.com/cesium-ml/baselayer_template_app). When building your own application on top of baselayer, you'll need to add your own `static` directory at the root of your project, as well as a `rspack.config.js` file to bundle your application. The `rspack.config.js` from the template application is a good starting point, and will be sufficient for most use cases. Instead of using the very popular [webpack](https://webpack.js.org/), we use [rspack](https://rspack.dev/) as a 1:1 replacement. It covers all the features needed by baselayer, but offers much faster build times in development and production modes. We've noticed a x2 speedup on average when building a complex & heavy web app such as [SkyPortal](https://github.com/skyportal/skyportal), and at least a x5 speedup when re-building the app in watch mode, which we use to update the web app in real-time when developing.
