#!/bin/bash

set -e

CHECKER="node_modules/.bin/check-dependencies"
INSTALLER="bun install"

if [[ ! -x ${CHECKER} ]]; then
    bun install check-dependencies
fi

# We suppress output for the next command because, annoyingly, it reports
# that a dependency is unsatisfied even if the --install flag is specified,
# and that package has been successfully installed
if ${CHECKER} ; then
    status=0
else
    status=1
fi

if [ ${status} -ne 0 ]; then
    echo "✗ Some Javascript dependencies are unsatisfied."
    echo "✗ Attempting to install missing dependencies..."
    ${INSTALLER}
fi

# Print report, if any unsatisfied dependencies remain
if ${CHECKER}; then
    echo "✓ All Javascript dependencies satisfied."
fi
