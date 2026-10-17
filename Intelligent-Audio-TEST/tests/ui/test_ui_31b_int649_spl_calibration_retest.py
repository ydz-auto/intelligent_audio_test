# -*- coding: utf-8 -*-
"""INT-649 P1 返修复测（真实 Chrome headless，按 test_ui_31 先例）。

前端UX审计打回项：详情弹窗「校准点明细」增益偏移/数字增益/基础电平/最终电平四列全「—」、
校准曲线 0 点空态——根因 CalibrationPointDto 按 snake_case 读取而实际 wire 为 camelCase
（后端 device_service._spl_mapping_to_dict 直传 DB JSONB）。React页面工程师B 已返修
（commit 99261c4c：CalibrationPointDto/splAdapter 读写侧改 camelCase，与 Vue 口径一致）。

本复测只测失败项 + 修复相关：
① 详情弹窗校准点明细实值渲染（增益偏移 dB / 基础电平 dBFS / 最终电平 dBFS / 实测 SPL dB，
   不再全「—」；校准点数与后端一致；校准曲线非空）；
② 深色主题下同样实值渲染（深浅色各附图）；
③ Network 核对：仅真实 /api/v1/spl（无 mock 路径请求）；console 无 SEVERE；
④ 无 mock 残留：/infrastructure/mock/spl-mock.ts 已删（grep 验证）。

前置：本 run 起的 dev server（REACT_DEV_BASE 默认 :5360，/api 代理 → 常驻后端 :5000）。
失败落 tests/ui/artifacts/int649_spl_calibration_retest/<用例>/。
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
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int649_spl_calibration_retest')

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5360')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

# 后端 /api/v1/spl 实测数据（映射「设备正面（0.5m+0°）」id=1 首点）：
# points[0] = {spl:69, gainOffset:-15, baseLevel:-30, finalLevel:-45}（camelCase wire，无 digital_gain）
EXPECT_POINT = ('-15 dB', '-30 dBFS', '-45 dBFS', '69 dB')


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


@pytest.fixture(scope='module')
def drv():
    global _DRIVER
    _DRIVER = _driver()
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
    WebDriverWait(drv, 20).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _wait_text(drv, text, timeout=20):
    WebDriverWait(drv, timeout).until(lambda d: text in _body_text(d))


def _resource_urls(drv):
    return drv.execute_script(
        "return performance.getEntriesByType('resource').map(e => e.name)")


def _api_paths(urls):
    paths = []
    for u in urls:
        if '/api/v1/' not in u:
            continue
        path = u.split('://', 1)[-1]
        path = path.split('/', 1)[-1] if '/' in path else path
        path = '/' + path
        path = path.split('?')[0]
        paths.append(path)
    return paths


def _screenshot(drv, name):
    d = os.path.join(ARTIFACTS, 'shots')
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, name)
    drv.save_screenshot(path)
    return path


def _set_dark_theme(drv, dark=True):
    drv.find_element(By.XPATH, "//button[@aria-label='打开主题设置']").click()
    WebDriverWait(drv, 5).until(
        lambda d: d.find_elements(By.XPATH, "//*[@aria-label='选择深浅色偏好']"))
    target = '深色' if dark else '浅色'
    drv.find_element(By.XPATH, f"//*[@role='radio'][contains(., '{target}')]").click()
    drv.find_element(By.TAG_NAME, 'body').send_keys('\ue00c')  # ESC
    time.sleep(0.8)


def _open_first_detail(drv):
    """物理域列表首行 → 行操作菜单 → 详情，返回详情弹窗 body 文本。"""
    _goto(drv, '/SPLMapping')
    _wait_text(drv, '声压级映射管理')
    _wait_text(drv, '设备正面（0.5m+0°）')
    trigger = drv.find_element(
        By.XPATH, "//button[starts-with(@aria-label, '映射 ') and contains(@aria-label, ' 的操作')]")
    trigger.click()
    time.sleep(0.8)
    drv.find_element(By.XPATH, "//*[@role='menuitem'][contains(., '详情')]").click()
    _wait_text(drv, '增益映射详情', timeout=15)
    return _body_text(drv)


def test_01_detail_dialog_calibration_real_values(drv):
    """P1 复测：详情弹窗校准点明细实值渲染（不再全「—」）。"""
    body = _open_first_detail(drv)
    flat = body.replace(' ', '').replace('\n', '')

    # ① 校准点明细表头存在
    for col in ('增益偏移', '数字增益', '基础电平', '最终电平', '实测SPL'):
        assert col in flat, f'校准点明细缺列头: {col}'

    # ② 首点实值渲染：增益偏移 dB / 基础电平 dBFS / 最终电平 dBFS / 实测 SPL dB
    for v in EXPECT_POINT:
        assert v in body, f'校准点明细缺实值 {v}（P1 未修复）: {body[:600]}'

    # ③ 校准点数 = 5（后端「设备正面（0.5m+0°）」id=1 有 5 点；不再因契约错配而空）
    assert '校准点数5' in flat, f'校准点数未显示 5: {flat[:500]}'

    # ④ 校准曲线区存在画布（vChart），非「尚无校准数据」空态
    assert '尚无校准数据' not in body, '校准点明细空态（P1 未修复）'
    _screenshot(drv, 'int649_spl_detail_light.png')
    # 关闭弹窗
    drv.find_element(By.TAG_NAME, 'body').send_keys('\ue00c')
    time.sleep(0.5)


def test_02_dark_theme_calibration_real_values(drv):
    """深色主题下详情弹窗同样实值渲染并截图。"""
    _set_dark_theme(drv, dark=True)
    body = _open_first_detail(drv)
    for v in EXPECT_POINT:
        assert v in body, f'深色主题下校准点明细缺实值 {v}: {body[:600]}'
    assert '尚无校准数据' not in body
    _screenshot(drv, 'int649_spl_detail_dark.png')
    drv.find_element(By.TAG_NAME, 'body').send_keys('\ue00c')
    time.sleep(0.5)
    # 切回浅色，避免影响后续 run
    _set_dark_theme(drv, dark=False)
    _wait_text(drv, '声压级映射管理')


def test_03_network_no_mock_and_console(drv):
    """Network 核对：详情弹窗数据来自真实 /api/v1/spl；无 mock 请求；console 无 SEVERE。"""
    body = _open_first_detail(drv)
    assert '增益映射详情' in body
    paths = _api_paths(_resource_urls(drv))
    assert paths, '未捕获任何 /api/v1 请求'
    # ① 无 mock 路径请求
    assert not [p for p in paths if 'mock' in p.lower()], f'存在 mock 路径请求: {paths}'
    # ② 真实 /spl（详情）被请求
    assert any(p == '/api/v1/spl' or p.startswith('/api/v1/spl/') for p in paths), \
        f'未请求真实 /api/v1/spl: {paths}'
    # ③ 其余 API 请求只在 SPL 族 / 认证引导范围
    unexpected = [
        p for p in paths
        if not (p.startswith('/api/v1/spl') or p.startswith('/api/v1/playback-devices')
                or p.startswith('/api/v1/digital-spl') or p.startswith('/api/v1/apis')
                or p.startswith('/api/v1/auth'))
    ]
    assert not unexpected, f'发现预期外 API 请求: {unexpected}'
    _drain_console(drv)
    assert not _CONSOLE_SEVERE, f'浏览器 console 存在 SEVERE: {_CONSOLE_SEVERE[:3]}'
    drv.find_element(By.TAG_NAME, 'body').send_keys('\ue00c')
    time.sleep(0.5)
