#!/bin/bash

set -e

# in this script, we want to use bun install to check if all the dependencies are installed
# if we run bun install and:
# - it contains and error message, print it out and exit
# - it contains "(no changes)" in the output, then we know all the dependencies are installed
# - otherwise, we tell the user that there are missing dependencies that were installed

INSTALLER="bun install"

# first run it and save the output
output=$(${INSTALLER} 2>&1)

# if we got an error message, print it out and exit with an error
if [ $? -ne 0 ]; then
    echo "✗ Error installing Javascript dependencies:"
    echo "${output}"
    exit 1
fi

# check if the output contains "(no changes)"
if echo "${output}" | grep -q "(no changes)"; then
     echo "✓ All Javascript dependencies satisfied."
else
    echo "✗ Some Javascript dependencies are unsatisfied."
    echo "✓ Missing dependencies have been installed."
fi
