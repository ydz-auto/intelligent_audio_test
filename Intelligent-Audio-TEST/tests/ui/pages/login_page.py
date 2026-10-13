# -*- coding: utf-8 -*-
"""登录页 Page Object：表单登录 / 错误提示 / 跳转断言锚点。"""
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from .base_page import BasePage


class LoginPage(BasePage):
    ROUTE = '/login'

    USERNAME_INPUT = '.login-card form input[type="text"]'
    PASSWORD_INPUT = '.login-card form input[type="password"]'
    SUBMIT_BTN = '.login-card form button.login-btn'
    ERROR_MSG = '.login-card .error-msg'
    LOGIN_TAB = '.login-card .tab-btn:nth-child(1)'
    CARD = '.login-card'

    def is_at_login(self, timeout: float = 15) -> bool:
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, self.CARD)))
            return True
        except TimeoutException:
            return False

    def login(self, username: str, password: str):
        self.fill(self.USERNAME_INPUT, username)
        self.fill(self.PASSWORD_INPUT, password)
        self.click(self.SUBMIT_BTN)

    def error_text(self, timeout: float = 8) -> str:
        el = self.wait_visible(self.ERROR_MSG, timeout)
        return el.text.strip()

    def wait_left_login(self, timeout: float = 20) -> bool:
        """登录成功后路由离开 /login（跳转断言锚点）。"""
        try:
            WebDriverWait(self.driver, timeout).until(
                lambda d: '/login' not in d.current_url.split('#')[-1])
            return True
        except TimeoutException:
            return False

    def wait_home_rendered(self, timeout: float = 20) -> bool:
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, '.main-content')))
            return True
        except TimeoutException:
            return False
