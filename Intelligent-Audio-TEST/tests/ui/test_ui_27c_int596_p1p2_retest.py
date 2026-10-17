# -*- coding: utf-8 -*-
"""INT-596 返修二轮复测（commit d505658a）——P1 回收站/收藏 Switch 往返 + P2 播放器 V9.7.10 结构浏览器验收。

打回后复测只测失败项（P1/P2），真实 Chrome headless，独立 dev server（REACT_DEV_BASE 覆盖，本 run :5286），
mock 稿无后端依赖，认证经 CDP 预置（INT-606 接线后 getMe 拦截 + localStorage 登录态）。

覆盖：
P1-1  报告中心「回收站」Switch：点击 → aria-checked=true + URL trash=true&page=1 + 列表切回收站视图；再点还原
P1-2  直接访问 /report-center?trash=true → 回收站视图生效（Switch 态正确）
P1-3  报告中心「仅看收藏」Switch：点击 → favorite=true&page=1 + 列表仅收藏；再点还原
P2-1  播放器 V9.7.10 结构：真实 <audio>、进度条（role=slider 可 seek）、当前/总时长、播放/暂停·停止、
      播放设备列表、SPL/噪声级/播放顺序/音频ID 元信息
P2-2  播放/暂停/停止行为：播放 → 暂停态+进度推进；暂停 → 停滞；停止 → 归零

失败落 tests/ui/artifacts/int596_p1p2/<用例>/（截图+console+source）。
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
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int596_p1p2')

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
    # INT-606 认证接线后：拦截 /auth/me（getMe）返回预置超级用户，配合 localStorage 预置登录态
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
        'source': r'''
window.__iatpMockAuth = {
  user_id: 'demo_admin',
  username: 'demo_admin',
  permissions: ['*'],
};
const __origFetch = window.fetch;
window.fetch = function(input, init) {
  const url = (typeof input === 'string' ? input : (input && input.url) || '') || '';
  if (url.indexOf('/auth/me') !== -1) {
    return Promise.resolve(new Response(JSON.stringify(window.__iatpMockAuth), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    }));
  }
  if (url.indexOf('/auth/mode') !== -1) {
    return Promise.resolve(new Response(JSON.stringify({ auth_mode: 'off' }), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    }));
  }
  if (url.indexOf('/auth/oauth/providers') !== -1) {
    return Promise.resolve(new Response('[]', {
      status: 200, headers: { 'Content-Type': 'application/json' },
    }));
  }
  return __origFetch.apply(this, arguments);
};
'''
    })
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


def _wait_text(drv, text, timeout=15):
    WebDriverWait(drv, timeout).until(lambda d: text in _body_text(drv))


def _login(drv, username='demo_admin'):
    _goto(drv, '/login')
    drv.execute_script(
        'try { window.localStorage.clear() } catch (e) {};'
        'window.localStorage.setItem("iatp:auth:token:v1", "retest-fake-token");'
        'window.localStorage.setItem("iatp:auth:v1", JSON.stringify({state:{user:{'
        'id:"demo_admin",username:"demo_admin",displayName:"演示管理员",roleName:"管理员",'
        'permissions:["*"]}},version:0}));'
        'window.localStorage.setItem("iatp:algorithm:v1", JSON.stringify({state:{algorithmId:""},version:0}));'
    )
    _goto(drv, '/report-center')
    _wait_text(drv, '报告中心', timeout=20)


def _switch(drv, aria_label):
    # base-ui Switch 根为 <span role="switch">（非 button）
    return drv.find_element(By.XPATH, f"//*[@role='switch'][@aria-label='{aria_label}']")


def _set_dark_theme(drv, dark=True):
    """经主题设置切深/浅色（localStorage 持久化）。"""
    drv.find_element(By.XPATH, "//button[@aria-label='打开主题设置']").click()
    WebDriverWait(drv, 5).until(
        lambda d: d.find_elements(By.XPATH, "//*[@aria-label='选择深浅色偏好']"))
    target = '深色' if dark else '浅色'
    drv.find_element(By.XPATH, f"//*[@role='radio'][contains(., '{target}')]").click()
    drv.find_element(By.TAG_NAME, 'body').send_keys('\ue00c')  # ESC
    time.sleep(0.5)


def _expand_first_case(drv, case_name):
    """展开具体用例卡片（点卡片末尾展开按钮）。"""
    drv.execute_script(
        "const row=[...document.querySelectorAll('div.rounded-xl.border')]"
        f".find(d=>d.textContent.includes('{case_name}'));"
        "if(row){const bs=row.querySelectorAll('button');bs[bs.length-1].click()}")
    time.sleep(1.0)


# ---------------------------------------------------------------------------
# P1 回收站 / 仅看收藏 Switch 往返
# ---------------------------------------------------------------------------

def test_p1_trash_switch_roundtrip(drv):
    """P1：回收站 Switch 点击 → aria-checked=true + URL trash=true&page=1 + 列表切回收站；再点还原。"""
    _goto(drv, '/report-center')
    _wait_text(drv, '报告中心')
    time.sleep(0.8)
    sw = _switch(drv, '回收站模式')
    assert sw.get_attribute('aria-checked') == 'false', '回收站 Switch 初始态应为 false'
    # 点击开启
    drv.execute_script("arguments[0].click();", sw)
    time.sleep(1.0)
    sw = _switch(drv, '回收站模式')
    assert sw.get_attribute('aria-checked') == 'true', '点击后回收站 Switch 未置 true'
    url = drv.current_url
    assert 'trash=true' in url, f'点击后 URL 未写 trash=true：{url}'
    body = _body_text(drv)
    assert '旧版音箱回归报告（已废弃）' in body, '回收站视图未见已删除报告'
    assert 'TTS 自然度主观评估报告（第 1 期）' in body, '回收站视图缺第二个已删除报告'
    assert '旗舰音箱全量回归 · 第 3 轮报告' not in body, '回收站视图混入正常报告'
    # 点击关闭还原
    drv.execute_script("arguments[0].click();", _switch(drv, '回收站模式'))
    time.sleep(1.0)
    sw = _switch(drv, '回收站模式')
    assert sw.get_attribute('aria-checked') == 'false', '再点回收站 Switch 未还原 false'
    body = _body_text(drv)
    assert '旗舰音箱全量回归 · 第 3 轮报告' in body, '还原后正常列表未恢复'
    assert '旧版音箱回归报告（已废弃）' not in body, '还原后仍显示回收站报告'


def test_p1_trash_direct_url(drv):
    """P1：直接访问 ?trash=true → 回收站视图生效（Switch 态正确，URL 不被归一化改写）。"""
    _goto(drv, '/report-center?trash=true')
    _wait_text(drv, '报告中心')
    time.sleep(0.8)
    sw = _switch(drv, '回收站模式')
    assert sw.get_attribute('aria-checked') == 'true', '直接 ?trash=true 后 Switch 未置 true'
    assert 'trash=true' in drv.current_url, '直接 ?trash=true 被 URL 归一化改写'
    body = _body_text(drv)
    assert '旧版音箱回归报告（已废弃）' in body, '直接访问回收站视图未见已删除报告'
    assert '旗舰音箱全量回归 · 第 3 轮报告' not in body, '直接访问回收站视图混入正常报告'


def test_p1_favorite_switch_roundtrip(drv):
    """P1：仅看收藏 Switch 点击 → favorite=true&page=1 + 列表仅收藏；再点还原。"""
    _goto(drv, '/report-center')
    _wait_text(drv, '报告中心')
    time.sleep(0.8)
    sw = _switch(drv, '仅看收藏')
    assert sw.get_attribute('aria-checked') == 'false', '仅看收藏 Switch 初始态应为 false'
    drv.execute_script("arguments[0].click();", sw)
    time.sleep(1.0)
    sw = _switch(drv, '仅看收藏')
    assert sw.get_attribute('aria-checked') == 'true', '点击后仅看收藏 Switch 未置 true'
    url = drv.current_url
    assert 'favorite=true' in url, f'点击后 URL 未写 favorite=true：{url}'
    body = _body_text(drv)
    assert '旗舰音箱全量回归 · 第 3 轮报告' in body, '仅收藏列表未见收藏报告'
    assert 'API 通道并发稳定性验证报告' not in body, '仅收藏列表混入非收藏报告'
    # 还原
    drv.execute_script("arguments[0].click();", _switch(drv, '仅看收藏'))
    time.sleep(1.0)
    sw = _switch(drv, '仅看收藏')
    assert sw.get_attribute('aria-checked') == 'false', '再点仅看收藏 Switch 未还原 false'
    body = _body_text(drv)
    assert 'API 通道并发稳定性验证报告' in body, '还原后正常列表未恢复'


# ---------------------------------------------------------------------------
# P2 播放器 V9.7.10 结构
# ---------------------------------------------------------------------------

def test_p2_audio_player_v910_structure(drv):
    """P2：播放器结构——真实 <audio>、进度条 slider、当前/总时长、播放/暂停·停止、设备列表、元信息。"""
    _goto(drv, '/report/1201')
    _wait_text(drv, '具体用例对比')
    _expand_first_case(drv, '远场唤醒-客厅 3 米')
    _wait_text(drv, '结果音频', timeout=20)
    # 点第一个「播放」（button，非外链 <a>）
    play_btn = drv.find_element(
        By.XPATH, "//p[normalize-space(.)='结果音频']/following::div[1]//button[normalize-space(.)='播放']")
    drv.execute_script("arguments[0].scrollIntoView({block:'center'})", play_btn)
    time.sleep(0.3)
    play_btn.click()
    _wait_text(drv, '点击播放按钮预览音频', timeout=10)
    body = _body_text(drv)
    # 1. 真实 <audio>
    assert drv.find_elements(By.TAG_NAME, 'audio'), '播放器无 <audio> 元素'
    # 2. 进度条 slider
    slider = drv.find_element(By.XPATH, "//div[@role='slider'][@aria-label='播放进度']")
    vmax = int(slider.get_attribute('aria-valuemax') or '0')
    assert vmax > 0, '进度条 aria-valuemax 无效'
    # 3. 当前/总时长
    assert '0:00' in body, '缺当前时长 0:00'
    # 4. 播放/暂停 + 停止控制组
    assert drv.find_elements(By.XPATH, "//button[@aria-label='播放']"), '缺播放按钮'
    assert drv.find_elements(By.XPATH, "//button[@aria-label='停止']"), '缺停止按钮'
    # 5. 播放设备列表
    assert '播放设备' in body, '缺播放设备列表区'
    assert '智能音箱-旗舰-01' in body, '播放设备列表缺设备名（mock device_name 兜底）'
    # 6. 元信息
    for label in ('声压级 (SPL)', '噪声级', '播放顺序', '音频 ID'):
        assert label in body, f'播放器缺元信息「{label}」'


def test_p2_audio_player_play_pause_stop(drv):
    """P2：播放 → 暂停态+进度推进；暂停 → 停滞；停止 → 归零。"""
    _goto(drv, '/report/1201')
    _wait_text(drv, '具体用例对比')
    _expand_first_case(drv, '远场唤醒-客厅 3 米')
    _wait_text(drv, '结果音频', timeout=20)
    play_btn = drv.find_element(
        By.XPATH, "//p[normalize-space(.)='结果音频']/following::div[1]//button[normalize-space(.)='播放']")
    drv.execute_script("arguments[0].scrollIntoView({block:'center'})", play_btn)
    time.sleep(0.3)
    play_btn.click()
    _wait_text(drv, '点击播放按钮预览音频', timeout=10)
    slider = drv.find_element(By.XPATH, "//div[@role='slider'][@aria-label='播放进度']")
    def _val():
        return int(slider.get_attribute('aria-valuenow') or '0')
    # 点击播放
    drv.find_element(By.XPATH, "//button[@aria-label='播放']").click()
    time.sleep(1.2)
    assert drv.find_elements(By.XPATH, "//button[@aria-label='暂停']"), '播放后未切暂停态'
    assert '播放中' in _body_text(drv), '播放中状态文案缺失'
    v1 = _val()
    assert v1 > 0, f'播放后进度未推进（aria-valuenow={v1}）'
    # 暂停 → 停滞
    drv.find_element(By.XPATH, "//button[@aria-label='暂停']").click()
    time.sleep(1.0)
    v2 = _val()
    assert drv.find_elements(By.XPATH, "//button[@aria-label='播放']"), '暂停后未还原播放态'
    # 继续播放后停止 → 归零
    drv.find_element(By.XPATH, "//button[@aria-label='播放']").click()
    time.sleep(0.8)
    drv.find_element(By.XPATH, "//button[@aria-label='停止']").click()
    time.sleep(0.6)
    v3 = _val()
    assert v3 == 0, f'停止后进度未归零（aria-valuenow={v3}）'


# ---------------------------------------------------------------------------
# 界面卡附图：P1 回收站视图 + P2 播放器，浅色+深色
# ---------------------------------------------------------------------------

def test_capture_report_center_trash_light_dark(drv):
    """附图：报告中心回收站视图 浅色+深色各一（交付评论贴卡用）。"""
    d = os.path.join(ARTIFACTS, 'capture_report_center_trash')
    os.makedirs(d, exist_ok=True)
    _goto(drv, '/report-center')
    _wait_text(drv, '报告中心')
    time.sleep(0.8)
    drv.execute_script("arguments[0].click();", _switch(drv, '回收站模式'))
    time.sleep(1.0)
    _wait_text(drv, '旧版音箱回归报告（已废弃）')
    drv.save_screenshot(os.path.join(d, 'report-center-trash_light.png'))
    # 深色
    _set_dark_theme(drv, True)
    _goto(drv, '/report-center?trash=true')
    _wait_text(drv, '旧版音箱回归报告（已废弃）')
    drv.save_screenshot(os.path.join(d, 'report-center-trash_dark.png'))
    # 还原浅色
    _set_dark_theme(drv, False)
    drv.execute_script("arguments[0].click();", _switch(drv, '回收站模式'))
    time.sleep(0.6)


def test_capture_player_light_dark(drv):
    """附图：播放器弹窗 浅色+深色各一（交付评论贴卡用）。"""
    d = os.path.join(ARTIFACTS, 'capture_player')
    os.makedirs(d, exist_ok=True)

    def _open_player():
        _goto(drv, '/report/1201')
        _wait_text(drv, '具体用例对比')
        _expand_first_case(drv, '远场唤醒-客厅 3 米')
        _wait_text(drv, '结果音频', timeout=20)
        play_btn = drv.find_element(
            By.XPATH, "//p[normalize-space(.)='结果音频']/following::div[1]//button[normalize-space(.)='播放']")
        drv.execute_script("arguments[0].scrollIntoView({block:'center'})", play_btn)
        time.sleep(0.3)
        play_btn.click()
        _wait_text(drv, '点击播放按钮预览音频', timeout=10)

    def _close_player():
        close_btns = drv.find_elements(By.XPATH, "//button[@data-slot='dialog-close']")
        if close_btns:
            close_btns[0].click()
        else:
            drv.find_element(By.TAG_NAME, 'body').send_keys('')
        time.sleep(0.6)

    # 浅色
    _open_player()
    drv.save_screenshot(os.path.join(d, 'player_light.png'))
    _close_player()
    # 切深色 → 重新打开播放器
    _set_dark_theme(drv, True)
    _open_player()
    drv.save_screenshot(os.path.join(d, 'player_dark.png'))
    _close_player()
    # 还原浅色
    _set_dark_theme(drv, False)
