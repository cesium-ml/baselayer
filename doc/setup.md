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
  - If you want to use [brotli compression](https://en.wikipedia.org/wiki/Brotli) with NGINX (better compression rates for the frontend), you can install NGINX with the `ngx_brotli` module with this command: `brew tap denji/nginx && brew install nginx-full --with-brotli`. *If you already had NGINX installed, you may need to uninstall it first with `brew unlink nginx`.*Otherwise, you can install NGINX normally with `brew install nginx`.
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
  `sudo apt-get install supervisor postgresql libpq-dev npm nodejs-legacy`

  - If you want to run NGINX as is (without brotli), you can simply install it with `sudo apt-get install nginx`.
    If want to use [brotli compression](https://en.wikipedia.org/wiki/Brotli) with NGINX (to have better compression rates for the frontend), you can install NGINX with the `ngx_brotli` module with these commands:

  ```
  # install nginx from source so we can add the brotli module
  git clone --recursive https://github.com/google/ngx_brotli.git
  wget https://nginx.org/download/nginx-1.24.0.tar.gz
  tar zxf nginx-1.24.0.tar.gz
  cd ngx_brotli/deps/brotli
  mkdir out && cd out
  cmake -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DCMAKE_C_FLAGS="-Ofast -m64 -march=native -mtune=native -flto -funroll-loops -ffunction-sections -fdata-sections -Wl,--gc-sections" -DCMAKE_CXX_FLAGS="-Ofast -m64 -march=native -mtune=native -flto -funroll-loops -ffunction-sections -fdata-sections -Wl,--gc-sections" -DCMAKE_INSTALL_PREFIX=./installed ..
  cmake --build . --config Release --target brotlienc
  cd ../../../..
  export CURRENT_DIR=$(pwd)
  cd nginx-1.24.0
  ./configure --sbin-path=/usr/sbin/nginx --conf-path=/usr/local/nginx/nginx.conf --pid-path=/usr/local/nginx/nginx.pid --with-http_ssl_module --with-stream --with-mail=dynamic --with-http_realip_module --with-compat --add-module=${CURRENT_DIR}/ngx_brotli
  sudo make && sudo make install
  ```

  To run it as a service, create an Nginx systemd unit file by running `sudo nano /lib/systemd/system/nginx.service` and adding the following content:

  ```
  [Unit]
  Description=The NGINX HTTP and reverse proxy server
  After=syslog.target network-online.target remote-fs.target nss-lookup.target
  Wants=network-online.target

  [Service]
  Type=forking
  PIDFile=/usr/local/nginx/nginx.pid
  ExecStartPre=/usr/sbin/nginx -t
  ExecStart=/usr/sbin/nginx
  ExecReload=/usr/sbin/nginx -s reload
  ExecStop=/bin/kill -s QUIT $MAINPID
  PrivateTmp=true

  [Install]
  WantedBy=multi-user.target
  ```

  Then run `sudo systemctl start nginx` to start the server. To start it automatically at boot, run `sudo systemctl enable nginx`.

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
