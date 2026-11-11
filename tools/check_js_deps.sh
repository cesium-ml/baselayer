#!/bin/bash

set -e

INSTALLER=$(PYTHONPATH=. uv run python baselayer/tools/get_js_installer.py)
CHECKER="node_modules/.bin/check-dependencies"

if [[ ! -x ${CHECKER} ]]; then
    echo "$" $INSTALLER install check-dependencies
    $INSTALLER install check-dependencies
fi

${CHECKER} --package-manager $INSTALLER --install

# Print a report if unsatisfied dependencies remain
${CHECKER} || true
