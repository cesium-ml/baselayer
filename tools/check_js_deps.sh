#!/bin/bash

set -e

INSTALLER=$(PYTHONPATH=. uv run python baselayer/tools/get_js_installer.py)
CHECKER="node_modules/.bin/check-dependencies"

BOLD="\033[1m"
NORMAL="\033[0m"

if [[ ! -x ${CHECKER} ]]; then
    echo -e "${BOLD}[·] Installing JavaScript packages${NORMAL}"
    $INSTALLER install check-dependencies
fi

# Show the installer's output only when it installs
if ${CHECKER} >/dev/null 2>&1; then
    echo "[✓] JavaScript packages"
else
    echo -e "${BOLD}[·] Installing JavaScript packages${NORMAL}"
    $INSTALLER install
    # Print a report if unsatisfied dependencies remain
    if ${CHECKER}; then
        echo "[✓] JavaScript packages"
    else
        echo "[✗] JavaScript packages"
    fi
fi
