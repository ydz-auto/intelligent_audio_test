# -*- coding: utf-8 -*-
"""Page Object 基类（INT-260）：登录态复用、等待策略、失败取证钩子。

约定：
- 所有定位等待走显式 WebDriverWait，禁止硬 sleep 兜底（_settle 仅用于
  渲染稳定余量，单点 <=0.5s）；
- headless 输入丢键（既有 e2e_tests/selenium 实证）→ _fill 读回校验，
  不符则 JS 直写 + 派发 input 事件（Vue v-model 监听 input）；
- 登录态复用：_inject_login_state 把 API 登录得到的 token/用户写入
  localStorage（authStore 的 TOKEN_KEY/USER_KEY），免去每条用例重复
  走登录表单——登录表单本身由专属用例覆盖。
"""
import json
import os
import time

from selenium.common.exceptions import (
    ElementClickInterceptedException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# authStore 的 localStorage 键（frontend/src/store/authStore.ts）
TOKEN_KEY = 'auth_token'
USER_KEY = 'auth_user'

# 失败取证输出根目录（issue 口径：tests/ui/artifacts/）
ARTIFACTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'artifacts')


class BasePage:
    """所有页面对象的基类：持 driver + 显式等待 + 登录态注入 + 取证。"""

    # 子类指定页面 hash 路由（如 '/TestCaseManager'）
    ROUTE = '/'

    def __init__(self, driver: WebDriver, base_url: str, timeout: int = 20):
        self.driver = driver
        self.base_url = base_url.rstrip('/')
        self.wait = WebDriverWait(driver, timeout)
        self.short_wait = WebDriverWait(driver, 6)

    # ── 导航 ──────────────────────────────────────────────
    def goto(self, route: str = ''):
        self.driver.get(f'{self.base_url}/#{route or self.ROUTE}')
        return self

    def current_route(self) -> str:
        return self.driver.current_url.split('#', 1)[-1] if '#' in self.driver.current_url else '/'

    def page_title_text(self) -> str:
        els = self.driver.find_elements(By.CSS_SELECTOR, '.page-title')
        return els[0].text.strip() if els else ''

    def document_title(self) -> str:
        return self.driver.title

    # ── 登录态复用 ────────────────────────────────────────
    def inject_login_state(self, token: str, user: dict):
        """把 API 登录态写入 localStorage 并整页重启应用。

        必须强刷：hash 路由的同文档导航不会重启应用，pinia authStore 的
        in-memory token 仍为空，路由守卫会继续弹回登录页；refresh 让应用
        以已注入的 token 重新 boot（init 从 localStorage 读回登录态）。
        """
        self.driver.get(f'{self.base_url}/#/login')
        self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.login-card')))
        # authStore 持久化口径：camelCase AuthUser + 原始 token
        payload = {
            'id': user.get('id', 0),
            'username': user.get('username', ''),
            'roleId': user.get('role_id'),
            'roleName': user.get('role_name', ''),
            'permissions': user.get('permissions', []),
        }
        self.driver.execute_script(
            'window.localStorage.setItem(arguments[0], arguments[1]);'
            'window.localStorage.setItem(arguments[2], arguments[3]);',
            TOKEN_KEY, token, USER_KEY, json.dumps(payload),
        )
        self.driver.refresh()
        return self

    def clear_login_state(self):
        self.driver.execute_script('window.localStorage.clear();')
        return self

    # ── 等待策略 ──────────────────────────────────────────
    def find(self, css: str, timeout: float = 10):
        return WebDriverWait(self.driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, css)))

    def find_visible(self, css: str, timeout: float = 10):
        return WebDriverWait(self.driver, timeout).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, css)))

    def find_all(self, css: str):
        return self.driver.find_elements(By.CSS_SELECTOR, css)

    def wait_visible(self, css: str, timeout: float = 10):
        return WebDriverWait(self.driver, timeout).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, css)))

    def wait_title_text(self, text: str, timeout: float = 15):
        """等待 .page-title 元素内出现指定标题文本。

        INT-467（测试时序修正）：hash 路由同文档跳转后，上一页的 .page-title 仍在 DOM 中，
        仅 wait_visible('.page-title') 会命中残留标题；须按目标标题文本等待（
        EC.text_to_be_present_in_element），避免读到上一页标题误判已导航完成。
        """
        return WebDriverWait(self.driver, timeout).until(
            EC.text_to_be_present_in_element((By.CSS_SELECTOR, '.page-title'), text))

    def wait_gone(self, css: str, timeout: float = 10) -> bool:
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.invisibility_of_element_located((By.CSS_SELECTOR, css)))
            return True
        except TimeoutException:
            return False

    def exists(self, css: str) -> bool:
        return bool(self.driver.find_elements(By.CSS_SELECTOR, css))

    def settle(self, seconds: float = 0.4):
        time.sleep(seconds)

    # ── 交互原语 ──────────────────────────────────────────
    def fill(self, css: str, value: str, timeout: float = 10):
        """输入框填写：headless 丢键防御（读回校验 → JS 直写派发 input）。"""
        el = self.find_visible(css, timeout)
        el.clear()
        el.click()
        el.send_keys(str(value))
        self.settle(0.2)
        if (el.get_attribute('value') or '') != str(value):
            self.driver.execute_script(
                "arguments[0].value = arguments[1];", el, str(value))
            self.driver.execute_script(
                "arguments[0].dispatchEvent(new Event('input', {bubbles: true}));", el)
            self.settle(0.2)
        return el

    def click(self, css: str, timeout: float = 10):
        el = WebDriverWait(self.driver, timeout).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, css)))
        try:
            el.click()
        except (ElementClickInterceptedException, StaleElementReferenceException):
            self.driver.execute_script('arguments[0].click();', el)
        return el

    def click_xpath(self, xpath: str, timeout: float = 10):
        el = WebDriverWait(self.driver, timeout).until(
            EC.element_to_be_clickable((By.XPATH, xpath)))
        try:
            el.click()
        except (ElementClickInterceptedException, StaleElementReferenceException):
            # 覆盖层拦截/元素重渲染兜底：JS 直点，Vue 事件委托必达
            self.driver.execute_script('arguments[0].click();', el)
        return el

    def js_click(self, css: str, timeout: float = 10):
        """可见后 JS 直点：侧栏 footer 等被透明覆盖层吞原生点击的区域用。"""
        el = self.find_visible(css, timeout)
        self.driver.execute_script('arguments[0].click();', el)
        return el

    def hover(self, css: str, timeout: float = 10):
        el = self.find_visible(css, timeout)
        ActionChains(self.driver).move_to_element(el).perform()
        return el

    # ── 失败取证（供 conftest 失败钩子调用）────────────────
    def capture_artifacts(self, out_dir: str) -> list:
        """截图 + console 日志 + 页面源码落盘，返回落盘路径列表。"""
        os.makedirs(out_dir, exist_ok=True)
        saved = []
        try:
            png = os.path.join(out_dir, 'screenshot.png')
            self.driver.save_screenshot(png)
            saved.append(png)
        except WebDriverException:
            pass
        try:
            with open(os.path.join(out_dir, 'page.html'), 'w', encoding='utf-8') as fh:
                fh.write(self.driver.page_source)
            saved.append(os.path.join(out_dir, 'page.html'))
        except WebDriverException:
            pass
        try:
            logs = self.driver.get_log('browser')
            lines = [f"[{e['level']}] {e['source']}: {e['message']}" for e in logs]
            with open(os.path.join(out_dir, 'console.log'), 'w', encoding='utf-8') as fh:
                fh.write('\n'.join(lines) or '(no console entries)')
            saved.append(os.path.join(out_dir, 'console.log'))
        except WebDriverException:
            pass
        return saved

    @staticmethod
    def node_artifact_dir(node_id: str) -> str:
        safe = node_id.replace('::', '__').replace('/', '_').replace('[', '_').replace(']', '')
        return os.path.join(ARTIFACTS_DIR, safe)
