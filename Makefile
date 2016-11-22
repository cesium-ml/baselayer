SHELL = /bin/bash
APP_NAME = webapp
SUPERVISORD=supervisord

.DEFAULT_GOAL := run

bundle = ./public/build/bundle.js
webpack = ./node_modules/.bin/webpack

dependencies:
	@./tools/install_deps.py requirements.txt
	@./tools/install_npm_deps.py package.json

$(bundle): webpack.config.js
	$(webpack)

bundle: $(bundle)

bundle-watch:
	$(webpack) -w

paths:
	mkdir -p log run tmp
	mkdir -p log/sv_child
	mkdir -p ~/.local/$(APP_NAME)/logs

log: paths
	./tools/watch_logs.py

run: paths dependencies
	$(SUPERVISORD) -c conf/supervisord.conf

debug:
	$(SUPERVISORD) -c conf/supervisord_debug.conf

# Attach to terminal of running webserver; useful to, e.g., use pdb
attach:
	supervisorctl -c conf/supervisord_common.conf fg app

clean:
	rm $(bundle)

status:
	PYTHONPATH='.' ./tools/supervisor_status.py

