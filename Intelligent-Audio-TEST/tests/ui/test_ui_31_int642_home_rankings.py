# -*- coding: utf-8 -*-
"""INT-642 首页门户 + benchmark 排行 infra mock→api 浏览器验收（真实 Chrome headless）。

针对 frontend-react/（接线 INT-642 版本，dev server 5388，rsbuild proxy /api → localhost:5000）：
1. 首页门户 /：真实 GET /api/v1/home/stats/details 请求（Network 证据）+ 规模条渲染后端
   真实数字（与 curl 同一接口比对，非 mock 常量 128/342）；接入测试对象分区渲染。
2. benchmark 排行 /rankings：公开路由直达（无权限硬守卫，数据 403 空态不跳登录）；
   真实 GET /api/v1/benchmarks/ranking 数据渲染（真实主体名称与后端比对）；
   「语音识别」页签 → category=asr 透传后端过滤 → 空态「暂无排行数据」；
   回「语音对话」→ category=voice_llm → 数据恢复（证明筛选参数已透传后端过滤）。
3. 深浅色截图 + 关键交互态（类别页签切换后空态）截图。
4. 无 mock 残留：Network 中首页/排行接口均为 /api/v1 真实端点，且渲染数字 ≠ mock 常量。

前置：dev server 5388（接线后代码）已在跑；:5000 后端由 5000 段 run_all.py 栈提供
（复用/只读探测，不停止）。页面登录态：AUTH_MODE=off → dev_user（permissions=["*"]）。
"""
import json
import os
import time
from urllib.request import urlopen

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5388')
BACKEND = os.environ.get('REACT_BACKEND', 'http://localhost:5000')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ARTIFACTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'ui', 'artifacts', 'int642_home_rankings')

_DRIVER = None


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
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
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


@pytest.fixture(scope='module')
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
    rep = outcome.get_result()
    if rep.when == 'call' and rep.failed and _DRIVER is not None:
        d = os.path.join(ARTIFACTS, item.name)
        os.makedirs(d, exist_ok=True)
        try:
            _DRIVER.save_screenshot(os.path.join(d, 'screenshot.png'))
            with open(os.path.join(d, 'page_source.html'), 'w', encoding='utf-8') as f:
                f.write(_DRIVER.page_source)
        except Exception:
            pass


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _wait_text(drv, text, timeout=20):
    WebDriverWait(drv, timeout).until(lambda d: text in _body_text(drv))


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 15).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)


def _resource_urls(drv):
    """已加载资源 URL 清单（fetch/XHR 一并计入）——Network 证据。"""
    return drv.execute_script(
        'return performance.getEntriesByType("resource").map(e => e.name)')


def _wait_resource_url(drv, fragment, timeout=10):
    """轮询资源清单直到出现包含 fragment 的请求（SPA fetch 完成后才入 performance buffer）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if any(fragment in u for u in _resource_urls(drv)):
            return True
        time.sleep(0.5)
    return False


def _backend_json(path):
    with urlopen(BACKEND + path, timeout=15) as r:
        return json.loads(r.read().decode('utf-8'))


def _shot(drv, name):
    os.makedirs(ARTIFACTS, exist_ok=True)
    drv.save_screenshot(os.path.join(ARTIFACTS, name))


def _set_theme(drv, dark):
    drv.execute_script(
        f'document.documentElement.classList'
        f'.{"add" if dark else "remove"}("dark")')


# ---------------------------------------------------------------------------
# 用例
# ---------------------------------------------------------------------------

def test_home_portal_real_stats_and_sections(drv):
    """首页门户 /：真实 /home/stats/details 请求 + 规模条渲染后端真实数字 + 分区渲染。

    AUTH_MODE=off → app 挂载即 ensureAuthSession 注入 dev_user（home:read 放行），
    门户公开路由直接走查。渲染数字与后端同一接口响应比对，非 mock 常量（128/342）。
    """
    _goto(drv, '/')
    _wait_text(drv, '接入测试对象')
    # 等登录态规模条（STATS_BAR.label=「平台规模」）出现——AUTH_MODE=off 下
    # ensureAuthSession 注入 dev_user 后 useHomeStats 才发 /home/stats/details 请求；
    # 「测试用例」字样在 Hero 区也有，不能作为规模条已渲染的判据。
    _wait_text(drv, '平台规模')

    # 后端同一接口的真实数字（比对基准）
    details = _backend_json('/api/v1/home/stats/details')['data']
    assert details['test_cases']['total'] > 0, (
        f'后端 /home/stats/details test_cases.total 为 0，无法作为真实数据比对基准')
    expected_total = details['test_cases']['total']
    expected_groups = details['test_cases']['groups']

    # 渲染文本包含后端数字（规模条「580」/「9 个分组」等）
    body = _body_text(drv)
    assert str(expected_total) in body, (
        f'规模条未渲染后端 test_cases.total={expected_total}（mock 残留 128？）')
    assert f'{expected_groups} 个分组' in body, (
        f'规模条未渲染后端 groups={expected_groups} 个分组')

    # Network 证据：真实端点请求确实发出（/api/v1 前缀，非 mock）
    assert _wait_resource_url(drv, '/api/v1/home/stats/details'), (
        f'未捕获 /home/stats/details 真实请求；资源清单：{_resource_urls(drv)}')
    # 无 mock 常量 128/342 残留
    assert '128' not in body.split('测试用例')[1][:20], '规模条疑似渲染 mock 常量 128'

    _shot(drv, 'home_light.png')

    # 深色
    _set_theme(drv, True)
    drv.get(BASE + '/')
    _wait_text(drv, '平台规模')
    _wait_text(drv, f'{expected_groups} 个分组')
    _shot(drv, 'home_dark.png')
    _set_theme(drv, False)


def test_rankings_public_route_real_data_and_category_filter(drv):
    """benchmark 排行 /rankings：公开路由真实数据渲染 + 类别页签筛选透传后端。"""
    _goto(drv, '/rankings')
    _wait_text(drv, '排行榜')

    # 后端同一接口的真实排行数据（比对基准）
    ranking = _backend_json('/api/v1/benchmarks/ranking')['data']
    subjects = {item['subject_name'] for item in ranking['items']}
    assert ranking['items'], '后端 /benchmarks/ranking 当前无数据，无法比对'
    assert 'INT95R7-voice-llm-adapter' in subjects, (
        f'后端排行数据缺预期主体，实际主体：{sorted(subjects)}')

    # 页面渲染真实主体名（真实 API 数据，非 mock 假名）
    _wait_text(drv, 'INT95R7-voice-llm-adapter')
    body = _body_text(drv)
    # mock 阶段的假主体名不应出现
    for mock_name in ('远场语音评测模型-旗舰版', '灵犀语音引擎 V3', 'DeepL API'):
        assert mock_name not in body, f'排行页出现 mock 主体名：{mock_name}'

    # Network 证据：真实端点请求
    assert _wait_resource_url(drv, '/api/v1/benchmarks/ranking'), (
        f'未捕获 /benchmarks/ranking 真实请求；资源清单：{_resource_urls(drv)}')

    _shot(drv, 'rankings_light.png')

    # 「语音识别」页签 → category=asr 透传后端 → 空态
    drv.find_element(By.XPATH, "//button[contains(., '语音识别')]").click()
    WebDriverWait(drv, 15).until(lambda d: 'category=asr' in d.current_url)
    _wait_text(drv, '暂无排行数据')
    # Network 证据：asr 过滤请求已发出（真实接口 + query 参数）
    assert _wait_resource_url(drv, '/api/v1/benchmarks/ranking?category=asr'), (
        f'未捕获 category=asr 透传请求；资源清单：{_resource_urls(drv)}')
    _shot(drv, 'rankings_asr_empty.png')

    # 回「语音对话」→ category=voice_llm → 数据恢复
    drv.find_element(By.XPATH, "//button[contains(., '语音对话')]").click()
    WebDriverWait(drv, 15).until(lambda d: 'category=voice_llm' in d.current_url)
    _wait_text(drv, 'INT95R7-voice-llm-adapter')
    assert '暂无排行数据' not in _body_text(drv), '回 voice_llm 后仍为空态'

    _shot(drv, 'rankings_voice_llm_restored.png')

    # 深色
    _set_theme(drv, True)
    drv.get(BASE + '/rankings?category=voice_llm')
    time.sleep(1.5)
    _wait_text(drv, '排行榜')
    _wait_text(drv, 'INT95R7-voice-llm-adapter')
    _shot(drv, 'rankings_dark.png')
    _set_theme(drv, False)


def test_rankings_anonymous_no_login_redirect(drv):
    """公开路由匿名直达：清 localStorage 后 /rankings 仍可达，不跳登录。"""
    drv.execute_script('try { window.localStorage.clear() } catch (e) {}')
    _goto(drv, '/rankings')
    _wait_text(drv, '排行榜')
    assert '/login' not in drv.current_url, (
        f'匿名访问 /rankings 被重定向到登录：{drv.current_url}')
