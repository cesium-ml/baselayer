import pytest
import distutils.spawn
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions
from selenium.common.exceptions import TimeoutException
from seleniumrequests.request import RequestMixin
import os
from baselayer.app import models
from baselayer.app.config import load_config


cfg = load_config()


def set_server_url(server_url):
    """Set web driver server URL using value loaded from test config file."""
    MyCustomWebDriver.server_url = server_url


class MyCustomWebDriver(RequestMixin, webdriver.Firefox):
    @property
    def server_url(self):
        if not hasattr(self, '_server_url'):
            raise NotImplementedError("Please first set the web driver URL"
                                      " using `set_server_url`")
        return self._server_url

    @server_url.setter
    def server_url(self, value):
        self._server_url = value

    def get(self, uri):
        return webdriver.Firefox.get(self, self.server_url + uri)

    def wait_for_xpath(self, xpath, timeout=5):
        return WebDriverWait(self, timeout).until(
            expected_conditions.presence_of_element_located((By.XPATH, xpath)))

    def wait_for_xpath_to_disappear(self, xpath, timeout=5):
        return WebDriverWait(self, timeout).until_not(
            expected_conditions.presence_of_element_located((By.XPATH, xpath)))


@pytest.fixture(scope='session')
def driver(request):
    from selenium import webdriver
    profile = webdriver.FirefoxProfile()

    profile.set_preference("browser.download.manager.showWhenStarting", False)
    profile.set_preference("browser.download.folderList", 2)
    profile.set_preference("browser.download.dir",
                           os.path.abspath(cfg['paths.downloads_folder']))
    profile.set_preference("browser.helperApps.neverAsk.saveToDisk",
                           ("text/csv,text/plain,application/octet-stream,"
                            "text/comma-separated-values,text/html"))

    driver = MyCustomWebDriver(firefox_profile=profile)
    driver.set_window_size(1920, 1200)
    login(driver)

    yield driver

    driver.close()


def login(driver):
    username_xpath = '//*[contains(string(),"testuser@cesium-ml.org")]'

    driver.get('/')
    try:
        driver.wait_for_xpath(username_xpath, 0.25)
        return  # Already logged in
    except TimeoutException:
        pass

    try:
        element = driver.wait_for_xpath('//a[contains(@href,"/login/google-oauth2")]', 5)
        element.click()
    except TimeoutException:
        pass

    try:
        driver.wait_for_xpath(username_xpath, 5)
    except TimeoutException:
        raise TimeoutException("Login failed:\n" + driver.page_source)


@pytest.fixture(scope='function', autouse=True)
def reset_state(request):
    def teardown():
        models.DBSession().rollback()
    request.addfinalizer(teardown)
