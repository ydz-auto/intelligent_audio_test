# -*- coding: utf-8 -*-
"""INT-1701 前端回归日巡冒烟（React 前端，docker 环境）。

环境（负责人 2026-10-23 环境铁律）：
- 后端网关 http://localhost:15000（database 必须为 intelligent_audio_test）
- React 前端 http://localhost:15173（容器 iat-react-frontend）
不启动任何本地栈；写操作只用本 run 自建的「接线测试_」前缀数据，结束前清理。

跑法：
    <intelligent_audio_test conda python> tests/ui/react_smoke_int1701.py --phase all

产出：tests/ui/artifacts/int1701/summary.json + 浅/深色截图。
"""
import argparse
import json
import os
import re
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ART = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1701')
CHROME_BINARY = os.environ.get(
    'UI_CHROME_BINARY', r'C:\Program Files\Google\Chrome\Application\chrome.exe')
BASE = os.environ.get('REACT_BASE', 'http://localhost:15173').rstrip('/')
API = os.environ.get('API_BASE', 'http://localhost:15000').rstrip('/')
USERNAME = os.environ.get('UI_TEST_USERNAME', '接线测试_admin')
PASSWORD = os.environ.get('UI_TEST_PASSWORD', 'JieXianTest@2026')
THEME_KEY = 'iatp:theme:v1:mode'
PREFIX = '接线测试_INT1701'

# 网络静默探针：页面数据请求常晚于首屏（报告域实测 >2s），按 in-flight 计数等静默
NET_PATCH = r"""
window.__net = { started: 0, inflight: 0, last: Date.now(), urls: [] };
function __track(url, done) {
  if (url && url.indexOf('/sse/') >= 0) return;
  window.__net.started += 1;
  window.__net.inflight += 1;
  window.__net.last = Date.now();
  window.__net.urls.push(url);
  const settle = function () {
    window.__net.inflight = Math.max(0, window.__net.inflight - 1);
    window.__net.last = Date.now();
  };
  done && done(settle);
}
const __of = window.fetch;
window.fetch = function (input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  let settle;
  __track(url, function (s) { settle = s; });
  const p = __of.apply(this, arguments);
  if (settle) { p.then(settle, settle); }
  return p;
};
const __xo = XMLHttpRequest.prototype.open;
const __xs = XMLHttpRequest.prototype.send;
XMLHttpRequest.prototype.open = function (m, u) { this.__u = u; return __xo.apply(this, arguments); };
XMLHttpRequest.prototype.send = function () {
  const x = this;
  let settle;
  __track(String(x.__u || ''), function (s) { settle = s; });
  if (settle) { x.addEventListener('loadend', settle); }
  return __xs.apply(this, arguments);
};
"""

RESULT = {'env': {}, 'pages': {}, 'chains': {}, 'screenshots': [], 'notes': []}


def log(msg):
    print('[int1701] %s' % msg, flush=True)


# ── HTTP（dev 模式免 token；写操作仅限本 run「接线测试_」数据）──────────
def http_json(method, path, body=None, timeout=180):
    url = API + '/api/v1' + path
    data = None
    headers = {'Content-Type': 'application/json'}
    if body is not None:
        data = json.dumps(body).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode('utf-8')
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode('utf-8', 'replace')
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {'raw': raw[:500]}
        return exc.code, parsed


# ── 环境校验 ─────────────────────────────────────────────
def env_check(tag):
    health = json.loads(urllib.request.urlopen(API + '/health', timeout=20).read().decode())
    html = urllib.request.urlopen(BASE + '/', timeout=20).read().decode('utf-8', 'replace')
    rec = {'tag': tag, 'health': health, 'react_build': 'lib-react' in html or 'assets/' in html,
           'html_title': re.search(r'<title>(.*?)</title>', html).group(1) if '<title>' in html else ''}
    RESULT['env'][tag] = rec
    log('ENV[%s] database=%s version=%s frontend_title=%s'
        % (tag, health.get('database'), health.get('version'), rec['html_title']))
    assert health.get('database') == 'intelligent_audio_test', '环境串库: %s' % health
    assert rec['react_build'], '前端不是 React 构建'
    return rec


# ── 浏览器 ───────────────────────────────────────────────
def _chromedriver():
    import winreg
    major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    best = ''
    if os.path.isdir(cache_root):
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if not os.path.isfile(exe):
                continue
            try:
                vmaj = int(ver.split('.')[0])
            except Exception:
                continue
            if vmaj == major:
                best = exe
    return best


def make_driver():
    opts = Options()
    opts.binary_location = CHROME_BINARY
    opts.add_argument('--headless=new')
    opts.add_argument('--window-size=1680,1050')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--lang=zh-CN')
    opts.add_argument('--disable-dev-shm-usage')
    opts.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
    drv_path = _chromedriver()
    svc = Service(executable_path=drv_path) if drv_path else Service()
    drv = webdriver.Chrome(options=opts, service=svc)
    drv.set_page_load_timeout(90)
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': NET_PATCH})
    return drv


def body_text(drv):
    return drv.execute_script('return document.body ? document.body.innerText : ""') or ''


def wait_body(drv, texts, timeout=45):
    WebDriverWait(drv, timeout).until(
        lambda d: all(t in body_text(d) for t in texts))


def set_theme(drv, mode):
    drv.execute_script('localStorage.setItem(arguments[0], arguments[1])', THEME_KEY, mode)


def wait_quiet(drv, timeout=35, quiet_ms=1500):
    """等页面网络静默：已发起过数据请求 + 无在途 + 最近 quiet_ms 无新请求。"""
    deadline = time.time() + timeout
    time.sleep(1.2)
    while time.time() < deadline:
        try:
            st = drv.execute_script('return window.__net || null')
        except Exception:
            st = None
        if st and st.get('started', 0) > 0 and st.get('inflight', 0) == 0:
            if time.time() * 1000 - st.get('last', 0) >= quiet_ms:
                return True
        time.sleep(0.25)
    return False


def shot(drv, name):
    os.makedirs(ART, exist_ok=True)
    path = os.path.join(ART, name + '.png')
    drv.save_screenshot(path)
    size = os.path.getsize(path)
    RESULT['screenshots'].append({'name': name, 'size': size})
    log('SHOT %s (%d bytes)' % (name, size))
    return {'path': os.path.relpath(path, PROJECT_ROOT), 'size': size}


def parse_perf(raw_logs):
    """Network 日志 → /api/v1/ 请求 [{method,url,status}]。"""
    pending = {}
    out = []
    for entry in raw_logs:
        try:
            msg = json.loads(entry.get('message', '{}'))
            inner = msg.get('message', {})
            method = inner.get('method', '')
            params = inner.get('params', {})
        except Exception:
            continue
        if method == 'Network.requestWillBeSent':
            rid = params.get('requestId')
            req = params.get('request', {})
            pending[rid] = {'method': req.get('method'), 'url': req.get('url')}
        elif method == 'Network.responseReceived':
            rid = params.get('requestId')
            resp = params.get('response', {})
            rec = dict(pending.get(rid) or {})
            rec['url'] = rec.get('url') or resp.get('url')
            rec['status'] = resp.get('status')
            rec['mime'] = resp.get('mimeType')
            if '/api/v1/' in (rec.get('url') or ''):
                out.append(rec)
    # 去重（同 URL+方法+状态）
    seen, uniq = set(), []
    for r in out:
        key = (r.get('method'), r.get('url'), r.get('status'))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)
    return uniq


def api_errors(apis):
    return [a for a in apis if isinstance(a.get('status'), int) and a['status'] >= 400]


def console_errors(drv):
    errs = []
    try:
        for e in drv.get_log('browser'):
            if e.get('level') != 'SEVERE':
                continue
            msg = str(e.get('message', ''))
            if 'favicon' in msg:
                continue
            errs.append(msg[:300])
    except Exception:
        pass
    return errs


def page_titles(drv):
    return [el.text.strip() for el in drv.find_elements(By.CSS_SELECTOR, 'main h1, main h2')
            if el.is_displayed() and el.text.strip()][:4]


# ── 登录 ─────────────────────────────────────────────────
def login(drv, attempts=3):
    last = ''
    for i in range(attempts):
        step = 'load'
        try:
            drv.get(BASE + '/login')
            step = 'wait-username'
            WebDriverWait(drv, 45).until(EC.presence_of_element_located((By.ID, 'username')))
            step = 'fill'
            u = drv.find_element(By.ID, 'username')
            p = drv.find_element(By.ID, 'password')
            u.clear(); u.send_keys(USERNAME)
            p.clear(); p.send_keys(PASSWORD)
            step = 'submit'
            btn = drv.find_element(By.CSS_SELECTOR, "button[type='submit']")
            drv.execute_script('arguments[0].click()', btn)
            step = 'wait-redirect'
            WebDriverWait(drv, 45).until(lambda d: '/login' not in d.current_url)
            time.sleep(1.2)
            if '/login' not in drv.current_url:
                return {'ok': True, 'url': drv.current_url, 'attempts': i + 1}
        except Exception as exc:
            last = '[%s] %s: %s | url=%s | text=%s' % (
                step, type(exc).__name__, str(exc)[:160], drv.current_url,
                (body_text(drv)[:120] if step != 'load' else ''))
            log('LOGIN retry %d %s' % (i + 1, last))
            time.sleep(2)
    return {'ok': False, 'error': last or 'login failed'}


# ── 单页走查 ─────────────────────────────────────────────
def visit(drv, route, expect, key, dark=False, ready_re=None, container='main'):
    """ready_re：数据就绪断言（正则，匹配 innerText），未命中记 note 不算硬失败。"""
    rec = {'route': route, 'ok': False, 'expected': expect, 'url': None, 'titles': [],
           'apis': [], 'api_errors': [], 'console_errors': [], 'shot': None, 'note': ''}
    try:
        set_theme(drv, 'dark' if dark else 'light')
        drv.get(BASE + route)
        WebDriverWait(drv, 60).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, container)))
        if expect:
            wait_body(drv, expect, 45)
        quiet = wait_quiet(drv, timeout=40)
        rec['quiet'] = quiet
        if ready_re:
            try:
                WebDriverWait(drv, 30).until(
                    lambda d: re.search(ready_re, body_text(d)) is not None)
                rec['ready_text'] = re.search(ready_re, body_text(d)).group(0)
            except Exception:
                rec['note'] = '数据就绪断言未命中: %s' % ready_re
        rec['url'] = drv.current_url
        time.sleep(0.8)
        rec['titles'] = page_titles(drv)
        rec['apis'] = parse_perf(drv.get_log('performance'))
        rec['api_errors'] = api_errors(rec['apis'])
        rec['console_errors'] = console_errors(drv)
        if dark:
            cls = drv.execute_script('return document.documentElement.className')
            rec['html_class'] = cls
            if 'dark' not in (cls or ''):
                rec['note'] = (rec['note'] + ' 深色类未应用').strip()
        rec['shot'] = shot(drv, key)
        rec['ok'] = bool(rec['titles']) or bool(expect)
    except Exception as exc:
        rec['note'] = 'EXC %s: %s' % (type(exc).__name__, str(exc)[:250])
        rec['url'] = drv.current_url
        try:
            rec['shot'] = shot(drv, key + '_FAIL')
            rec['page_snippet'] = body_text(drv)[:400]
        except Exception:
            pass
        log('FAIL %s %s' % (route, rec['note']))
    return rec


def capture_login_page_fresh():
    """独立干净会话截 /login（已登录会话访问 /login 会被守卫重定向）。"""
    drv = make_driver()
    rec = {'route': '/login', 'ok': False, 'expected': ['登录', '用户名或电子邮件'],
           'url': None, 'titles': [], 'apis': [], 'api_errors': [], 'console_errors': [],
           'shot': None, 'note': ''}
    try:
        drv.get(BASE + '/login')
        WebDriverWait(drv, 60).until(EC.presence_of_element_located((By.ID, 'username')))
        wait_body(drv, ['登录', '用户名或电子邮件'], 45)
        time.sleep(1.0)
        rec['url'] = drv.current_url
        rec['apis'] = parse_perf(drv.get_log('performance'))
        rec['api_errors'] = api_errors(rec['apis'])
        rec['console_errors'] = console_errors(drv)
        rec['has_form'] = bool(drv.find_elements(By.ID, 'username')) and bool(
            drv.find_elements(By.ID, 'password'))
        rec['shot'] = shot(drv, 'page_login_light')
        rec['ok'] = rec['has_form']
    except Exception as exc:
        rec['note'] = 'EXC %s: %s' % (type(exc).__name__, str(exc)[:200])
        try:
            rec['shot'] = shot(drv, 'page_login_light_FAIL')
        except Exception:
            pass
    finally:
        try:
            drv.quit()
        except Exception:
            pass
    return rec


def try_step(name, fn):
    try:
        out = fn()
        RESULT['chains'][name] = out
        log('CHAIN %s ok=%s' % (name, out.get('ok') if isinstance(out, dict) else 'n/a'))
    except Exception as exc:
        RESULT['chains'][name] = {'ok': False,
                                  'error': '%s: %s' % (type(exc).__name__, str(exc)[:400]),
                                  'trace': traceback.format_exc()[-800:]}
        log('CHAIN %s ERROR %s' % (name, exc))


# ── 关键链路 1：登录 → 任务列表 → 任务详情 ─────────────────
def chain_login_to_task(drv):
    out = {'ok': False, 'steps': []}
    drv.get(BASE + '/tasks/daily')
    WebDriverWait(drv, 60).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, 'table tbody tr')) > 0)
    time.sleep(1.5)
    rows = drv.find_elements(By.CSS_SELECTOR, 'table tbody tr')
    first = rows[0]
    cells = [c.text.strip() for c in first.find_elements(By.TAG_NAME, 'td')]
    out['steps'].append({'step': '任务列表', 'rows': len(rows), 'first_row': cells[:6],
                         'url': drv.current_url})
    out['shot_list'] = shot(drv, 'chain1_1_task_list')
    # 行内「查看详情」
    btn = first.find_element(By.CSS_SELECTOR, "button[title='查看详情']")
    drv.execute_script('arguments[0].click()', btn)
    WebDriverWait(drv, 60).until(lambda d: re.search(r'/tasks/\d+', d.current_url))
    time.sleep(2.5)
    out['detail_url'] = drv.current_url
    out['detail_titles'] = page_titles(drv)
    out['detail_text_head'] = body_text(drv)[:400]
    apis = parse_perf(drv.get_log('performance'))
    out['detail_apis'] = apis
    out['detail_api_errors'] = api_errors(apis)
    out['console_errors'] = console_errors(drv)
    out['shot_detail'] = shot(drv, 'chain1_2_task_detail')
    out['task_id'] = int(re.search(r'/tasks/(\d+)', drv.current_url).group(1))
    out['ok'] = bool(out['detail_titles']) and not out['detail_api_errors']
    return out


# ── 关键链路 2：用例列表 → 用例详情 ────────────────────────
def chain_cases(drv):
    out = {'ok': False, 'steps': []}
    drv.get(BASE + '/testcases/by-tag')
    WebDriverWait(drv, 90).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "button[title='查看用例详情']")))
    time.sleep(2.0)
    cards = drv.find_elements(By.CSS_SELECTOR, "button[title='查看用例详情']")
    out['steps'].append({'step': '用例列表', 'case_cards': len(cards),
                         'first': cards[0].text.strip()[:80], 'url': drv.current_url})
    out['list_apis'] = parse_perf(drv.get_log('performance'))
    out['shot_list'] = shot(drv, 'chain2_1_case_list')
    drv.execute_script('arguments[0].click()', cards[0])
    WebDriverWait(drv, 40).until(
        lambda d: any(x.is_displayed() for x in d.find_elements(By.CSS_SELECTOR, '[role="dialog"]')))
    time.sleep(1.5)
    dlg = [x for x in drv.find_elements(By.CSS_SELECTOR, '[role="dialog"]') if x.is_displayed()][0]
    out['dialog_text_head'] = dlg.text[:600]
    apis = parse_perf(drv.get_log('performance'))
    out['detail_apis'] = apis
    out['detail_api_errors'] = api_errors(apis)
    out['shot_detail'] = shot(drv, 'chain2_2_case_detail')
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(0.8)
    out['ok'] = bool(out['dialog_text_head'])
    return out


# ── 关键链路 3：发布正式任务 → 正式任务列表/详情 → 再执行 ───
def chain_publish(drv):
    out = {'ok': False, 'steps': []}
    # 1) 自建源任务（接线测试_ 前缀）
    status, case_resp = http_json('GET', '/testcases?page=1&per_page=1')
    case_items = (case_resp.get('data') or {}).get('items') or []
    if not case_items:
        raise AssertionError('无可用用例，无法自建源任务')
    case_id = case_items[0]['id']
    out['case_id'] = case_id
    status, created = http_json('POST', '/tasks', {
        'name': '%s_发布源' % PREFIX,
        'description': 'INT-1701 日巡冒烟自建，结束删除',
        'case_ids': [case_id],
        'visibility': 'shared',
    })
    out['create_status'] = status
    src_id = (created.get('data') or {}).get('id')
    out['source_task_id'] = src_id
    log('created source task %s status=%s' % (src_id, status))
    if status not in (200, 201) or not src_id:
        raise AssertionError('源任务创建失败: %s %s' % (status, created))

    # 2) UI 发布（任务列表行菜单 → 发布 → 弹窗主钮）
    drv.get(BASE + '/tasks/daily')
    WebDriverWait(drv, 60).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, 'table tbody tr')) > 0)
    # 搜索关键字定位自建任务
    try:
        search_box = drv.find_element(By.CSS_SELECTOR, "input[placeholder*='搜索']")
        search_box.clear(); search_box.send_keys('%s_发布源' % PREFIX)
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ENTER)
        time.sleep(2.5)
    except Exception as exc:
        out['steps'].append({'step': '搜索定位', 'note': str(exc)[:150]})
    rows = drv.find_elements(By.CSS_SELECTOR, 'table tbody tr')
    target = None
    for r in rows:
        if '%s_发布源' % PREFIX in r.text:
            target = r
            break
    if target is None:
        raise AssertionError('列表未找到自建源任务行（rows=%d）' % len(rows))
    out['row_text'] = target.text[:200]
    target.find_element(By.CSS_SELECTOR, "button[aria-label='任务操作']").click()
    time.sleep(1.0)
    menu_items = [m for m in drv.find_elements(By.CSS_SELECTOR, "[role='menuitem']") if m.is_displayed()]
    out['menu_items'] = [m.text.strip() for m in menu_items]
    publish_item = next((m for m in menu_items if m.text.strip() == '发布'), None)
    if publish_item is None:
        raise AssertionError('行菜单无「发布」项: %s' % out['menu_items'])
    drv.execute_script('arguments[0].click()', publish_item)
    WebDriverWait(drv, 30).until(
        lambda d: any(x.is_displayed() for x in d.find_elements(By.CSS_SELECTOR, '[role="dialog"]')))
    time.sleep(1.5)
    dlg = [x for x in drv.find_elements(By.CSS_SELECTOR, '[role="dialog"]') if x.is_displayed()][0]
    out['publish_dialog_text'] = dlg.text[:400]
    out['shot_publish_dialog'] = shot(drv, 'chain3_1_publish_dialog')
    # 主钮：弹窗内「发布」
    submit = None
    for b in dlg.find_elements(By.TAG_NAME, 'button'):
        if b.is_displayed() and b.text.strip() == '发布':
            submit = b
    if submit is None:
        raise AssertionError('发布弹窗无主钮')
    parse_perf(drv.get_log('performance'))  # 清空旧日志
    drv.execute_script('arguments[0].click()', submit)
    time.sleep(3.5)
    apis = parse_perf(drv.get_log('performance'))
    out['publish_apis'] = apis
    out['publish_api_errors'] = api_errors(apis)
    out['publish_toast'] = body_text(drv)[:300]
    pub_id = None
    for a in apis:
        if '/published-tasks' in (a.get('url') or '') and a.get('method') == 'POST':
            pub_id = None
    # 从列表确认（GET /published-tasks 取 keyword 匹配）
    status, pub_list = http_json('GET', '/published-tasks?page=1&per_page=50&keyword=%s'
                                 % urllib.parse.quote('%s_发布源' % PREFIX))
    items = (pub_list.get('data') or {}).get('items') or []
    match = [i for i in items if PREFIX in (i.get('name') or '')]
    if match:
        pub_id = match[0]['id']
    out['published_task_id'] = pub_id
    if pub_id is None:
        raise AssertionError('发布后未查到已发布任务: %s' % str(pub_list)[:300])

    # 3) 正式任务列表 + 详情（展开版本链）
    drv.get(BASE + '/tasks/published')
    WebDriverWait(drv, 60).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, 'table tbody tr')) > 0)
    time.sleep(2.0)
    out['published_list_apis'] = parse_perf(drv.get_log('performance'))
    out['published_list_api_errors'] = api_errors(out['published_list_apis'])
    out['shot_published_list'] = shot(drv, 'chain3_2_published_list')
    prow = next((r for r in drv.find_elements(By.CSS_SELECTOR, 'table tbody tr')
                 if '%s_发布源' % PREFIX in r.text), None)
    if prow is None:
        raise AssertionError('正式任务列表未找到自建记录')
    out['published_row_text'] = prow.text[:200]
    drv.execute_script('arguments[0].click()',
                       prow.find_element(By.CSS_SELECTOR, "button[aria-label='展开版本详情']"))
    time.sleep(3.0)
    out['published_detail_text'] = body_text(drv)[:600]
    detail_apis = parse_perf(drv.get_log('performance'))
    out['published_detail_apis'] = detail_apis
    out['published_detail_api_errors'] = api_errors(detail_apis)
    out['shot_published_detail'] = shot(drv, 'chain3_3_published_detail')

    # 4) 基于正式任务再执行（行内「执行」→ 确认弹窗）
    exec_btn = None
    for b in prow.find_elements(By.TAG_NAME, 'button'):
        if b.is_displayed() and b.text.strip() == '执行':
            exec_btn = b
    if exec_btn is None:
        raise AssertionError('正式任务行无「执行」按钮')
    drv.execute_script('arguments[0].click()', exec_btn)
    WebDriverWait(drv, 30).until(
        lambda d: any(x.is_displayed() for x in d.find_elements(By.CSS_SELECTOR, '[role="dialog"]')))
    time.sleep(0.8)
    cdlg = [x for x in drv.find_elements(By.CSS_SELECTOR, '[role="dialog"]') if x.is_displayed()][0]
    out['execute_confirm_text'] = cdlg.text[:300]
    parse_perf(drv.get_log('performance'))
    confirm = None
    for b in cdlg.find_elements(By.TAG_NAME, 'button'):
        if b.is_displayed() and b.text.strip() in ('执行', '确定', '确认执行'):
            confirm = b
    if confirm is None:
        raise AssertionError('执行确认弹窗无确认钮: %s' % out['execute_confirm_text'])
    drv.execute_script('arguments[0].click()', confirm)
    time.sleep(4.0)
    exec_apis = parse_perf(drv.get_log('performance'))
    out['execute_apis'] = exec_apis
    out['execute_api_errors'] = api_errors(exec_apis)
    out['after_execute_url'] = drv.current_url
    out['shot_after_execute'] = shot(drv, 'chain3_4_after_execute')
    # 新日常任务 id（从 URL 或接口响应摘要）
    m = re.search(r'/tasks/(\d+)', drv.current_url)
    out['new_task_id'] = int(m.group(1)) if m else None
    if out['new_task_id'] is None:
        # 从 /tasks 列表按名称查
        status, tl = http_json('GET', '/tasks?page=1&per_page=20&search=%s'
                               % urllib.parse.quote('%s_发布源' % PREFIX))
        cands = [i for i in ((tl.get('data') or {}).get('items') or [])
                 if PREFIX in (i.get('name') or '') and i.get('id') != src_id]
        if cands:
            out['new_task_id'] = cands[0]['id']
    out['ok'] = (not out['publish_api_errors']) and pub_id is not None and out['new_task_id'] is not None
    return out


# ── 清理 ─────────────────────────────────────────────────
def cleanup(ids):
    done = {}
    for tid in ids.get('tasks', []):
        if not tid:
            continue
        st, resp = http_json('DELETE', '/tasks/%s' % tid)
        done['task:%s' % tid] = {'status': st, 'resp': str(resp)[:200]}
    pid = ids.get('published_task')
    if pid:
        st, resp = http_json('POST', '/published-tasks/%s/archive' % pid)
        done['published_task:%s' % pid] = {'status': st, 'resp': str(resp)[:200],
                                           'note': '已发布任务无删除端点，仅归档（残留记录）'}
    RESULT['cleanup'] = done
    return done


def verify_no_residue():
    st, tl = http_json('GET', '/tasks?page=1&per_page=50&search=%s'
                       % urllib.parse.quote(PREFIX))
    items = [i for i in ((tl.get('data') or {}).get('items') or [])
             if PREFIX in (i.get('name') or '') and not i.get('deleted')]
    st2, pt = http_json('GET', '/published-tasks?page=1&per_page=50&keyword=%s'
                        % urllib.parse.quote(PREFIX))
    pubs = [i for i in ((pt.get('data') or {}).get('items') or [])
            if PREFIX in (i.get('name') or '')]
    RESULT['residue'] = {'tasks': items, 'published_tasks': pubs}
    log('RESIDUE tasks=%d published=%d' % (len(items), len(pubs)))
    return RESULT['residue']


# ── main ────────────────────────────────────────────────
def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument('--phase', default='all', choices=['pages', 'chains', 'all', 'cleanup'])
    ap.add_argument('--chains', default='1,2,3')
    args = ap.parse_args()
    os.makedirs(ART, exist_ok=True)

    env_check('start')

    if args.phase == 'cleanup':
        print(json.dumps(verify_no_residue(), ensure_ascii=False, indent=2))
        return

    drv = make_driver()
    try:
        # 登录先行：AUTH_MODE=off 下 /login 在会话建立后会被守卫重定向，
        # 登录页截图放到全部走查结束后用独立干净会话补拍（capture_login_page_fresh）。
        RESULT['login'] = login(drv)
        log('LOGIN %s' % RESULT['login'])
        if not RESULT['login'].get('ok'):
            raise AssertionError('登录失败: %s' % RESULT['login'])
        set_theme(drv, 'light')

        if args.phase in ('pages', 'all'):
            # 取真实 id
            st, t = http_json('GET', '/tasks?page=1&per_page=1')
            task_id = (((t.get('data') or {}).get('items') or [{}])[0]).get('id')
            st, rp = http_json('GET', '/reports?page=1&per_page=1')
            report_item = ((rp.get('data') or {}).get('items') or [{}])[0]
            report_id = report_item.get('id')
            report_name = (report_item.get('name') or '')[:20]
            RESULT['ids'] = {'task': task_id, 'report': report_id, 'report_name': report_name}

            pages = [
                ('/tasks/daily', ['任务管理', '日常'], 'tasks_daily', True, None),
                ('/tasks/published', ['任务管理', '已发布'], 'tasks_published', False, None),
                ('/testcases/by-group', ['用例管理', '按分组'], 'testcases_by_group', True, None),
                ('/testcases/by-tag', ['用例管理', '按标签'], 'testcases_by_tag', False, None),
                ('/reports', ['浏览测试报告'], 'reports_showcase', True,
                 r'共\s*\d+\s*个已发布报告'),
                ('/report-center', ['浏览测试报告，按任务与算法检索'], 'report_center', True,
                 r'共\s*\d+\s*个报告'),
            ]
            if task_id:
                pages.append(('/tasks/%s' % task_id, [], 'task_detail', True, None))
            if report_id:
                pages.append(('/report/%s' % report_id, [report_name] if report_name else [],
                              'report_view', True, None))
            for route, expect, key, need_dark, ready_re in pages:
                RESULT['pages'][key] = visit(drv, route, expect, 'page_' + key,
                                             dark=False, ready_re=ready_re)
                if need_dark:
                    RESULT['pages'][key + '_dark'] = visit(
                        drv, route, expect, 'page_' + key + '_dark', dark=True,
                        ready_re=ready_re)
            set_theme(drv, 'light')

        if args.phase in ('chains', 'all'):
            sel = set((args.chains or '').split(','))
            if '1' in sel:
                try_step('1_login_task_detail', lambda: chain_login_to_task(drv))
            if '2' in sel:
                try_step('2_cases', lambda: chain_cases(drv))
            if '3' in sel:
                try_step('3_publish_execute', lambda: chain_publish(drv))

            ids = {'tasks': [], 'published_task': None}
            c3 = RESULT['chains'].get('3_publish_execute') or {}
            for k in ('source_task_id', 'new_task_id'):
                if c3.get(k):
                    ids['tasks'].append(c3[k])
            ids['published_task'] = c3.get('published_task_id')
            cleanup(ids)
            verify_no_residue()

        env_check('end')
    finally:
        try:
            drv.quit()
        except Exception:
            pass

    if args.phase in ('pages', 'all'):
        # 独立干净会话补拍登录页（此时主会话已登录，/login 会被守卫重定向）
        try:
            RESULT['pages']['login'] = capture_login_page_fresh()
        except Exception as exc:
            RESULT['pages']['login'] = {'ok': False,
                                        'note': 'EXC %s: %s' % (type(exc).__name__, str(exc)[:150])}

    out_path = os.path.join(ART, 'summary.json')
    with open(out_path, 'w', encoding='utf-8') as fh:
        json.dump(RESULT, fh, ensure_ascii=False, indent=2)
    print('\nSUMMARY_JSON=%s' % out_path)
    # 简要控制台汇总
    for k, v in RESULT['pages'].items():
        print('PAGE %-28s ok=%s api_err=%s titles=%s note=%s'
              % (k, v.get('ok'), len(v.get('api_errors') or []), v.get('titles'), v.get('note', '')[:80]))
    for k, v in RESULT['chains'].items():
        print('CHAIN %-24s ok=%s %s' % (k, v.get('ok'), (v.get('error') or '')[:120]))


if __name__ == '__main__':
    main()
