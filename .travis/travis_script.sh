#!/bin/bash

set -ex


section "Tests"

(cd ../baselayer_template_app && (make log &) && make ${TEST_TARGET})

section_end "Tests"

section "Build.docs"

make baselayer_html

section_end "Build.docs"
