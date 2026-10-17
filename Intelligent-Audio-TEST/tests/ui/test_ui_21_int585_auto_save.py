# -*- coding: utf-8 -*-
"""INT-585 算法编辑 Sheet「30s 自动保存提醒」浏览器走查（真实 Chrome headless，按 test_ui_13 先例）。

针对 frontend-react/ mock 稿（无后端依赖，直接驱动 dev server，默认 5273）：
1. 倒计时出现与重置：编辑变脏 → footer「将在 30 秒后自动保存」；等待递减；再次编辑 → 重置 30
2. 归零自动保存：30s 到 0 → toast「已自动保存」+ Sheet 不关 + 倒计时消失；关闭不再弹脏态守卫
3. 校验不过暂停：清空必填 → Alert「有校验未通过，请修正后再自动保存」+ 倒计时消失；修正后重现
4. 手动保存优先：编辑后立即「保存」→ toast「算法已保存」+ Sheet 关闭（30s 内手动赢，无自动保存）
5. 深浅色两主题下倒计时/Alert 可读

失败落 tests/ui/artifacts/int585_auto_save/<用例>/（截图+console+source）。
"""
import json
import os
import re
import time

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int585_auto_save')

# 5273 = 本工作区常驻 dev server；env 可覆写（INT-473 隔离副本为 5274）
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
    """把浏览器 console 累积的 SEVERE 条目归入会话级列表（get_log 只返回上次调用后的增量）。"""
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
    # 会话级登录（demo_admin 权限 '*'），单跑任意用例也能通过路由守卫
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


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_makereport(item, call):
    if call.when == 'call' and call.excinfo is not None and _DRIVER is not None:
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


def _wait_rows(drv, n):
    WebDriverWait(drv, 12).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')) == n)


def _wait_rows_retry(drv, n):
    """等待列表行数；8s 未达到则刷新页面重试一次（dev server HMR 重编译期间防抖）。"""
    try:
        _wait_rows(drv, n)
        return
    except Exception:
        drv.refresh()
        time.sleep(1.5)
        _wait_rows(drv, n)


def _open_row_menu(drv, name):
    btn = drv.find_element(By.XPATH, f"//button[@aria-label='算法 {name} 的操作']")
    btn.click()
    WebDriverWait(drv, 5).until(
        lambda d: d.find_elements(By.XPATH, "//*[@role='menuitem']"))


def _click_menu_item(drv, label):
    items = drv.find_elements(By.XPATH, "//*[@role='menuitem']")
    for it in items:
        if label in it.text:
            it.click()
            return
    raise AssertionError(f'行菜单项「{label}」未找到')


def _open_edit_sheet(drv, row_name='通用识别引擎'):
    """行菜单 → 编辑，等 Sheet 出现（§6.1）。"""
    _goto(drv, '/AlgorithmConfig')
    _wait_rows_retry(drv, 7)
    _open_row_menu(drv, row_name)
    _click_menu_item(drv, '编辑')
    WebDriverWait(drv, 8).until(lambda d: '编辑算法' in _body_text(drv))
    time.sleep(0.6)


def _edit_name(drv, new_name):
    """用原生 value setter + input 事件改写显示名称（Selenium clear/send_keys 不触发 React onChange）。"""
    el = drv.find_element(By.XPATH, "//input[@id='algo-name']")
    drv.execute_script(
        "const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;"
        "s.call(arguments[0], arguments[1]);"
        "arguments[0].dispatchEvent(new Event('input', { bubbles: true }));",
        el, new_name)
    time.sleep(0.6)


def _countdown_number(drv):
    """从 body 文本提取「将在 {n} 秒后自动保存」的 n；无倒计时返回 None。"""
    m = re.search(r'将在 (\d+) 秒后自动保存', _body_text(drv))
    return int(m.group(1)) if m else None


def _press_esc(drv):
    webdriver.ActionChains(drv).send_keys(Keys.ESCAPE).perform()
    time.sleep(0.6)


def _close_sheet(drv):
    """ESC 关闭 Sheet；若脏态守卫 ConfirmDialog（§6.1）弹出则点「离开并丢弃」确认离开。"""
    _press_esc(drv)
    try:
        WebDriverWait(drv, 3).until(
            lambda d: d.find_elements(
                By.XPATH, "//*[@role='alertdialog'][contains(., '有未保存的更改')]"))
        drv.find_element(
            By.XPATH, "//*[@role='alertdialog']//button[contains(., '离开并丢弃')]").click()
    except Exception:
        pass
    WebDriverWait(drv, 5).until(lambda d: '编辑算法' not in _body_text(drv))


def _js_click(drv, xpath):
    """滚动到视野后用 JS 原生 click（绕开抽屉动画/遮罩导致的 ElementClickIntercepted）。"""
    el = drv.find_element(By.XPATH, xpath)
    drv.execute_script(
        "arguments[0].scrollIntoView({ block: 'center' }); arguments[0].click();", el)
    time.sleep(0.6)


# ── 1. 倒计时出现与重置 ──
def test_01_countdown_appears_and_resets(drv):
    _open_edit_sheet(drv)
    # 编辑态预填合法 → 未变脏，不应有倒计时
    assert _countdown_number(drv) is None, '编辑态未编辑不应显示自动保存倒计时'

    _edit_name(drv, '通用识别引擎 自动保存走查')
    n = _countdown_number(drv)
    assert n == 30, f'变脏后应显示「将在 30 秒后自动保存」，实际 {n}'

    # 等待递减
    time.sleep(5)
    n2 = _countdown_number(drv)
    assert n2 is not None and n2 < n, f'倒计时应递减：{n} → {n2}'

    # 再次编辑 → 重置回 30
    _edit_name(drv, '通用识别引擎 自动保存走查二')
    n3 = _countdown_number(drv)
    assert n3 == 30, f'再次编辑应重置回 30s，实际 {n3}'
    _close_sheet(drv)


# ── 2. 归零自动保存：toast「已自动保存」+ Sheet 不关 + 快照重置 ──
def test_02_zero_out_auto_save(drv):
    _open_edit_sheet(drv)
    _edit_name(drv, '归零自动保存走查')
    assert _countdown_number(drv) == 30, '编辑后应显示倒计时 30s'

    # 30s 归零 → 自动保存聚合提交（mock 120ms）→ toast「已自动保存」
    WebDriverWait(drv, 35).until(lambda d: '已自动保存' in _body_text(drv))
    # Sheet 不关（仍在编辑算法），倒计时消失（快照重置 isDirty 归零）
    assert '编辑算法' in _body_text(drv), '自动保存成功后 Sheet 不应关闭'
    assert _countdown_number(drv) is None, '自动保存成功后倒计时应消失'

    # 快照重置：此刻关闭不再弹「有未保存的更改」脏态守卫（§6.1a 最重要口径修正）
    _press_esc(drv)
    WebDriverWait(drv, 5).until(lambda d: '编辑算法' not in _body_text(drv))
    txt = _body_text(drv)
    assert '有未保存的更改' not in txt, '自动保存成功后关闭不应弹脏态守卫'


# ── 3. 校验不过暂停 + Alert；修正后重新计时 ──
def test_03_validation_blocked_pause(drv):
    _open_edit_sheet(drv)
    _edit_name(drv, '校验暂停走查')
    assert _countdown_number(drv) == 30

    # 清空必填「显示名称」→ 校验不过 → Alert 出现、倒计时消失
    _edit_name(drv, '')
    WebDriverWait(drv, 5).until(
        lambda d: '有校验未通过，请修正后再自动保存' in _body_text(drv))
    assert _countdown_number(drv) is None, '校验不过时倒计时应暂停消失'

    # 修正 → Alert 消失、倒计时重新 30s
    _edit_name(drv, '校验暂停走查-修正')
    WebDriverWait(drv, 5).until(
        lambda d: '有校验未通过，请修正后再自动保存' not in _body_text(drv))
    n = _countdown_number(drv)
    assert n == 30, f'修正后应重新计时 30s，实际 {n}'
    _close_sheet(drv)


# ── 4. 手动保存优先：30s 内手动保存赢，Sheet 关闭 ──
def test_04_manual_save_priority(drv):
    _open_edit_sheet(drv)
    _edit_name(drv, '手动保存优先走查')
    assert _countdown_number(drv) == 30

    # 立即手动「保存」→ toast「算法已保存」+ Sheet 关闭（30s 内手动赢）
    drv.find_element(By.XPATH, "//button[normalize-space()='保存']").click()
    WebDriverWait(drv, 10).until(lambda d: '算法已保存' in _body_text(drv))
    WebDriverWait(drv, 5).until(lambda d: '编辑算法' not in _body_text(drv))
    txt = _body_text(drv)
    assert '已自动保存' not in txt, '手动保存优先：30s 内不应触发自动保存'


# ── 5. 深浅色两主题下倒计时可读 ──
def test_05_light_dark_theme_readable(drv):
    # 浅色（默认）：打开编辑 Sheet → 倒计时 + 校验不过 Alert 可读
    _open_edit_sheet(drv)
    _edit_name(drv, '深浅色走查-浅色')
    assert _countdown_number(drv) == 30, '浅色主题下倒计时应可读'
    _edit_name(drv, '')
    WebDriverWait(drv, 5).until(
        lambda d: '有校验未通过，请修正后再自动保存' in _body_text(drv))
    _close_sheet(drv)

    # 切深色（主题经 localStorage 持久化，后续 _goto 整页刷新仍生效）
    drv.find_element(By.XPATH, "//button[@aria-label='打开主题设置']").click()
    WebDriverWait(drv, 5).until(
        lambda d: d.find_elements(By.XPATH, "//*[@aria-label='选择深浅色偏好']"))
    _js_click(drv, "//*[@role='radio'][contains(., '深色')]")
    _press_esc(drv)
    time.sleep(0.5)

    # 深色：打开编辑 Sheet → 倒计时 + Alert 可读
    _open_edit_sheet(drv)
    _edit_name(drv, '深浅色走查-深色')
    assert _countdown_number(drv) == 30, '深色主题下倒计时应可读'
    _edit_name(drv, '')
    WebDriverWait(drv, 5).until(
        lambda d: '有校验未通过，请修正后再自动保存' in _body_text(drv))
    _close_sheet(drv)

    # 切回浅色还原
    drv.find_element(By.XPATH, "//button[@aria-label='打开主题设置']").click()
    WebDriverWait(drv, 5).until(
        lambda d: d.find_elements(By.XPATH, "//*[@aria-label='选择深浅色偏好']"))
    _js_click(drv, "//*[@role='radio'][contains(., '浅色')]")
    _press_esc(drv)
    time.sleep(0.5)


# ── 6. 全会话无 JS 严重错误 ──
def test_06_no_severe_console_errors(drv):
    _goto(drv, '/AlgorithmConfig')
    _wait_rows_retry(drv, 7)
    time.sleep(1.0)
    _drain_console(drv)
    assert not _CONSOLE_SEVERE, \
        '浏览器控制台存在 SEVERE 错误：\n' + '\n'.join(_CONSOLE_SEVERE)
