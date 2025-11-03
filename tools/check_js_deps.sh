#!/bin/bash

set -e

INSTALLER=$(python baselayer/tools/get_js_installer.py)
CHECKER="node_modules/.bin/check-dependencies"

if [[ ! -x ${CHECKER} ]]; then
    echo "$" $INSTALLER install check-dependencies
    $INSTALLER install check-dependencies
fi

# We suppress output for the next command because, annoyingly, it reports
# that a dependency is unsatisfied even if the --install flag is specified,
# and that package has been successfully installed
echo "$" ${CHECKER} --package-manager $INSTALLER --install
${CHECKER} --package-manager $INSTALLER --install

# Print report, if any unsatisfied dependencies remain
if ${CHECKER}; then
    echo "✓ All Javascript dependencies satisfied."
fi
