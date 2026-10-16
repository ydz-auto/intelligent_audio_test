# -*- coding: utf-8 -*-
"""INT-500 返修验证：报告中心 Dialog 打开 + 收藏角标计数（P1/P2，测试打回复测）。

前置：dev server 运行于 5273（rsbuild 钉死端口）。真实 Chrome headless。
"""
import json
import os
import time

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int500_dialog_fix')

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5273')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium',
                              'chromedriver', 'win64')
    drv_path = ''
    if chrome_major and os.path.isdir(cache_root):
        cands = []
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
                except ValueError:
                    continue
        same = [exe for ver, exe in cands if ver and ver[0] == chrome_major]
        if same:
            drv_path = max(same)
    service = Service(executable_path=drv_path) if drv_path else Service()
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(45)
    return drv


_DRIVER = None
_CONSOLE_SEVERE = []


def _drain_console(drv):
    global _CONSOLE_SEVERE
    try:
        for entry in drv.get_log('browser'):
            if entry.get('level') == 'SEVERE':
                _CONSOLE_SEVERE.append(entry.get('message', ''))
    except Exception:
        pass


def _save_evidence(name, drv):
    d = os.path.join(ARTIFACTS, name)
    os.makedirs(d, exist_ok=True)
    try:
        drv.save_screenshot(os.path.join(d, 'screenshot.png'))
        with open(os.path.join(d, 'page_source.html'), 'w', encoding='utf-8') as f:
            f.write(drv.page_source)
        with open(os.path.join(d, 'console.log'), 'w', encoding='utf-8') as f:
            for entry in drv.get_log('browser'):
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except Exception:
        pass


@pytest.fixture(scope='session')
def drv():
    global _DRIVER
    _DRIVER = _driver()
    try:
        _login(_DRIVER)
    except Exception:
        pass
    yield _DRIVER
    try:
        _drain_console(_DRIVER)
        _DRIVER.quit()
    except Exception:
        pass


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when == 'call' and rep.failed and _DRIVER is not None:
        _save_evidence(item.name, _DRIVER)


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 15).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.2)
    _drain_console(drv)


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _login(drv, username='demo_admin'):
    _goto(drv, '/login')
    drv.execute_script('try { window.localStorage.clear() } catch (e) {}')
    _goto(drv, '/login')
    drv.find_element(By.ID, 'username').send_keys(username)
    drv.find_element(By.ID, 'password').send_keys('mock-pass-001')
    drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()
    WebDriverWait(drv, 15).until(lambda d: '/login' not in d.current_url)
    time.sleep(1.0)


def _wait_text(drv, text, timeout=15):
    WebDriverWait(drv, timeout).until(lambda d: text in _body_text(drv))


def _clear_global_algorithm(drv):
    drv.execute_script(
        'localStorage.setItem("iatp:algorithm:v1", JSON.stringify({state:{algorithmId:""},version:0}))')
    time.sleep(0.4)


def _dialog_count(drv):
    return len(drv.find_elements(By.CSS_SELECTOR, '[role="dialog"]'))


def _find_button(drv, label):
    return drv.find_element(By.XPATH, f"//button[contains(., '{label}')]")


# ---------------------------------------------------------------------------
# 复测用例
# ---------------------------------------------------------------------------

def test_report_center_generate_dialog_opens(drv):
    """P1：报告中心「生成报告」点击 → [role=dialog] 出现（此前 SectionPageLayout 丢弃子组件不渲染）。"""
    _clear_global_algorithm(drv)
    _goto(drv, '/report-center')
    _wait_text(drv, '报告中心')
    assert _dialog_count(drv) == 0, '进入页面即有 Dialog（不应）'
    _find_button(drv, '生成报告').click()
    WebDriverWait(drv, 8).until(lambda d: _dialog_count(d) >= 1)
    body = _body_text(drv)
    assert '生成报告' in body
    # 关闭
    drv.execute_script('document.querySelector("[role=dialog]").__close && __close()')
    close_btns = drv.find_elements(By.CSS_SELECTOR, '[role="dialog"] [data-slot="dialog-close"]')
    if close_btns:
        drv.execute_script('arguments[0].click()', close_btns[0])
    WebDriverWait(drv, 8).until(lambda d: _dialog_count(d) == 0)


def test_report_center_export_dialog_opens(drv):
    """P1：更多操作 → 导出 CSV → 导出 Dialog（含导出进度/导出历史页签）出现。"""
    _clear_global_algorithm(drv)
    _goto(drv, '/report-center')
    _wait_text(drv, '报告中心')
    drv.find_element(By.CSS_SELECTOR, 'button[aria-label="更多操作"]').click()
    WebDriverWait(drv, 8).until(
        lambda d: d.find_elements(By.CSS_SELECTOR, '[role="menuitem"]'))
    item = drv.find_element(By.XPATH, "//*[@role='menuitem'][contains(., '导出 CSV')]")
    item.click()
    WebDriverWait(drv, 8).until(lambda d: _dialog_count(d) >= 1)
    body = _body_text(drv)
    assert '导出' in body
    assert _dialog_count(drv) >= 1


def test_favorite_badge_count_updates(drv):
    """P2：行内收藏切换 → 「仅看收藏」角标计数随 summary-counts 失效重拉更新。"""
    _clear_global_algorithm(drv)
    _goto(drv, '/report-center')
    _wait_text(drv, '报告中心')

    # 精确读取「仅看收藏」Switch 所在 label 内计数徽标（避免命中全页其它数字）
    def fav_badge_value():
        sw = drv.find_elements(By.CSS_SELECTOR, '[aria-label="仅看收藏"]')
        if not sw:
            return None
        label = sw[0].find_element(By.XPATH, '..')
        for s in label.find_elements(By.CSS_SELECTOR, 'span'):
            if s.text.strip().isdigit():
                return int(s.text.strip())
        return None

    before = fav_badge_value()
    assert before is not None, '未找到「仅看收藏」角标'

    # 打开第一行行操作菜单 → 点收藏/取消收藏
    row_trigger = drv.find_element(By.CSS_SELECTOR, 'button[aria-label^="报告操作："]')
    drv.execute_script(
        'arguments[0].scrollIntoView({block:"center", inline:"nearest"});'
        'arguments[0].click()', row_trigger)
    WebDriverWait(drv, 8).until(
        lambda d: [i for i in d.find_elements(By.CSS_SELECTOR, '[role="menuitem"]')
                   if i.text.strip() in ('收藏', '取消收藏') and i.is_displayed()])
    items = drv.find_elements(By.CSS_SELECTOR, '[role="menuitem"]')
    fav_item = next(
        (i for i in items if i.text.strip() in ('收藏', '取消收藏')), None)
    assert fav_item is not None, '行操作菜单无收藏项'
    drv.execute_script('arguments[0].click()', fav_item)
    time.sleep(2.5)  # 等待 invalidate + refetch

    after = fav_badge_value()
    assert after is not None
    assert after != before, f'收藏角标未更新（before={before} after={after}）'


def test_no_severe_console_errors(drv):
    """全走查后无 console SEVERE。"""
    _drain_console(drv)
    severe = [m for m in _CONSOLE_SEVERE if 'favicon' not in m.lower()]
    assert not severe, f'console SEVERE: {severe[:5]}'
