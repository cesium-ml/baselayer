SHELL = /bin/bash
SUPERVISORD=PYTHONPATH=. FLAGS=$$FLAGS supervisord -c baselayer/conf/supervisor/supervisor.conf
SUPERVISORCTL=PYTHONPATH=. FLAGS=$$FLAGS supervisorctl -c baselayer/conf/supervisor/supervisor.conf
ENV_SUMMARY=PYTHONPATH=. baselayer/tools/env_summary.py $$FLAGS
ESLINT=../node_modules/.bin/eslint

.DEFAULT_GOAL := run

bundle = ../static/build/bundle.js
webpack = node_modules/.bin/webpack

dependencies: README.md
	@./tools/silent_monitor.py pip install -r requirements.txt
	@./tools/silent_monitor.py pip install -r ../requirements.txt
	@cd .. && baselayer/tools/silent_monitor.py baselayer/tools/check_js_deps.sh

db_init: dependencies
	@cd .. && PYTHONPATH=. baselayer/tools/silent_monitor.py baselayer/tools/db_init.py

db_clear: dependencies
	@cd .. && PYTHONPATH=. baselayer/tools/silent_monitor.py baselayer/tools/db_init.py -f

$(bundle): ../webpack.config.js ../package.json
	cd .. && $(webpack)

bundle: $(bundle)

bundle-watch:
	$(webpack) -w

paths:
	@mkdir -p ../log ../run ../tmp
	@mkdir -p ../log/sv_child
	@mkdir -p ~/.local/cesium/logs

fill_conf_values:
	pip install -q pyyaml
	find . -name "*.template" | PYTHONPATH=.. xargs ./tools/fill_conf_values.py

log: paths fill_conf_values
	cd .. && PYTHONUNBUFFERED=1 baselayer/tools/watch_logs.py

run: paths dependencies fill_conf_values
	@echo "Supervisor will now fire up various micro-services."
	@echo
	@echo " - Run \`make log\` in another terminal to view logs"
	@echo " - Run \`make monitor\` in another terminal to restart services"
	@echo
	@echo "The server is in debug mode:"
	@echo "  JavaScript and Python files will be reloaded upon change."
	@echo

	@FLAGS="--debug" && \
	cd .. && \
	$(ENV_SUMMARY) && echo && \
	echo "Press Ctrl-C to abort the server" && \
	echo && \
	$(SUPERVISORD)

run_production: paths fill_conf_values
	@echo
	@echo "[!] Production run: not automatically installing dependencies."
	@echo
	export FLAGS="--config config.yaml" && \
	cd .. && \
	$(ENV_SUMMARY) && \
	$(SUPERVISORD)

run_testing: paths dependencies fill_conf_values
	export FLAGS="--config test_config.yaml" && \
	cd .. && \
	$(ENV_SUMMARY) && \
	$(SUPERVISORD)

monitor:
	@echo "Entering supervisor control panel."
	@echo " - Type \`status\` too see microservice status"
	$(SUPERVISORCTL) -i status

# Attach to terminal of running webserver; useful to, e.g., use pdb
attach:
	cd .. && $(SUPERVISORCTL) fg app

clean:
	rm -f $(bundle)

stop:
	$(SUPERVISORCTL) stop all

status:
	PYTHONPATH='..' ./tools/supervisor_status.py

test_headless: paths dependencies fill_conf_values
	cd .. && PYTHONPATH='.' xvfb-run baselayer/tools/test_frontend.py

test: paths dependencies fill_conf_values
	cd .. && PYTHONPATH='.' baselayer/tools/test_frontend.py

# Call this target to see which Javascript dependencies are not up to date
check-js-updates:
	cd .. && baselayer/tools/check_js_updates.sh
