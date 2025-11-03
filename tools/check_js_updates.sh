#!/bin/bash

set -e

export NPM_CHECK_INSTALLER=$(python baselayer/tools/get_js_installer.py)
CHECKER="npx npm-check"

if ( ! $CHECKER --version > /dev/null 2>&1 ); then
    echo "Update checker not found; installing."
    echo "$" $INSTALLER install npm-check
    $INSTALLER install npm-check
fi

echo "$" NPM_CHECK_INSTALLER=$NPM_CHECK_INSTALLER ${CHECKER} --skip-unused -u

${CHECKER} --skip-unused -u
