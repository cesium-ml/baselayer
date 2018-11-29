#!/bin/bash

set -ex

section "install.base.requirements"

# Install v1.7 or newer of nginx to support 'if' statement for logging
sudo apt-add-repository -y ppa:nginx/stable
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

pip list --format=columns
section_end "install.baselayer.requirements"

section "init.baselayer"
make db_init
section_end "init.baselayer"

section "install.geckodriver.and.selenium"
wget https://github.com/mozilla/geckodriver/releases/download/v0.20.0/geckodriver-v0.20.0-linux64.tar.gz
sudo tar -xzf geckodriver-v0.20.0-linux64.tar.gz -C /usr/local/bin
rm geckodriver-v0.20.0-linux64.tar.gz
which geckodriver
geckodriver --version
pip install --upgrade selenium
python -c "import selenium; print(f'Selenium {selenium.__version__}')"
section_end "install.geckodriver.and.selenium"
