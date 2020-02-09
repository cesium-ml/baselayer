SHELL = /bin/bash
ESLINT=npx eslint

.DEFAULT_GOAL := help

# Use `config.yaml` by default, unless overridden by user
# through setting FLAGS environment variable
FLAGS:=$(if $(FLAGS),$(FLAGS),"--config=config.yaml")

PYTHON=PYTHONPATH=. python
ENV_SUMMARY=$(PYTHON) baselayer/tools/env_summary.py $(FLAGS)

# Flags are propagated to supervisord via the FLAGS environment variable
# Inside of supervisord configuration files, you may reference them using
# %(ENV_FLAGS)s
SUPERVISORD_CFG=baselayer/conf/supervisor/supervisor.conf
SUPERVISORD=export FLAGS=$(FLAGS) && $(PYTHON) -m supervisor.supervisord -c $(SUPERVISORD_CFG)
SUPERVISORCTL=$(PYTHON) -m supervisor.supervisorctl -c $(SUPERVISORD_CFG)

LOG=@$(PYTHON) -c "from baselayer.log import make_log; spl = make_log('baselayer'); spl('$1')"

# Bold
B=\033[1m
# Normal
N=\033[0m

bundle = static/build/bundle.js
webpack = npx webpack

# NOTE: These targets are meant to be *included* in the parent app
#       Makefile.  See end of this file for baselayer specific targets.

.PHONY: clean dependencies db_init db_clear bundle bundle-watch paths
.PHONY: fill_conf_values log run run_production run_testing monitor attach
.PHONY: stop status test_headless test test-nginx-config check-js-updates
.PHONY: lint-install lint lint-unix lint-githook baselayer_doc_reqs html

help:
	@python ./baselayer/tools/makefile_to_help.py $(MAKEFILE_LIST)

dependencies: README.md
	@cd baselayer && ./tools/check_app_environment.py
	@PYTHONPATH=. python baselayer/tools/pip_install_requirements.py baselayer/requirements.txt requirements.txt
	@./baselayer/tools/silent_monitor.py baselayer/tools/check_js_deps.sh

db_init: ## Initialize database and models.
db_init: dependencies
	@echo -e "\nInitializing database:"
	@PYTHONPATH=. baselayer/tools/db_init.py $(FLAGS)

db_clear: ## Delete all data from the database.
db_clear: dependencies
	@PYTHONPATH=. baselayer/tools/silent_monitor.py baselayer/tools/db_init.py -f $(FLAGS)

$(bundle): webpack.config.js package.json
	$(webpack)

bundle: $(bundle)

bundle-watch:
	$(webpack) -w

paths:
	@mkdir -p log run tmp
	@mkdir -p ./log/sv_child

fill_conf_values:
	@find ./baselayer -name "*.template" | PYTHONPATH=. xargs ./baselayer/tools/fill_conf_values.py $(FLAGS)

log: ## Monitor log files for all services.
log: paths
	@PYTHONPATH=. PYTHONUNBUFFERED=1 baselayer/tools/watch_logs.py

run: ## Start the web application.
run: paths dependencies fill_conf_values
	@echo
	$(call LOG, Starting micro-services)
	@echo
	@echo " - Run \`make log\` in another terminal to view logs"
	@echo " - Run \`make monitor\` in another terminal to restart services"
	@echo
	@echo "The server is in debug mode:"
	@echo
	@echo "  JavaScript and Python files will be reloaded upon change."
	@echo

	@$(ENV_SUMMARY) && echo && \
	echo "Press Ctrl-C to abort the server" && \
	echo && \
	$(SUPERVISORD)

run_production: ## Run the web application in production mode (no dependency checking).
run_production: paths fill_conf_values
	@echo "[!] Production run: not automatically installing dependencies."
	@echo
	$(ENV_SUMMARY) && \
	$(SUPERVISORD)

run_testing: FLAGS = "--config=test_config.yaml"  # both this and the next FLAGS definition are needed
run_testing: paths dependencies fill_conf_values
	@echo -e "\n$(B)[baselayer] Launch app for testing$(N)"
	@export FLAGS=$(FLAGS) && \
	$(ENV_SUMMARY) && \
	$(SUPERVISORD)

monitor: ## Monitor microservice status.
	@echo "Entering supervisor control panel."
	@echo
	@echo " - Type \`status\` to see microservice status"
	@echo
	@$(SUPERVISORCTL) -i

attach: ## Attach to terminal of running webserver; useful to, e.g., use pdb.
	$(SUPERVISORCTL) fg app

clean:
	rm -f $(bundle)

stop: ## Stop all running services.
	$(SUPERVISORCTL) stop all

status:
	@PYTHONPATH='.' ./baselayer/tools/supervisor_status.py

test_headless: ## Run tests headlessly with xvfb (Linux only).
test_headless: paths dependencies fill_conf_values
	@PYTHONPATH='.' xvfb-run baselayer/tools/test_frontend.py

test: ## Run tests.
test: paths dependencies fill_conf_values
	@PYTHONPATH='.' ./baselayer/tools/test_frontend.py

test-nginx-config: ## Check nginx configuration.
	@PWD=$(shell pwd); \
	echo $(PWD) ; \
	nginx -t -p $(PWD) -c baselayer/conf/nginx.conf 2>&1 | grep -v "could not open error log"

# Call this target to see which Javascript dependencies are not up to date
check-js-updates:
	./baselayer/tools/check_js_updates.sh

# Lint targets
lint-install: ## Install ESLint and a git pre-commit hook.
lint-install: cp-lint-yaml lint-githook
	@echo "Installing latest version of ESLint and AirBNB style rules"
	@./baselayer/tools/update_eslint.sh

cp-lint-yaml: # Copy eslint config file to parent app if not present
	@if ! [ -e .eslintrc.yaml ]; then \
	  echo "No ESLint configuration found; copying baselayer's version of .eslintrc.yaml"; \
	  cp baselayer/.eslintrc.yaml .eslintrc.yaml; \
	fi

$(ESLINT): lint-install

lint: ## Check JavaScript code style.
	$(ESLINT) --ext .jsx,.js -c .eslintrc.yaml static/js

lint-unix:
	$(ESLINT) --ext .jsx,.js -c .eslintrc.yaml --format=unix static/js

lint-githook:
	@if ! [ -e .git/hooks/pre-commit ]; then \
	  echo "Installing ESLint pre-commit hook into \`.git/hooks/pre-commit\`"; \
	  cp baselayer/.git-pre-commit .git/hooks/pre-commit; \
	fi

# baselayer-specific targets
# All other targets are run from the parent app.  The following are related to
# baselayer itself, and will be run from the baselayer repo root.

# Documentation targets, run from the `baselayer` directory
baselayer_doc_reqs:
	pip install -q -r requirements.docs.txt

baselayer_html: | baselayer_doc_reqs
	export SPHINXOPTS=-W; make -C doc html
