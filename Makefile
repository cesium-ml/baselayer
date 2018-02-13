SHELL = /bin/bash
SUPERVISORD=PYTHONPATH=. FLAGS=$$FLAGS supervisord -c baselayer/conf/supervisor/supervisor.conf
SUPERVISORCTL=PYTHONPATH=. FLAGS=$$FLAGS supervisorctl -c baselayer/conf/supervisor/supervisor.conf
ENV_SUMMARY=PYTHONPATH=. baselayer/tools/env_summary.py $$FLAGS
ESLINT=./node_modules/.bin/eslint

.DEFAULT_GOAL := run

bundle = static/build/bundle.js
webpack = node_modules/.bin/webpack

# NOTE: These targets are meant to be *included* in the parent app
#       Makefile.  See end of this file for baselayer specific targets.

.PHONY: clean dependencies db_init db_clear bundle bundle-watch paths
.PHONY: fill_conf_values log run run_production run_testing monitor attach
.PHONY: stop status test_headless test check-js-updates lint-install
.PHONY: lint lint-unix lint-githook baselayer_doc_reqs html

help:
	@python ./baselayer/tools/makefile_to_help.py $(MAKEFILE_LIST)

dependencies: README.md
	@cd baselayer && ./tools/check_app_environment.py
	@./baselayer/tools/silent_monitor.py pip install -r baselayer/requirements.txt
	@./baselayer/tools/silent_monitor.py pip install -r requirements.txt
	@./baselayer/tools/silent_monitor.py baselayer/tools/check_js_deps.sh

db_init: ## Initialize database and models.
db_init: dependencies
	@echo -e "\nInitializing database:"
	@PYTHONPATH=. baselayer/tools/db_init.py

db_clear: ## Delete all data from the database.
db_clear: dependencies
	@PYTHONPATH=. baselayer/tools/silent_monitor.py baselayer/tools/db_init.py -f

$(bundle): webpack.config.js package.json
	$(webpack)

bundle: $(bundle)

bundle-watch:
	$(webpack) -w

paths:
	@mkdir -p log run tmp
	@mkdir -p ./log/sv_child

fill_conf_values:
	@echo -e "[-] Compiling configuration templates"
	@find ./baselayer -name "*.template" | PYTHONPATH=. xargs ./baselayer/tools/fill_conf_values.py

log: ## Monitor log files for all services.
log: paths fill_conf_values
	PYTHONUNBUFFERED=1 baselayer/tools/watch_logs.py

run: ## Start the web application.
run: paths dependencies fill_conf_values
	@echo "Supervisor will now fire up various micro-services."
	@echo
	@echo " - Run \`make log\` in another terminal to view logs"
	@echo " - Run \`make monitor\` in another terminal to restart services"
	@echo
	@echo "The server is in debug mode:"
	@echo "  JavaScript and Python files will be reloaded upon change."
	@echo

	@export FLAGS="--config config.yaml --debug" && \
	$(ENV_SUMMARY) && echo && \
	echo "Press Ctrl-C to abort the server" && \
	echo && \
	$(SUPERVISORD)

run_production: ## Run the web application in production mode (no dependency checking).
run_production: paths fill_conf_values
	@echo
	@echo "[!] Production run: not automatically installing dependencies."
	@echo
	export FLAGS="--config config.yaml" && \
	$(ENV_SUMMARY) && \
	$(SUPERVISORD)

run_testing: paths dependencies fill_conf_values
	export FLAGS="--config test_config.yaml" && \
	$(ENV_SUMMARY) && \
	$(SUPERVISORD)

monitor: ## Monitor microservice status.
	@echo "Entering supervisor control panel."
	@echo " - Type \`status\` too see microservice status"
	$(SUPERVISORCTL) -i status

# Attach to terminal of running webserver; useful to, e.g., use pdb
attach:
	$(SUPERVISORCTL) fg app

clean:
	rm -f $(bundle)

stop: ## Stop all running services.
	$(SUPERVISORCTL) stop all

status:
	PYTHONPATH='.' ./baselayer/tools/supervisor_status.py

test_headless: ## Run tests headlessly with xvfb (Linux only).
test_headless: paths dependencies fill_conf_values
	PYTHONPATH='.' xvfb-run baselayer/tools/test_frontend.py

test: ## Run tests.
test: paths dependencies fill_conf_values
	PYTHONPATH='.' ./baselayer/tools/test_frontend.py

# Call this target to see which Javascript dependencies are not up to date
check-js-updates:
	./baselayer/tools/check_js_updates.sh

# Lint targets
lint-install: ## Install ESLint and a git pre-commit hook.
lint-install: cp-lint-yaml lint-githook
	./baselayer/tools/update_eslint.sh

cp-lint-yaml: ## Copy eslint config file to parent app if not present
	if ! [ -e .eslintrc.yaml ]; then cp baselayer/.eslintrc.yaml .eslintrc.yaml; fi

$(ESLINT): lint-install

lint: ## Check JavaScript code style.
	$(ESLINT) --ext .jsx,.js -c .eslintrc.yaml static/js

lint-unix:
	$(ESLINT) --ext .jsx,.js -c .eslintrc.yaml --format=unix static/js

lint-githook:
	cp baselayer/.git-pre-commit .git/hooks/pre-commit


# baselayer-specific targets
# All other targets are run from the parent app.  The following are related to
# baselayer itself, and will be run from the baselayer repo root.

# Documentation targets, run from the `baselayer` directory
baselayer_doc_reqs:
	pip install -q -r requirements.docs.txt

baselayer_html: | baselayer_doc_reqs
	export SPHINXOPTS=-W; make -C doc html
