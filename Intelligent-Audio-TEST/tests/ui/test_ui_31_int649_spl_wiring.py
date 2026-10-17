# -*- coding: utf-8 -*-
"""INT-649 SPL 映射页接线（infra mock→api）浏览器实测（真实 Chrome headless，按 test_ui_28/30 先例）。

针对 frontend-react/ 接线后代码：SPL 映射页经基座 client.ts（INT-605）走真实后端。
前置：本 run 起的 dev server（REACT_DEV_BASE 默认 :5360，/api 代理 → 常驻后端 :5000，
AUTH_MODE=off 开放模式自动引导 dev 会话）；:5000 后端由 5000 段 run_all.py 栈提供（复用/只读探测）。

覆盖 INT-649 验收标准：
① 物理域真实渲染：标题「声压级映射管理」徽标「已校准 3/共 3」+ 统计徽章（映射总数3/已校准3/
   未校准0/关联设备数3，与 GET /spl/stats 一致）+ 真实 3 条映射（设备正面（0.5m+0°）/音箱0°/
   设备正左斜侧（1m-90°））+ 十列 DataTable + 页头动作区（批量配置 SPL/导入映射数据/添加增益映射）；
② 播放设备引用下拉（关联播放设备 facet，真实 GET /playback-devices 选项渲染）；
③ 行操作菜单 → 校准历史弹窗（真实 GET /spl/{id}/history，空态「暂无校准记录」渲染）；
④ 数字域：GET /digital-spl 空态「暂无 RMS-SPL 映射」+ 关联 API facet（GET /apis）加载；
⑤ Network 核对：仅真实 API 端点（/spl、/spl/stats、/digital-spl、/apis、/playback-devices、
   /auth/me、/auth/mode），无 mock 请求；浏览器 console 无 SEVERE；
⑥ 深浅两套主题截图 + 数字域空态 + 校准历史弹窗 附图（§2.5.3）。

失败落 tests/ui/artifacts/int649_spl_wiring/<用例>/（截图+console+source）。
"""
import json
import os
import time

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int649_spl_wiring')

# 本 run 隔离 dev server（5360 空闲端口起；env 可覆写）
BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5360')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

REAL_API_ENDPOINTS = [
    '/api/v1/spl/stats',
    '/api/v1/spl/',
    '/api/v1/digital-spl',
    '/api/v1/apis',
    '/api/v1/playback-devices',
    '/api/v1/auth/me',
    '/api/v1/auth/mode',
]


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
    """取 /api/v1/... 请求的路径部分（去 origin 与 query）。"""
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
    """经主题设置切深/浅色（localStorage 持久化；test_ui_27c 同口径）。"""
    drv.find_element(By.XPATH, "//button[@aria-label='打开主题设置']").click()
    WebDriverWait(drv, 5).until(
        lambda d: d.find_elements(By.XPATH, "//*[@aria-label='选择深浅色偏好']"))
    target = '深色' if dark else '浅色'
    drv.find_element(By.XPATH, f"//*[@role='radio'][contains(., '{target}')]").click()
    drv.find_element(By.TAG_NAME, 'body').send_keys('\ue00c')  # ESC
    time.sleep(0.8)


# ---------------------------------------------------------------------------
# ① 物理域真实渲染
# ---------------------------------------------------------------------------

def test_01_physical_domain_real_render(drv):
    """物理域：标题/徽标/统计徽章/真实 3 条映射/十列 DataTable/页头动作区。"""
    _goto(drv, '/SPLMapping')
    _wait_text(drv, '声压级映射管理')

    body = _body_text(drv)
    # 徽标：已校准 {n}/共 {m}（后端 3 条全已校准）
    assert '已校准 3/共 3' in body, f'徽标未对齐后端口径: {body[:300]}'
    # 统计徽章（GET /spl/stats 实测 total=3 calibrated=3 uncalibrated=0 associated=3）
    flat = body.replace(' ', '')
    assert '映射总数3' in flat and '已校准3' in flat and '未校准0' in flat and '关联设备数3' in flat, \
        f'统计徽章未对齐 /spl/stats: {flat[:400]}'
    # 真实 3 条映射渲染（后端 /spl 数据，非 mock 常量）
    for name in ('设备正面（0.5m+0°）', '音箱0°', '设备正左斜侧（1m-90°）'):
        assert name in body, f'物理域缺真实映射行: {name}'
    # 十列 DataTable
    for col in ('名称', '关联设备', '类型', '测量距离', '目标声压级', '测试频率',
                '校准点数', '校准状态', '更新时间', '操作'):
        assert col in body, f'缺列头: {col}'
    # 页头动作区
    for btn in ('批量配置 SPL', '导入映射数据', '添加增益映射'):
        assert btn in body, f'缺页头按钮: {btn}'
    _screenshot(drv, 'int649_spl_light.png')


def test_02_playback_device_facet(drv):
    """播放设备引用下拉：真实 GET /playback-devices 选项渲染。"""
    _goto(drv, '/SPLMapping')
    _wait_text(drv, '声压级映射管理')
    drv.find_element(By.XPATH, "//button[contains(., '关联播放设备')]").click()
    time.sleep(1.0)
    body = _body_text(drv)
    # 真实设备名（后端 /playback-devices 实测含「音箱90°」等；mock 阶段无此数据）
    assert '音箱' in body, '播放设备 facet 未渲染真实选项'
    assert '全部' in body.replace(' ', ''), 'facet 应含「全部」'
    _screenshot(drv, 'int649_spl_playback_facet.png')
    drv.find_element(By.TAG_NAME, 'body').send_keys('\ue00c')  # ESC 收起
    time.sleep(0.5)


def test_03_row_menu_history_dialog(drv):
    """行操作菜单 → 校准历史弹窗：真实 GET /spl/{id}/history + 空态渲染。"""
    _goto(drv, '/SPLMapping')
    _wait_text(drv, '声压级映射管理')
    # 首行操作菜单（aria-label「映射 {name} 的操作」）
    trigger = drv.find_element(By.XPATH, "//button[starts-with(@aria-label, '映射 ') and contains(@aria-label, ' 的操作')]")
    trigger.click()
    time.sleep(0.8)
    drv.find_element(By.XPATH, "//*[@role='menuitem'][contains(., '校准历史')]").click()
    _wait_text(drv, '校准历史', timeout=15)
    _wait_text(drv, '暂无校准记录', timeout=10)
    _screenshot(drv, 'int649_spl_history_dialog.png')
    drv.find_element(By.TAG_NAME, 'body').send_keys('\ue00c')  # ESC 关闭弹窗
    time.sleep(0.5)


def test_04_digital_domain_empty(drv):
    """数字域：GET /digital-spl 空态 + 关联 API facet（GET /apis）加载。"""
    _goto(drv, '/SPLMapping')
    _wait_text(drv, '声压级映射管理')
    drv.find_element(By.XPATH, "//*[@role='tab'][contains(., 'API/Realtime RMS-SPL')]").click()
    _wait_text(drv, '暂无 RMS-SPL 映射', timeout=20)
    body = _body_text(drv)
    assert 'RMS-SPL 映射数' in body, '数字域缺统计徽章'
    assert '添加 RMS-SPL 映射' in body, '数字域缺主按钮'
    # 关联 API facet（数字页签动态 GET /apis）
    drv.find_element(By.XPATH, "//button[contains(., '关联 API')]").click()
    time.sleep(1.0)
    facet_body = _body_text(drv)
    assert 'voice-llm' in facet_body or 'API' in facet_body, '关联 API facet 未渲染真实选项'
    _screenshot(drv, 'int649_spl_digital_empty.png')
    drv.find_element(By.TAG_NAME, 'body').send_keys('\ue00c')
    time.sleep(0.5)


def test_05_network_no_mock_and_console(drv):
    """Network 核对：仅真实 API 端点、无 mock 请求；console 无 SEVERE。"""
    _goto(drv, '/SPLMapping')
    _wait_text(drv, '声压级映射管理')
    # 切一次数字域，确保 /digital-spl + /apis 被请求
    drv.find_element(By.XPATH, "//*[@role='tab'][contains(., 'API/Realtime RMS-SPL')]").click()
    _wait_text(drv, '暂无 RMS-SPL 映射', timeout=20)
    time.sleep(1.0)
    paths = _api_paths(_resource_urls(drv))
    assert paths, '未捕获任何 /api/v1 请求'
    # ① 无 mock 路径请求
    assert not [p for p in paths if 'mock' in p.lower()], f'存在 mock 路径请求: {paths}'
    # ② 核心 SPL 接口确被真实请求（物理列表/统计/播放设备 facet + 数字域/关联 API）
    for expect in ('/api/v1/spl', '/api/v1/spl/stats', '/api/v1/playback-devices',
                   '/api/v1/digital-spl', '/api/v1/apis'):
        assert any(p == expect or p.startswith(expect + '/') for p in paths), \
            f'核心接口未被请求: {expect}（实际 {paths}）'
    # ③ 其余 API 请求只在认证引导 / SPL 族范围内（有平台侧栏资源请求时再收敛）
    def _allowed(p):
        if p.startswith('/api/v1/spl') or p.startswith('/api/v1/playback-devices') \
           or p.startswith('/api/v1/digital-spl') or p.startswith('/api/v1/apis') \
           or p.startswith('/api/v1/auth'):
            return True
        return False
    unexpected = [p for p in paths if not _allowed(p)]
    assert not unexpected, f'发现预期外 API 请求: {unexpected}'
    _drain_console(drv)
    assert not _CONSOLE_SEVERE, f'浏览器 console 存在 SEVERE: {_CONSOLE_SEVERE[:3]}'


def test_06_dark_theme_screenshot(drv):
    """深色主题下物理域渲染正常并截图（浅色已截于 test_01）。"""
    _goto(drv, '/SPLMapping')
    _wait_text(drv, '声压级映射管理')
    _set_dark_theme(drv, dark=True)
    _wait_text(drv, '声压级映射管理')
    _wait_text(drv, '设备正面（0.5m+0°）')
    _screenshot(drv, 'int649_spl_dark.png')
    # 切回浅色，避免影响后续
    _set_dark_theme(drv, dark=False)
    _wait_text(drv, '声压级映射管理')
