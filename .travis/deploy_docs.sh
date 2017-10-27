#!/bin/bash

set -e

if [[ $TRAVIS_PULL_REQUEST == false && \
      $TRAVIS_BRANCH == "master" ]]
then
    pip install doctr==1.6.1
    doctr deploy --gh-pages-docs '.' --deploy-repo "cesium-ml/baselayer"
else
    echo "-- will only push docs from master --"
fi

