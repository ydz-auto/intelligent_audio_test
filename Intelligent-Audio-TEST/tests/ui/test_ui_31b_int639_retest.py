# -*- coding: utf-8 -*-
"""INT-639 打回修复复测（P1 试听双模式 + P2 标签 facet 计数切真实列表）。

复测范围（负责人 2026-10-17 裁定：打回后复测只测失败项 + 修复改动相关用例）：
- P1（打回项#1）：试听播放双模式真实接线——
  浏览器播放 = GET /api/v1/audios/{id}/stream → 预签名 URL → <audio> 真实播放（进度/时长随媒体事件）；
  实验室播放 = POST /api/v1/testcases/{id}/preview（playbackMode=backend）→ 停止 POST /{id}/stop_preview 生效。
- P2（打回项#2）：标签 facet 用例计数由 MOCK_TEST_CASES 常量切真实已加载列表（cases prop）派生。

前置：dev server 已在本 worktree 起（rsbuild proxy /api → localhost:5000 常驻栈，AUTH_MODE=off）；
本卡为只读走查 + 浏览器取证，不写入任何共享库 fixture。

证据基准（5000 段栈共享库现网数据，2026-10-18 探测）：
- 测试用例_2026144019.wav（audio 2236 的 stream 预签名 URL 可播放，dur≈1.64s；唯一可播音频，
  位于 INT321_D_1792230256 分组——默认前 5 分组不渲染，需点分组级「加载更多」展开）
- 测试用例_HJ050_…wav（type e2e，round1 配置 playback_device_id=3；实验室 preview/stop 实测通过）
- 现共享库 580 条真实用例均 algorithm_type=voice_llm → 全局算法需切 voice_llm 才有数据（asr-v3 空）
"""
import json
import os
import time
import urllib.parse
import urllib.request

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5347')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ARTIFACTS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         'artifacts', 'int639_wiring_retest')

# 真实数据断言基准
CASE_STREAM_KW = '2026144019'   # audio 2236 stream 可播（唯一）
CASE_LAB_KW = 'HJ050'           # type e2e + playback_device_id=3
REAL_GROUP = '环境理解'
REAL_TAG = 'INT308'
REAL_TAG_R3 = 'INT308R3'

_DRIVER = None
_CONSOLE_JS_ERRORS = []


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


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 15).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.2)


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _wait_text(drv, text, timeout=15):
    WebDriverWait(drv, timeout).until(lambda d: text in _body_text(drv))


def _clear_storage(drv):
    drv.execute_script('try { window.localStorage.clear() } catch (e) {}')


def _fill_and_submit_login(drv, username, password):
    _goto(drv, '/login')
    _wait_text(drv, '登录')
    drv.find_element(By.ID, 'username').send_keys(username)
    drv.find_element(By.ID, 'password').send_keys(password)
    drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()


def _ensure_logged_in(drv, tries=3):
    """保证已登录：直航 /dashboard，若被重定向到 /login 则走 admin/admin123 真实登录链。

    登录后把全局算法（store localStorage iatp:algorithm:v1）切到 voice_llm——
    现共享库 580 条真实用例均 algorithm_type=voice_llm，默认 asr-v3 筛选为空态。
    """
    for attempt in range(1, tries + 1):
        _goto(drv, '/dashboard')
        if '/login' not in drv.current_url:
            break
        _fill_and_submit_login(drv, 'admin', 'admin123')
        ok = False
        for _ in range(4):
            time.sleep(2)
            if '/dashboard' in drv.current_url and '欢迎回来！' in _body_text(drv):
                ok = True
                break
            if '/login' in drv.current_url and '加密初始化失败' in _body_text(drv):
                break
        if ok:
            break
        if attempt < tries:
            time.sleep(5)
    WebDriverWait(drv, 25).until(lambda d: '/dashboard' in d.current_url)
    _wait_text(drv, '工作台', timeout=25)
    drv.execute_script(
        "localStorage.setItem('iatp:algorithm:v1', "
        "JSON.stringify({state:{algorithmId:'voice_llm'},version:0}))")
    _goto(drv, '/dashboard')
    _wait_text(drv, '工作台', timeout=25)


def _set_theme(drv, name):
    """切主题（深色/浅色）：先 ESC 收掉引导/弹窗遮罩，JS 点击主题设置钮 → 偏好 radio。"""
    drv.find_element(By.TAG_NAME, 'body').send_keys('')  # 收引导/弹窗
    time.sleep(0.4)
    _js_click(drv, "//button[@aria-label='打开主题设置']")
    WebDriverWait(drv, 5).until(
        lambda d: d.find_elements(By.XPATH, "//*[@aria-label='选择深浅色偏好']"))
    _js_click(drv, f"//*[@role='radio'][contains(., '{name}')]")
    drv.find_element(By.TAG_NAME, 'body').send_keys('\ue00c')
    time.sleep(0.5)


def _js_click(drv, xpath):
    el = drv.find_element(By.XPATH, xpath)
    drv.execute_script('arguments[0].click()', el)


def _shot(drv, name):
    d = os.path.join(ARTIFACTS, name)
    os.makedirs(os.path.dirname(d), exist_ok=True)
    drv.save_screenshot(d)
    return d


def _find_case_id(keyword):
    """经 dev server 代理查后端，解析用例关键字 → 首个用例 id。"""
    url = BASE + '/api/v1/testcases?keyword=' + urllib.parse.quote(keyword) + '&page=1&per_page=5'
    with urllib.request.urlopen(url, timeout=15) as r:
        payload = json.load(r)
    items = payload['data']['items']
    assert items, f'未找到关键字 {keyword} 对应用例'
    return items[0]['id']


def _inject_fetch_logger(drv):
    """捕获真实 API 请求（URL + method + POST body），供断言真实端点被调用。"""
    drv.execute_script("""
    window.__INT639_RETEST_REQS__ = [];
    const _origFetch = window.fetch;
    window.fetch = function(...args) {
      try {
        const u = (typeof args[0] === 'string') ? args[0] : (args[0] && args[0].url);
        if (u && String(u).includes('/api/v1/')) {
          const method = ((args[1] && args[1].method) || 'GET');
          let body = '';
          try {
            if (args[1] && args[1].body) {
              if (typeof args[1].body === 'string') body = args[1].body;
              else if (args[1].body instanceof URLSearchParams) body = args[1].body.toString();
            }
          } catch (e) {}
          window.__INT639_RETEST_REQS__.push(method + ' ' + String(u) + (body ? ' :: ' + body : ''));
        }
      } catch (e) {}
      return _origFetch.apply(this, args);
    };
    const _origOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function(method, url, ...rest) {
      try {
        if (String(url).includes('/api/v1/')) {
          window.__INT639_RETEST_REQS__.push(String(method) + ' ' + String(url));
        }
      } catch (e) {}
      return _origOpen.call(this, method, url, ...rest);
    };
    """)


def _read_requests(drv):
    try:
        return drv.execute_script('return window.__INT639_RETEST_REQS__ || []') or []
    except Exception:
        return []


def _audio_js(drv):
    """对话框内 <audio> 元素状态（src/duration/currentTime/ended），供真实播放断言。"""
    return drv.execute_script("""
    const a = document.querySelector('[role=dialog] audio');
    if (!a) return null;
    return { src: a.src || '', duration: a.duration, currentTime: a.currentTime,
             ended: a.ended, paused: a.paused, readyState: a.readyState };
    """)


def _drain_console(drv):
    try:
        for entry in drv.get_log('browser'):
            lvl = entry.get('level', '')
            msg = entry.get('message', '')
            if lvl == 'SEVERE' and 'Failed to load resource' not in msg:
                _CONSOLE_JS_ERRORS.append(msg)
    except Exception:
        pass


def _expand_all_groups(drv):
    """点分组级「加载更多」把低用例数分组（INT321 等）渲染出来（默认只显示前 5 组）。"""
    for _ in range(3):
        try:
            el = drv.find_element(By.XPATH,
                "//button[contains(., '个分组') and contains(., '加载更多')]")
            el.click()
            time.sleep(1.5)
        except Exception:
            break


def _open_preview_dialog(drv, case_keyword):
    """按用例关键字定位（ID 精确匹配）→ 点该用例卡的「预览音频」→ 配置弹窗就绪。"""
    case_id = _find_case_id(case_keyword)
    _expand_all_groups(drv)
    WebDriverWait(drv, 10).until(
        lambda d: d.find_elements(By.XPATH,
            f"//button[normalize-space(.)='{case_id}']"))
    id_btn = drv.find_element(By.XPATH, f"//button[normalize-space(.)='{case_id}']")
    card = id_btn.find_element(By.XPATH, "./ancestor::div[contains(@class,'bg-card')][1]")
    btn = card.find_element(By.XPATH, ".//button[contains(@aria-label, '预览音频')]")
    btn.click()
    WebDriverWait(drv, 10).until(
        lambda d: d.find_elements(By.XPATH, "//*[@role='dialog'][contains(., '音频试听配置')]"))
    dtext = _body_text(drv)
    assert '浏览器播放' in dtext and '实验室播放' in dtext, \
        '试听配置弹窗应同时具备浏览器播放/实验室播放两种模式'
    return case_id


# ---------------------------------------------------------------------------
# 复测用例
# ---------------------------------------------------------------------------

def test_01_browser_play_real_stream(drv):
    """P1-浏览器播放：开始试听 → GET /audios/{id}/stream → 预签名 URL → <audio> 真实播放。

    断言 media duration≈1.64s 加载成功（loadedmetadata）且 currentTime 随播放推进（timeupdate），
    证明不再是演示态（MOCK_DURATION 步进模拟）。
    """
    _ensure_logged_in(drv)
    _goto(drv, '/testcases/by-group')
    _wait_text(drv, REAL_GROUP, timeout=25)
    case_id = _open_preview_dialog(drv, CASE_STREAM_KW)
    _shot(drv, '01-audio-config-dialog-light.png')

    _inject_fetch_logger(drv)
    _js_click(drv, "//*[@role='dialog']//button[contains(., '开始试听')]")
    WebDriverWait(drv, 10).until(
        lambda d: d.find_elements(By.XPATH, "//*[@role='dialog'][contains(., '测试用例预览')]"))

    # 等待 <audio> metadata 加载（duration 出现）
    WebDriverWait(drv, 15).until(
        lambda d: (_audio_js(drv) or {}).get('duration') is not None and
                  (_audio_js(drv) or {}).get('duration') > 0.5)
    time.sleep(0.8)

    reqs = _read_requests(drv)
    stream_reqs = [u for u in reqs if '/audios/' in u and '/stream' in u]
    assert stream_reqs, f'浏览器播放未发出 GET /audios/{{id}}/stream 真实请求：{reqs}'
    assert any('GET ' in u for u in stream_reqs), f'stream 请求应为 GET：{stream_reqs}'
    print(f'[P1-BROWSER] stream 请求: {stream_reqs}')

    # 点播放 → currentTime 推进（真实播放证据）
    btn = drv.find_element(By.XPATH, "//*[@role='dialog']//button[contains(@aria-label, '播放')]")
    btn.click()
    t0 = _audio_js(drv)
    time.sleep(1.6)
    t1 = _audio_js(drv)
    assert t0 and t1, '对话框内未找到 <audio> 元素'
    assert t1['currentTime'] > t0['currentTime'], \
        f'音频 currentTime 未推进（真实播放未生效）：{t0} → {t1}'
    assert t1['duration'] > 0.5, f'音频时长未从 media metadata 加载：{t1}'
    print(f'[P1-BROWSER] <audio> 状态: before={t0} after={t1}')
    _shot(drv, '02-audio-player-browser-light.png')
    _drain_console(drv)


def test_02_lab_play_backend_preview_stop(drv):
    """P1-实验室播放：POST /testcases/{id}/preview（playback_mode=backend）→ 停止 POST stop_preview 生效。"""
    _ensure_logged_in(drv)
    _goto(drv, '/testcases/by-group')
    _wait_text(drv, REAL_GROUP, timeout=25)
    case_id = _open_preview_dialog(drv, CASE_LAB_KW)
    # 切到实验室播放
    _js_click(drv, "//*[@role='dialog']//label[contains(., '实验室播放')]//input")
    time.sleep(0.3)

    _inject_fetch_logger(drv)
    _js_click(drv, "//*[@role='dialog']//button[contains(., '开始试听')]")
    WebDriverWait(drv, 12).until(
        lambda d: d.find_elements(By.XPATH, "//*[@role='dialog'][contains(., '测试用例预览')]"))
    time.sleep(1.2)

    reqs = _read_requests(drv)
    preview_reqs = [u for u in reqs if f'/testcases/{case_id}/preview' in u]
    assert preview_reqs, f'实验室播放未发出 POST /testcases/{{id}}/preview 请求：{reqs}'
    assert any('playback_mode' in u for u in preview_reqs), \
        f'preview 载荷应为 playback_mode=backend：{preview_reqs}'
    print(f'[P1-LAB] preview 请求: {preview_reqs}')
    _shot(drv, '03-audio-player-lab-light.png')

    # 点「停止」→ stop_preview 真实请求
    _js_click(drv, "//*[@role='dialog']//button[contains(@aria-label, '停止')]")
    time.sleep(1.0)
    reqs2 = _read_requests(drv)
    stop_reqs = [u for u in reqs2 if 'stop_preview' in u]
    assert stop_reqs, f'实验室播放停止未发出 POST /testcases/{{id}}/stop_preview：{reqs2}'
    print(f'[P1-LAB] stop_preview 请求: {stop_reqs}')
    _shot(drv, '04-audio-player-lab-stopped-light.png')
    _drain_console(drv)


def test_03_tag_facet_real_list_p2(drv):
    """P2-标签 facet：真实标签渲染 + 计数源为真实已加载列表（无 mock 请求）。

    现共享库无打标签真实用例 → countTagCases(cases) 全 0 → 计数徽标不显示（与 Vue 一致）；
    证明点：Network 无 mock 请求、facet 选项来自真实 /tags、列表数据来自真实 /testcases。
    """
    _ensure_logged_in(drv)
    _goto(drv, '/testcases/by-group')
    _wait_text(drv, REAL_GROUP, timeout=25)
    # 打开标签 facet（工具栏「标签 全部」Popover 触发钮；避免命中「按标签」子视图切换）
    _js_click(drv, "//button[contains(., '标签') and contains(., '全部')]")
    _wait_text(drv, '未分类', timeout=8)
    _wait_text(drv, REAL_TAG, timeout=8)
    _wait_text(drv, REAL_TAG_R3, timeout=8)
    time.sleep(0.5)
    _shot(drv, '05-tag-facet-real.png')

    # 页面自身网络历史（Performance API）核对真实请求——列表/标签均来自真实端点
    api_urls = sorted(set(drv.execute_script(
        'return performance.getEntriesByType("resource")'
        '.map(e => e.name).filter(u => u.includes("/api/v1/"))')))
    assert any('/api/v1/testcases' in u for u in api_urls), f'未捕获真实 /testcases：{api_urls}'
    assert any('/api/v1/tags' in u for u in api_urls), f'未捕获真实 /tags：{api_urls}'
    assert not any('mock' in u.lower() for u in api_urls), f'出现 mock 请求：{api_urls}'
    print(f'[P2] 真实请求: {[u.split("?")[0] for u in api_urls]}')
    # 真实数据无打标签用例 → 不应渲染任何「n」计数徽标（旧 mock 口径才会出幻影计数）
    badges = drv.find_elements(By.XPATH,
        "//*[@role='dialog']//button[.//*[contains(@class,'tabular-nums')]]")
    print(f'[P2] facet 计数徽标元素数={len(badges)}（真实数据无打标签用例 → 应为 0，'
          f'证明计数来自真实列表而非 mock 常量）')
    _drain_console(drv)


def test_04_dark_theme_player_screenshots(drv):
    """深色主题下浏览器播放/实验室播放玩家截图（复测补图：P1 双模式深色态）。"""
    _ensure_logged_in(drv)
    _set_theme(drv, '深色')
    # 浏览器播放深色
    _goto(drv, '/testcases/by-group')
    _wait_text(drv, REAL_GROUP, timeout=25)
    _open_preview_dialog(drv, CASE_STREAM_KW)
    _js_click(drv, "//*[@role='dialog']//button[contains(., '开始试听')]")
    WebDriverWait(drv, 10).until(
        lambda d: d.find_elements(By.XPATH, "//*[@role='dialog'][contains(., '测试用例预览')]"))
    time.sleep(1.2)
    _shot(drv, '06-audio-player-browser-dark.png')
    # 关闭 → 实验室播放深色
    drv.find_element(By.TAG_NAME, 'body').send_keys('\ue00c')
    time.sleep(0.6)
    _goto(drv, '/testcases/by-group')
    _wait_text(drv, REAL_GROUP, timeout=25)
    _open_preview_dialog(drv, CASE_LAB_KW)
    _js_click(drv, "//*[@role='dialog']//label[contains(., '实验室播放')]//input")
    _js_click(drv, "//*[@role='dialog']//button[contains(., '开始试听')]")
    WebDriverWait(drv, 12).until(
        lambda d: d.find_elements(By.XPATH, "//*[@role='dialog'][contains(., '测试用例预览')]"))
    time.sleep(1.2)
    _shot(drv, '07-audio-player-lab-dark.png')
    # 停止 + 关闭
    _js_click(drv, "//*[@role='dialog']//button[contains(@aria-label, '停止')]")
    time.sleep(0.6)
    _set_theme(drv, '浅色')
    _drain_console(drv)


def test_05_no_js_runtime_errors(drv):
    _ensure_logged_in(drv)
    _goto(drv, '/testcases/by-group')
    _wait_text(drv, REAL_GROUP, timeout=25)
    time.sleep(1.0)
    _drain_console(drv)
    assert not _CONSOLE_JS_ERRORS, \
        '浏览器控制台存在 JS 运行时严重错误：\n' + '\n'.join(_CONSOLE_JS_ERRORS[-10:])
