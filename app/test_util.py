import pytest
import distutils.spawn
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions
from selenium.common.exceptions import (TimeoutException,
                                        ElementClickInterceptedException)
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
            expected_conditions.presence_of_element_located((By.XPATH, xpath))
        )

    def wait_for_css(self, css, timeout=5):
        return WebDriverWait(self, timeout).until(
            expected_conditions.presence_of_element_located((By.CSS, css))
        )

    def wait_for_xpath_to_disappear(self, xpath, timeout=5):
        return WebDriverWait(self, timeout).until_not(
            expected_conditions.presence_of_element_located((By.XPATH, xpath))
        )

    def wait_for_css_to_disappear(self, css, timeout=5):
        return WebDriverWait(self, timeout).until_not(
            expected_conditions.presence_of_element_located((By.CSS, css))
        )

    def wait_for_xpath_to_be_clickable(self, xpath, timeout=5):
        return WebDriverWait(self, timeout).until(
            expected_conditions.element_to_be_clickable((By.XPATH, xpath))
        )

    def wait_for_css_to_be_clickable(self, css, timeout=5):
        return WebDriverWait(self, timeout).until(
            expected_conditions.element_to_be_clickable((By.CSS, css))
        )

    def scroll_to_element_and_click(self, element):
        ActionChains(self).move_to_element(element).perform()
        return element.click()

    def click_xpath(self, xpath):
        element = self.wait_for_xpath_to_be_clickable(xpath)
        return self.scroll_to_element_and_click(element)

    def click_css(self, xpath):
        element = self.wait_for_css_to_be_clickable(xpath)
        return self.scroll_to_element_and_click(element)

    def become_user(self, user_id):
        self.wait_for_css("body").send_keys(Keys.CONTROL + "t")
        self.get(f'/become_user/{user_id}')
        self.wait_for_css("body").send_keys(Keys.CONTROL + "w")

        self.execute_script(f"window.open('{self.server_url + '/become_user/{user_id}'}', 'new_window')")
        driver.switch_to_window(driver.window_handles[0])


        browser.find_element_by_tag_name("body").send_keys(Keys.COMMAND + 
Keys.NUMPAD2)


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
