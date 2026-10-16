# -*- coding: utf-8 -*-
"""INT-512 文档页可视稿 浏览器走查（真实 Chrome headless，按 test_ui_14 先例）。

针对 frontend-react/ mock 稿（无后端依赖，直接驱动 dev server，默认 5273）：
1. /user-guide 使用手册：公共路由无守卫直达；H1+guide-prose；手册切换两条
   （当前 aria-current=page）；目录 10 条锚点可达；标题锚点 id 生成；表格滚动包裹
   （role=region 可聚焦）；代码块（text）复制按钮「复制代码」；移动端目录折叠触发器
2. /user-guide-api API 手册：H1；shiki 懒加载高亮（bash/json/powershell → .shiki span
   带 --shiki-light/--shiki-dark）；{{API_BASE_URL}} 占位符展开为站点根 + /api/v1、
   正文无字面占位符；复制按钮文案
3. 深浅主题：shiki 双主题 CSS 变量存在（github-light/github-dark）

失败落 tests/ui/artifacts/int512_user_guide/<用例>/（截图+console+source）。
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
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int512_user_guide')

# 5273 = 本工作区常驻 dev server；env 可覆写
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
    drv.set_page_load_timeout(60)
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
    _drain_console(drv)


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _toc_links(drv):
    return drv.find_elements(By.CSS_SELECTOR, 'aside nav[aria-label="目录"] a')


# ── 1. 使用手册：公共直达 + 骨架 + 目录锚点 ───
def test_01_user_guide_public_layout(drv):
    _goto(drv, '/user-guide')
    txt = _body_text(drv)
    assert '平台使用手册' in txt, f'H1 缺失：{txt[:120]}'
    assert 'guide-prose' in drv.page_source, 'guide-prose 阅读排版未应用'
    # 公共路由无守卫直达：站头应出现「登录」而非工作台侧栏
    assert '登录' in txt, '公开站头「登录」缺失'
    # 手册切换两条 + 当前 aria-current=page
    switch = drv.find_elements(By.CSS_SELECTOR, 'aside nav[aria-label="用户手册"] a')
    assert len(switch) == 2, f'手册切换条数={len(switch)}'
    texts = [a.text for a in switch]
    assert any('使用手册' in t for t in texts), f'切换项缺失：{texts}'
    assert any('API 手册' in t for t in texts), f'切换项缺失：{texts}'
    assert switch[0].get_attribute('aria-current') == 'page', \
        '当前手册未标 aria-current=page'


def test_02_user_guide_toc_anchors(drv):
    _goto(drv, '/user-guide')
    links = _toc_links(drv)
    assert len(links) == 10, f'目录条数={len(links)}'
    # 锚点全部可达：点第 2 条 → 对应标题出现且带生成 id
    target = links[1]
    title = target.text.strip()
    target.click()
    time.sleep(0.8)
    h = drv.find_elements(By.XPATH,
                          f"//div[contains(@class,'guide-prose')]//h2[normalize-space()='{title}']")
    assert h, f'目录点击后目标标题「{title}」不可达'
    assert h[0].get_attribute('id') == title, \
        f'标题锚点 id 未生成：{h[0].get_attribute("id")}'


def test_03_user_guide_tables_and_code(drv):
    _goto(drv, '/user-guide')
    # 表格滚动包裹（role=region + tabIndex=0 可聚焦，07_文档.md §1.2）
    regions = drv.find_elements(By.CSS_SELECTOR, '.markdown-table-scroll')
    assert len(regions) >= 2, f'表格滚动包裹数={len(regions)}'
    assert all(r.get_attribute('role') == 'region' for r in regions), \
        '表格滚动区缺 role=region'
    # 联系支持 text 代码块：复制按钮「复制代码」
    buttons = drv.find_elements(By.CSS_SELECTOR, '.guide-code-block button')
    assert buttons, '代码块复制按钮缺失'
    assert '复制代码' in buttons[0].text, f'复制按钮文案：{buttons[0].text}'


def test_04_user_guide_mobile_toc(drv):
    _goto(drv, '/user-guide')
    # 桌面目录常开；移动端折叠触发器存在且可开合
    triggers = drv.find_elements(By.CSS_SELECTOR,
                                 'aside [data-slot="collapsible-trigger"]')
    assert len(triggers) == 1, '移动端目录折叠触发器缺失'
    d = drv.get_window_size()
    drv.set_window_size(700, 900)
    time.sleep(0.8)
    # 折叠触发器可见 → 点击展开 → 目录条目显示
    triggers[0].click()
    time.sleep(0.8)
    links = _toc_links(drv)
    assert len(links) == 10, f'移动端展开后目录条数={len(links)}'
    drv.set_window_size(d['width'], d['height'])
    time.sleep(0.5)


def test_05_user_guide_scroll_spy_and_theme(drv):
    _goto(drv, '/user-guide')
    # 滚动追踪：触底强制高亮最后一节（07_文档.md §1.3-5）
    drv.execute_script('window.scrollTo(0, document.body.scrollHeight)')
    time.sleep(1.5)
    active = drv.find_elements(
        By.CSS_SELECTOR, 'aside nav[aria-label="目录"] a[aria-current="location"]')
    assert len(active) == 1, f'触底激活目录条数={len(active)}'
    # 深浅主题：html.dark 可切换，shiki 双主题 CSS 变量在 token 上
    has_light_var = drv.execute_script(
        "return !!document.querySelector('code.shiki span') ? "
        "getComputedStyle(document.querySelector('code.shiki span')).getPropertyValue('--shiki-light') "
        "!== '' : true")
    assert has_light_var, '代码块缺 --shiki-light 变量（github-light 主题）'
    drv.execute_script("document.documentElement.classList.add('dark')")
    time.sleep(0.5)
    has_dark_var = drv.execute_script(
        "return !!document.querySelector('code.shiki span') ? "
        "getComputedStyle(document.querySelector('code.shiki span')).getPropertyValue('--shiki-dark') "
        "!== '' : true")
    assert has_dark_var, '代码块缺 --shiki-dark 变量（github-dark 主题）'


# ── 2. API 手册：shiki 高亮 + 占位符展开 ───
def test_06_api_guide_render(drv):
    _goto(drv, '/user-guide-api')
    txt = _body_text(drv)
    assert '平台 API 手册' in txt, f'H1 缺失：{txt[:120]}'
    # 手册切换跨路由：当前高亮 API 手册
    switch = drv.find_elements(By.CSS_SELECTOR, 'aside nav[aria-label="用户手册"] a')
    assert switch[1].get_attribute('aria-current') == 'page', \
        'API 手册当前项未高亮'


def test_07_api_guide_shiki_highlight(drv):
    _goto(drv, '/user-guide-api')
    # shiki 懒加载后：bash/json/powershell 全部高亮（.shiki span 带 --shiki 变量）
    WebDriverWait(drv, 15).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR,
                                      'code.shiki span[style*="--shiki"]')) > 0)
    blocks = drv.find_elements(By.CSS_SELECTOR, '.guide-code-block pre')
    assert len(blocks) >= 12, f'代码块数={len(blocks)}'
    langs = {b.get_attribute('aria-label') for b in blocks}
    assert {'bash', 'json', 'powershell'} <= langs, f'语言缺失：{langs}'
    tokens = drv.find_elements(By.CSS_SELECTOR, 'code.shiki span[style*="--shiki"]')
    assert len(tokens) > 100, f'高亮 token 数={len(tokens)}'


def test_08_api_guide_placeholders(drv):
    _goto(drv, '/user-guide-api')
    page = drv.page_source
    assert '{{API_BASE_URL}}' not in page, '占位符 {{API_BASE_URL}} 未替换'
    assert '/api/v1/auth/login' in page, '{{API_BASE_URL}} 未展开为站点根 + /api/v1'
    assert '/api/v1/tasks' in page, '任务接口端点缺失'


def test_09_api_guide_switch_back(drv):
    _goto(drv, '/user-guide-api')
    switch = drv.find_elements(By.CSS_SELECTOR, 'aside nav[aria-label="用户手册"] a')
    switch[0].click()  # 使用手册
    WebDriverWait(drv, 10).until(lambda d: 'user-guide-api' not in d.current_url)
    time.sleep(1.0)
    txt = _body_text(drv)
    assert '平台使用手册' in txt, f'跨路由切换后使用手册缺失：{txt[:120]}'


def test_10_no_console_severe(drv):
    _goto(drv, '/user-guide')
    _goto(drv, '/user-guide-api')
    assert not _CONSOLE_SEVERE, f'浏览器控制台 SEVERE 错误：{_CONSOLE_SEVERE[:3]}'
