# -*- coding: utf-8 -*-
"""INT-1488 复走·React·日志域：筛选/查询/详情 + 导出/清除/实时配置三模态窗深走。

环境：docker iat-react-frontend http://localhost:15173 + 真实库栈 http://localhost:15000
（database=intelligent_audio_test）。只读为主：清空弹窗只验确认/取消路径，不提交。
"""
import json
import os
import shutil
import sys
import time
import urllib.parse
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

BASE = os.environ.get('REACT_BASE', 'http://localhost:15173')
API = os.environ.get('API_BASE', 'http://localhost:15000')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.path.join('tests', 'ui', 'artifacts', 'int1488')
DL = os.path.join(ART, 'downloads')
THEME_KEY = 'iatp:theme:v1:mode'

RESULTS = {'env': [], 'steps': {}, 'requests': [], 'screenshots': []}
FAIL = []

FETCH_PATCH = r"""
window.__fetchLog = [];
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = ((init && init.method) || 'GET').toUpperCase();
  const entry = { url: url, method: method, reqBody: init && init.body ? String(init.body) : null };
  try {
    const res = await __origFetch.apply(this, arguments);
    entry.status = res.status;
    entry.resCt = res.headers.get('content-type') || '';
    window.__fetchLog.push(entry);
    return res;
  } catch (e) {
    entry.error = String(e);
    window.__fetchLog.push(entry);
    throw e;
  }
};
"""


def log(msg):
    print(msg, flush=True)


def env_check(tag):
    health = json.loads(urllib.request.urlopen(API + '/health', timeout=15).read().decode())
    html = urllib.request.urlopen(BASE + '/', timeout=15).read().decode()
    mark = 'lib-react' in html
    RESULTS['env'].append({'tag': tag, 'health': health, 'lib_react': mark})
    log('ENV[%s]: database=%s lib-react=%s' % (tag, health.get('database'), mark))
    assert health.get('database') == 'intelligent_audio_test', '环境串库：%s' % health
    assert mark, '前端不是 React 构建'
    return health


def api_get(path, params=None):
    url = API + '/api/v1' + path
    if params:
        url += '?' + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=60) as resp:
        return json.loads(resp.read().decode()).get('data')


def api_total(params=None):
    data = api_get('/logs', dict(params or {}, page=1, per_page=1))
    return data.get('total')


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-features=DownloadBubble')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    options.add_experimental_option('prefs', {
        'download.default_directory': os.path.abspath(DL),
        'download.prompt_for_download': False,
        'download.directory_upgrade': True,
        'safebrowsing.enabled': True,
    })
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    drv_path = ''
    if chrome_major and os.path.isdir(cache_root):
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    if tuple(int(x) for x in ver.split('.') if x.isdigit())[0] == chrome_major:
                        drv_path = exe
                except Exception:
                    continue
    service = Service(executable_path=drv_path) if drv_path else Service()
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(60)
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    return drv


def body(drv):
    return drv.execute_script('return document.body.textContent || ""') or ''


def wait_text(drv, text, timeout=25):
    WebDriverWait(drv, timeout).until(lambda d: text in body(d))


def js_click(drv, el):
    drv.execute_script('arguments[0].click()', el)


def fetch_log(drv):
    return drv.execute_script('return window.__fetchLog || []') or []


def clear_fetch_log(drv):
    drv.execute_script('window.__fetchLog = []')


def find_button(drv, text, root=None):
    root = root or drv
    for b in root.find_elements(By.XPATH, ".//button[normalize-space(.)='%s']" % text):
        if b.is_displayed():
            return b
    return None


def click_button(drv, text, root=None):
    b = find_button(drv, text, root)
    if b is None:
        raise AssertionError('按钮未找到: %s' % text)
    js_click(drv, b)
    time.sleep(0.6)


def dialog(drv):
    for d in drv.find_elements(By.CSS_SELECTOR, '[role="dialog"]'):
        if d.is_displayed():
            return d
    return None


def wait_dialog(drv, timeout=15):
    return WebDriverWait(drv, timeout).until(lambda d: dialog(d))


def set_theme_and_goto_logs(drv, theme):
    drv.get(BASE + '/')
    time.sleep(1.0)
    drv.execute_script('localStorage.setItem(%r, %r)' % (THEME_KEY, theme))
    drv.get(BASE + '/logs')
    WebDriverWait(drv, 40).until(lambda d: len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')) > 0)
    time.sleep(1.2)
    cls = drv.execute_script('return document.documentElement.className')
    if theme == 'dark':
        WebDriverWait(drv, 15).until(lambda d: 'dark' in d.execute_script('return document.documentElement.className'))
    return cls


def shot(drv, name):
    path = os.path.join(ART, name)
    drv.save_screenshot(path)
    ok = os.path.getsize(path) > 10_000
    RESULTS['screenshots'].append({'name': name, 'size': os.path.getsize(path)})
    log('SHOT %s size=%d' % (name, os.path.getsize(path)))
    assert ok, '截图过小 %s' % name
    return path


def page_total_text(drv):
    import re
    m = re.search(r'共\s*([\d,]+)\s*条日志', body(drv))
    return int(m.group(1).replace(',', '')) if m else None


def _visible_contents(drv):
    return [c for c in drv.find_elements(By.CSS_SELECTOR, '[data-slot="select-content"]') if c.is_displayed()]


def _open_trigger(drv, trig):
    """点开触发器，返回本次新出现的 popup（base-ui 多弹层可同时打开，按新 id 判定）。"""
    before = {c.id for c in _visible_contents(drv)}
    js_click(drv, trig)
    deadline = time.time() + 10
    while time.time() < deadline:
        for c in _visible_contents(drv):
            if c.id not in before:
                time.sleep(0.3)
                return c
        time.sleep(0.2)
    raise AssertionError('下拉未打开')


def _close_popups(drv):
    try:
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    except Exception:
        pass
    time.sleep(0.4)


def open_select(drv, aria_label, root=None, index=0):
    root = root or drv
    _close_popups(drv)
    trigs = [t for t in root.find_elements(
        By.CSS_SELECTOR, '[aria-label="%s"][role="combobox"], button[aria-label="%s"]' % (aria_label, aria_label))
        if t.is_displayed()]
    if not trigs:
        raise AssertionError('触发器未找到: %s' % aria_label)
    trig = trigs[index]
    content = _open_trigger(drv, trig)
    items = [i for i in content.find_elements(By.CSS_SELECTOR, '[data-slot="select-item"]') if i.is_displayed()]
    return trig, content, items


def select_option(drv, aria_label, option_text, root=None):
    trig, content, items = open_select(drv, aria_label, root)
    names = [(i.text or '').strip() for i in items]
    target = None
    for i in items:
        if (i.text or '').strip() == option_text:
            target = i
            break
    if target is None:
        raise AssertionError('选项未找到 %s，现有=%s' % (option_text, names))
    js_click(drv, target)
    time.sleep(0.9)
    _close_popups(drv)
    return names


def select_options(drv, aria_label, root=None):
    trig, content, items = open_select(drv, aria_label, root)
    names = [(i.text or '').strip() for i in items]
    _close_popups(drv)
    return names


def set_input_js(drv, el, value):
    drv.execute_script(
        "const el=arguments[0];const v=arguments[1];"
        "const s=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;"
        "s.call(el,v);el.dispatchEvent(new Event('input',{bubbles:true}));", el, value)
    time.sleep(0.8)


def wait_download(prefix, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        files = [f for f in os.listdir(DL) if not f.endswith('.crdownload')]
        done = [f for f in files if f.startswith(prefix)]
        if done:
            path = os.path.join(DL, sorted(done, key=lambda f: os.path.getmtime(os.path.join(DL, f)))[-1])
            size = os.path.getsize(path)
            # 等文件写满
            prev = -1
            stable = 0
            while time.time() < deadline and stable < 3:
                time.sleep(0.4)
                cur = os.path.getsize(path)
                stable = stable + 1 if cur == prev else 0
                prev = cur
            return path, os.path.getsize(path)
        time.sleep(0.5)
    return None, 0


def step(name, fn):
    log('\n===== %s =====' % name)
    try:
        out = fn()
        RESULTS['steps'][name] = {'ok': True, 'detail': out}
        log('OK %s: %s' % (name, json.dumps(out, ensure_ascii=False)[:1200]))
        return out
    except Exception as e:
        import traceback
        traceback.print_exc()
        RESULTS['steps'][name] = {'ok': False, 'error': repr(e)}
        FAIL.append(name)
        return None
