# `baselayer`: A Web Application Template

## About

Tornado-based, customizable web application template.

Edit `public/index.html`, add your own JavaScript code to `public/scripts`,
add handlers for your routes to `webapp/handlers`, and watch your app fly!

## Running the app locally
1. Install the following dependencies:

- supervisor
- nginx
- npm

### MacOS
Using [Homebrew](http://brew.sh/):

`brew install supervisor nginx node`

### Linux
On Debian or Ubuntu:
```
sudo apt-get install nginx supervisor npm nodejs-legacy
```

2. Install Python and npm dependencies: `make dependencies`
3. Run `make` to start the server, and navigate to `localhost:7000`.

## Dev Tips
Debugging:

- Run `make log` to watch log output
- Run `make debug` to start webserver in debug mode
- Run `make attach` to attach to output of webserver, e.g. for use with `pdb.set_trace()`
