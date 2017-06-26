#!/bin/bash

set -ex

section "install.base.requirements"

# Install v1.7 or newer of nginx to support 'if' statement for logging
sudo apt-add-repository -y ppa:nginx/development
sudo apt update
sudo apt install -y nginx

pip install --upgrade pip
hash -d pip  # find upgraded pip
section_end "install.base.requirements"

section "install.baselayer.requirements"
cd ..
git clone git://github.com/cesium-ml/baselayer_template_app
cp -rf baselayer baselayer_template_app/
cd baselayer_template_app
npm -g install npm@4.2.0
npm --version
node --version
make dependencies
make check-js-updates

pip list --format=columns
section_end "install.baselayer.requirements"


section "init.baselayer"
make paths
make db_init
make bundle
section_end "init.baselayer"


section "install.chromedriver"
wget https://chromedriver.storage.googleapis.com/2.29/chromedriver_linux64.zip
sudo unzip chromedriver_linux64.zip chromedriver -d /usr/local/bin
rm chromedriver_linux64.zip
which chromium-browser
chromium-browser --version
section_end "install.chromedriver"
