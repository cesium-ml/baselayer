#!/bin/bash

set -e

INSTALLER=$(PYTHONPATH=. uv run python baselayer/tools/get_js_installer.py)
CHECKER="node_modules/.bin/check-dependencies"

BOLD="\033[1m"
NORMAL="\033[0m"

# Show the installer's output only when it installs
if [[ -x ${CHECKER} ]] && ${CHECKER} >/dev/null 2>&1; then
    echo "[✓] JavaScript packages"
    exit 0
fi

echo -e "${BOLD}[·] Installing JavaScript packages${NORMAL}"
if [[ ! -x ${CHECKER} ]]; then
    $INSTALLER install check-dependencies
fi
$INSTALLER install

# Print a report if unsatisfied dependencies remain
if ! ${CHECKER}; then
    echo "[✗] JavaScript packages"
    exit 1
fi
echo "[✓] JavaScript packages"
