# Setup

This guide describes how to get a webapp, derived from `baselayer`, up
and running. A simple example of such an application is provides as a
[template application](https://github.com/cesium-ml/baselayer_template_app).

Clone that application, and then proceed with the following instructions.

## Installation

- A **Python 3.8** or later installation is required.
- Install the following dependencies: Supervisor, NGINX, PostgreSQL, Node.JS

### On macOS

- Using [Homebrew](http://brew.sh/): `brew install supervisor nginx postgresql node`
  - Start the postgresql server:
    - to start automatically at login: `brew services start postgresql`
    - to start manually: `pg_ctl -D /usr/local/var/postgres start`
- Using [MacPorts](https://www.macports.org): `port install nginx +realip postgresql13-server npm7`
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
  `sudo apt-get install nginx supervisor postgresql libpq-dev npm nodejs-legacy`
- It may be necessary to configure your database permissions: at
  the end of your `pg_hba.conf` (typically in `/etc/postgresql/13.3/main` or `/var/lib/pgsql/data`),
  add the following lines and restart PostgreSQL
  (`sudo service postgresql restart` or `systemctl reload postgresql`):

  ```
  # CONNECTION DATABASE USER ADDRESS METHOD
  host template_app template_app localhost trust
  host all postgres localhost trust
  ```

  Substitute the correct database name and user, as defined in your `config.yaml`.

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
