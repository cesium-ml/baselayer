#!/bin/bash

set -e

CHECKER="npx npm-check"

if ( ! $CHECKER --version > /dev/null 2>&1 ); then
    echo "Update checker not found; installing."
    pnpm install npm-check
fi

${CHECKER} --skip-unused -u
