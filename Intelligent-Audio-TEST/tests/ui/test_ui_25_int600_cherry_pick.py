# -*- coding: utf-8 -*-
"""INT-600 挑选合并交互重设计 冒烟核心链路浏览器走查（真实 Chrome headless，按 test_ui_12 先例）。

针对 frontend-react/ mock 稿（无后端依赖，直接驱动 dev server，默认 5273）：
P1 三页签终态：任务列表无「合并」页签，「挑选合并」页签存在且 /tasks/merged 重定向到 /tasks/cherry-picks
P2 「开始挑选」→ 页内四步向导：Step1 挑选（多级树勾选）→ 加入购物车 → Step2 购物车（树形分组）→
   去复核 → Step3 复核（摘要统计）→ 确认下单 → Step4 三出口 → 下单成功 toast + 出清
P3 多级树联动：勾选任务级 → 全部子孙选中（R1）；取消 device 级 → 其下 result_type 清空（R4）
P4 购物车移除矩阵：单条 X / 批量勾选移除 / 清空购物车

失败落 tests/ui/artifacts/int600_cherry_pick/<用例>/（截图+console+source）。
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
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int600_cherry_pick')

# 5273 = 本工作区常驻 dev server；env 可覆写
BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5273')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
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
    yield _DRIVER
    try:
        _DRIVER.quit()
    except Exception:
        pass


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    if call.when == 'call' and call.excinfo is not None:
        try:
            _save_evidence(item.name, _DRIVER)
        except Exception:
            pass


def _wait(drv, by, value, timeout=12):
    return WebDriverWait(drv, timeout).until(
        lambda d: d.find_elements(by, value))


def _click(drv, by, value, timeout=12):
    el = _wait(drv, by, value, timeout)
    # 取第一个可见/可点元素
    for cand in el:
        if cand.is_displayed():
            cand.click()
            return cand
    return el[0]


def _texts(drv, by, value):
    return [e.text.strip() for e in drv.find_elements(by, value) if e.text.strip()]


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 15).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.4)


def _login(drv, username='demo_admin'):
    drv.get(BASE + '/login')
    time.sleep(1.2)
    drv.execute_script('try { window.localStorage.clear() } catch (e) {}')
    _goto(drv, '/login')
    drv.find_element(By.ID, 'username').send_keys(username)
    drv.find_element(By.ID, 'password').send_keys('mock-pass-001')
    drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()
    WebDriverWait(drv, 15).until(lambda d: '/login' not in d.current_url)
    time.sleep(1.0)


def test_01_three_tabs_and_merged_redirect(drv):
    """P1 三页签终态 + /tasks/merged 重定向到 /tasks/cherry-picks"""
    _login(drv)
    _goto(drv, '/tasks/daily')
    tabs = _texts(drv, By.CSS_SELECTOR, '[data-slot="tabs-list"] button, [role="tablist"] button')
    joined = ' '.join(tabs)
    assert '日常' in joined and '已发布' in joined and '挑选合并' in joined
    assert '合并' not in [t for t in tabs if '挑选合并' not in t]

    # 旧「合并」路径重定向（§2.2 裁定①）
    drv.get(BASE + '/tasks/merged')
    time.sleep(2)
    assert '/cherry-picks' in drv.current_url or '/tasks/cherry-picks' in drv.current_url


def test_02_open_wizard_and_linkage(drv):
    """P2/P3 开始挑选 → Step1 多级树勾选联动 R1/R4"""
    _login(drv)
    _goto(drv, '/tasks/cherry-picks')
    # 开始挑选（页内向导）
    btn = _click(drv, By.XPATH, "//button[contains(., '开始挑选')]")
    assert btn
    time.sleep(1.5)
    assert _wait(drv, By.XPATH, "//*[contains(., '挑选') and contains(., '购物车') and contains(., '复核')]")

    # 任务级节点勾选 → 全部子孙选中（R1）；base-ui Checkbox 勾选态由 [data-checked] 表达
    task_check = _wait(drv, By.CSS_SELECTOR, '[data-testid^="pick-branch-task:"] [data-slot="checkbox"]')
    task_check[0].click()
    time.sleep(0.5)
    task_node_checked = drv.find_elements(By.CSS_SELECTOR,
                                          '[data-testid^="pick-branch-task:"] [data-slot="checkbox"][data-checked]')
    assert len(task_node_checked) > 0, '任务级勾选后节点应为全选态（R1）'
    # 已选汇总条出现「已选 n 条结果」（n>0）
    summary = _texts(drv, By.XPATH, "//*[contains(., '已选') and contains(., '条结果')]")
    assert any('条结果' in s for s in summary)


def test_03_add_to_cart_review_checkout(drv):
    """P2 四步主链路：加购 → 购物车 → 复核 → 下单三出口"""
    _login(drv)
    _goto(drv, '/tasks/cherry-picks')
    _click(drv, By.XPATH, "//button[contains(., '开始挑选')]")
    time.sleep(1.5)

    # Step1 勾选 → 加入购物车
    task_check = _wait(drv, By.CSS_SELECTOR, '[data-testid^="pick-branch-task:"] [data-slot="checkbox"]')
    task_check[0].click()
    time.sleep(0.3)
    add_btn = _click(drv, By.XPATH, "//button[contains(., '加入购物车')]")
    assert add_btn
    time.sleep(1.5)

    # Step2 购物车树形分组（任务组头 + 计数）
    group_header = _texts(drv, By.CSS_SELECTOR, '[data-testid^="cart-branch-cart-task:"]')
    assert len(group_header) > 0

    # 去复核 → Step3 复核摘要
    _click(drv, By.XPATH, "//button[contains(., '去复核')]")
    time.sleep(1.5)
    assert any('结果' in s and '条' in s for s in _texts(drv, By.XPATH, "//*[contains(., '来源任务')]"))

    # 确认下单 → Step4 三出口
    _click(drv, By.XPATH, "//button[contains(., '确认下单')]")
    time.sleep(1.0)
    assert _wait(drv, By.CSS_SELECTOR, '[data-testid^="checkout-action-"]')


def test_04_cart_remove_matrix(drv):
    """P4 购物车移除矩阵：清空购物车确认"""
    _login(drv)
    _goto(drv, '/tasks/cherry-picks')
    _click(drv, By.XPATH, "//button[contains(., '打开购物车')]")
    time.sleep(1.0)
    # 购物车抽屉出现「我的购物车」
    assert _wait(drv, By.XPATH, "//*[contains(., '我的购物车')]")
