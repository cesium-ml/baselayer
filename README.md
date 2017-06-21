# `baselayer`: A Web Application Template

Baselayer is a "batteries included" web application template that includes:

- a Tornado-based Python web application template to customize to your liking
- WebSockets
- JavaScript 6 compilation via Babel, with Redux & React frontend
- Process management via supervisord
- Proxy configuration via nginx
- Authentication (currently using Google) via Python Social Auth
- Distributed task computation, via `dask` and `distributed`

Please clone and try our example application at

https://github.com/cesium-ml/baselayer_template_app

## Setup

To be completed.

## Dependencies

To be completed.

### MacOS

Using [Homebrew](http://brew.sh/):

`brew install supervisor nginx node`

### Linux

On Debian or Ubuntu:
```
sudo apt-get install nginx supervisor npm nodejs-legacy
```

2. Install Python and npm dependencies: `make dependencies`
3. Run `make` to start the server, and navigate to `localhost:5000`.

## Dev Tips

To be completed.

Debugging:


- Run `make log` to watch log output
- Run `make debug` to start webserver in debug mode
- Run `make attach` to attach to output of webserver, e.g. for use with `pdb.set_trace()`

