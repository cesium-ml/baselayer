# Setup

This guide describes how to get a webapp, derived from `baselayer`, up
and running. A simple example of such an application is provides as a
[template application](https://github.com/cesium-ml/baselayer_template_app).

Clone that application, and then proceed with the following instructions.

## Installation

- A **Python 3.8** or later installation is required.
- Install the following dependencies: Supervisor, NGINX, PostgreSQL, Node.JS

### On macOS

- Using [Homebrew](http://brew.sh/): `brew install supervisor postgresql node`
  - If you want to use [brotli compression](https://en.wikipedia.org/wiki/Brotli) with NGINX (better compression rates for the frontend), you can install NGINX with the `ngx_brotli` module with this command: `brew tap denji/nginx && brew install nginx-full --with-brotli`. _If you already had NGINX installed, you may need to uninstall it first with `brew unlink nginx`._ Otherwise, you can install NGINX normally with `brew install nginx`.
  - Start the postgresql server:
    - to start automatically at login: `brew services start postgresql`
    - to start manually: `pg_ctl -D /usr/local/var/postgres start`
- Using [MacPorts](https://www.macports.org): `port install nginx +realip postgresql13-server`
  - Start the postgresql server: `port load postgresql13-server`

#### Port Number Configuration with macOS

The default port number used by the baselayer app is 5000, but this port is not available for use with all operating systems.
Port 5000 is not free for the latest macOS version, Monterey.

If 5000 is not available, you will need to modify the `config.yaml` file to use another port. For example, you may use:

```yaml
ports:
  app: 5700
```

See [below](#configuration) for more information on modifying the baselayer configuration file.

### On Linux

- Using `apt-get`:
  `sudo apt-get install supervisor postgresql libpq-dev nodejs`

  If you want to use [brotli compression](https://en.wikipedia.org/wiki/Brotli) with NGINX (better compression rates for the frontend), you have to install NGINX and the brotli module from another source with:

  ```
  sudo apt remove -y nginx nginx-common nginx-core
  sudo add-apt-repository ppa:ondrej/nginx-mainline -y
  sudo apt update -y
  sudo apt install -y nginx libnginx-mod-brotli
  ```

  Otherwise, you can install NGINX normally with `sudo apt-get install nginx`.

- It may be necessary to configure your database permissions: at
  the end of your `pg_hba.conf` (typically in `/etc/postgresql/13.3/main` or `/var/lib/pgsql/data`),
  add the following lines and restart PostgreSQL
  (`sudo service postgresql restart` or `systemctl reload postgresql`):

  ```
  # CONNECTION DATABASE USER ADDRESS METHOD
  host template_app template_app localhost trust
  host template_app template_app_test localhost trust
  host all postgres localhost trust
  ```

  Substitute the correct database name and user, as defined in your `config.yaml`.

  If you use IPv6, `localhost` becomes `::1/128`.

## Building the baselayer database

- Initialize the database with `make db_init` (also tests that your
  permissions have been properly configured).

- Run `make` to start the server and navigate to `localhost:5000`. If you have modified the baselayer configuration to use a different app port, you should instead navigate to `localhost:PORTNUMBER`.

## Configuration

- Customize `config.yaml` (see `config.yaml.defaults` for all options).
  - Always modify `secret_key` before deployment!
- If you want other users to be able to log in:
  - Provide Google auth credentials, obtained as described in `config.yaml`.

## Launch

Launch the app with `make run`.

## Deployment options

The default configuration file used can be overridden by setting the
FLAGS environment variable:

```
FLAGS="--config=myconfig.yaml" make run
```

## Debug mode

By default, `baselayer` runs in debug mode. In debug mode:

- The server binds to localhost, not 0.0.0.0 (i.e., is not publicly
  accessible).
- Authentication always succeeds, but does not connect to any oauth
  provider.
- Code changes cause automatic reloads of the app, and recompilation
  of Javascript bundles.
-

When switching to production mode (`debug` set to False in the config
file):

- The server binds to 0.0.0.0.
- Javascript bundles are not compiled; they need to be pre-compiled
  using `make bundle`.
