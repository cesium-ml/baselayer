#!/bin/bash

set -ex


section "Tests"

(cd ../baselayer_template_app && (make log &) && make ${TEST_TARGET})

(cd ../skyportal && (make log &) && make ${TEST_TARGET} TEST_SPEC="skyportal/tests/models/test_permissions.py,-k,\'stream,or,classification,or,followup_request,or,group\'")

section_end "Tests"

section "Build.docs"

make baselayer_html

section_end "Build.docs"
