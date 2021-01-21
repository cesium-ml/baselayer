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

# this line should be modified to skyportal/skyportal before the PR is
# merged, only here now because the SkyPortal permissions PR hasn't
# been merged to master yet, so can't use master to get the
# permissions model tests
git clone git://github.com/dannygoldstein/skyportal
cp -rf baselayer baselayer_template_app/
cp -rf baselayer skyportal/

# this line should be deleted before the PR is merged,
# only here now because the SkyPortal permissions PR
# hasn't been merged to master yet, so can't use master
# to get the permissions model tests
cd skyportal && git checkout a11fdf3 && cd - 
cd baselayer_template_app
npm -g install npm@next
npm --version
node --version

pip list --format=columns
section_end "install.baselayer.requirements"

section "init.baselayer"
make db_init
section_end "init.baselayer"

section "install.geckodriver.and.selenium"
GECKO_VER=0.24.0
wget https://github.com/mozilla/geckodriver/releases/download/v${GECKO_VER}/geckodriver-v${GECKO_VER}-linux64.tar.gz
sudo tar -xzf geckodriver-v${GECKO_VER}-linux64.tar.gz -C /usr/local/bin
rm geckodriver-v${GECKO_VER}-linux64.tar.gz
which geckodriver
geckodriver --version
pip install --upgrade selenium
python -c "import selenium; print(f'Selenium {selenium.__version__}')"
section_end "install.geckodriver.and.selenium"
