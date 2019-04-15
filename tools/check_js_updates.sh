#!/bin/bash

set -e

CHECKER="npx ncu"

if ( ! $CHECKER --version > /dev/null 2>&1 ); then
    echo "Update checker not found; installing."
    npm install npm-check-updates
fi

${CHECKER}
