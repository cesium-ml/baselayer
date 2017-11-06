# Setup

## Installation

- A **Python 3.6** or later installation is required.
- Install the following dependencies: Supervisor, NGINX, PostgreSQL, Node.JS

### On macOS

- Using [Homebrew](http://brew.sh/): `brew install supervisor nginx postgresql node`
- Start the postgresql server:
  - to start automatically at login: `brew services start postgresql`
  - to start manually: `pg_ctl -D /usr/local/var/postgres start`

### On Linux

- Using `apt-get`:
  `sudo apt-get install nginx supervisor postgresql libpq-dev npm nodejs-legacy`
- It may be necessary to configure your database permissions: at
  the end of your `pg_hba.conf` (typically in `/etc/postgresql/9.6/main`),
  add the following lines and restart PostgreSQL
  (`sudo service postgresql restart`):
  ```
  local all postgres peer
  local baselayer baselayer trust
  local baselayer_test baselayer trust
  ```

- Initialize the database with `make db_init` (also tests that your
  permissions have been properly configured).

- Run `make` to start the server and navigate to `localhost:5000`

## Configuration

- Customize `config.yaml` (see `config.yaml.defaults` for all options).
  - Always modify `secret-key` before deployment!
- If you want other users to be able to log in:
  - Provide Google auth credentials, obtained as described in `config.yaml`.

## Launch

Launch the app with `make run`.
