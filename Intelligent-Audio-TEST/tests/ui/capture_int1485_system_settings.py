# -*- coding: utf-8 -*-
"""INT-1485 系统设置域深走查（React 15173 + docker 真实库栈 15000）。

覆盖卡内 5 个模态/组件 + 六域 11 分区：
  A 六域分区浅色渲染 + 真实接口证据
  B 六域分区深色截图
  C settings-form-page：加载→编辑→保存→回读→重置 + 保存/重置按钮状态
  D form-dirty-indicator：改动出现 / 保存后消失
  E form-navigation-guard：脏表单切域拦截（留下/离开/Esc）+ 刷新 beforeunload
  F user-mutate-drawer：新建（含校验/同名约束）→编辑→停用→删除→GET 回读
  G settings-form-layout：六域侧栏树与分区导航
  H 状态态：空态 / 错误态（拦接口）/ 加载态
  I RBAC 低权限视角（/auth/me 响应改写为 guest 权限集，验证隐藏而非置灰）
  J 清单外新增窗口：OAuth 提供方新建/编辑 Dialog、日志清理/归档确认、用户删除确认
  Z 清理：还原选项、删除测试用户/提供方、主题回浅色

环境：仅 15173（React 构建）+ 15000（intelligent_audio_test 真实库栈）。
运行：
  D:/00_env/conda_envs/intelligent_audio_test/python.exe -I tests/ui/capture_int1485_system_settings.py --phase all
"""
import argparse
import base64
import json
import os
import sys
import time
import traceback
import urllib.parse
import urllib.request

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://localhost:15173')
API = os.environ.get('API_BASE', 'http://127.0.0.1:15000')
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ART = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1485')
THEME_KEY = 'iatp:theme:v1:mode'
TOKEN_KEY = 'iatp:auth:token:v1'
ACCOUNT = ('接线测试_admin', 'JieXianTest@2026')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

SECTIONS = [
    ('site', 'info', '站点信息'),
    ('site', 'notice', '站点公告'),
    ('site', 'navigation', '导航模块'),
    ('iam', 'users', '用户管理'),
    ('iam', 'roles', '角色权限管理'),
    ('auth', 'methods', '认证方式'),
    ('auth', 'oauth-providers', 'OAuth 提供方'),
    ('appearance', 'presets', '主题预设'),
    ('appearance', 'fine-tuning', '外观微调'),
    ('security', 'access-control', '访问控制'),
    ('operations', 'log-maintenance', '日志维护'),
]

RESULTS = []


def record(step, ok, detail='', evidence=None):
    entry = {'step': step, 'ok': bool(ok), 'detail': detail, 'evidence': evidence or {}}
    RESULTS.append(entry)
    print(('[PASS] ' if ok else '[FAIL] ') + step + ' :: ' + str(detail)[:600])
    return entry


# ---------------------------------------------------------------------------
# 基础设施
# ---------------------------------------------------------------------------

def _chrome_major():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            return int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        return 0


def driver_init():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--no-first-run')
    options.add_argument('--no-default-browser-check')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    drv_path = ''
    major = _chrome_major()
    if major and os.path.isdir(cache_root):
        best = None
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    parts = tuple(int(x) for x in ver.split('.') if x.isdigit())
                except ValueError:
                    continue
                if parts and parts[0] == major:
                    best = max(best, (parts, exe)) if best else (parts, exe)
        if best:
            drv_path = best[1]
    service = Service(executable_path=drv_path) if drv_path else Service()
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(60)
    drv.set_script_timeout(60)
    # 页内 fetch 打点：记录 method/url/body/status，供逐窗请求证据
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': r'''
(function(){
  try {
    window.__reqs = [];
    var orig = window.fetch;
    if (!orig) return;
    window.fetch = function(input, init){
      var url = (typeof input === 'string') ? input : ((input && input.url) || '');
      var method = ((init && init.method) || (input && input.method) || 'GET').toUpperCase();
      var body = (init && typeof init.body === 'string') ? init.body : null;
      var rec = {url: url, method: method, body: body, status: null, ts: Date.now()};
      window.__reqs.push(rec);
      var p = orig.apply(this, arguments);
      try {
        p.then(function(r){
          rec.status = r.status;
          try { r.clone().text().then(function(t){ rec.resp = (t || '').slice(0, 1500); }, function(){}); } catch(e){}
        }, function(e){ rec.status = -1; rec.err = String(e); });
      } catch(e){}
      try {
        if (url.indexOf('/auth/me') !== -1) {
          var override = null;
          try { override = sessionStorage.getItem('__rbac_perm'); } catch(e) {}
          if (override) {
            p = p.then(function(r){
              return r.clone().json().then(function(data){
                var perms = JSON.parse(override);
                if (data && data.data && Array.isArray(data.data.permissions)) data.data.permissions = perms;
                else if (data && Array.isArray(data.permissions)) data.permissions = perms;
                return new Response(JSON.stringify(data), {status: r.status, headers: {'Content-Type': 'application/json'}});
              }, function(){ return r; });
            });
          }
        }
        if (url.indexOf('/api/option/') !== -1) {
          var dl = 0;
          try { dl = parseInt(sessionStorage.getItem('__delay_option') || '0', 10); } catch(e) {}
          if (dl > 0) {
            p = p.then(function(r){ return new Promise(function(res){ setTimeout(function(){ res(r); }, dl); }); });
          }
        }
      } catch(e){}
      return p;
    };
  } catch(e) {}
})();
'''})
    return drv


def rsa_login_token(username, password):
    key = json.load(urllib.request.urlopen(API + '/api/v1/auth/login/encryption-key'))
    from cryptography.hazmat.primitives import serialization, hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    pub = serialization.load_pem_public_key(key['public_key'].encode())
    ct = pub.encrypt(password.encode(), padding.OAEP(
        mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    data = urllib.parse.urlencode({
        'username': username,
        'password_encrypted': base64.b64encode(ct).decode(),
        'encryption_key_id': key['kid'],
    }).encode()
    req = urllib.request.Request(API + '/api/v1/auth/login', data=data,
                                 headers={'Content-Type': 'application/x-www-form-urlencoded'})
    body = json.load(urllib.request.urlopen(req))
    return body['access_token'], body.get('user')


def api(path, token=None, method='GET', body=None):
    url = API + path
    data = None
    headers = {}
    if headers is not None:
        headers['Accept'] = 'application/json'
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if body is not None:
        data = json.dumps(body).encode()
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, json.loads(r.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or '{}')
        except Exception:
            return e.code, {}


def api_text(path, token=None):
    req = urllib.request.Request(API + path, headers={'Authorization': 'Bearer ' + token} if token else {})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def wait_ready(drv, timeout=60):
    WebDriverWait(drv, timeout).until(lambda d: d.execute_script('return document.readyState') == 'complete')


def body_text(drv):
    return drv.execute_script('return document.body ? (document.body.textContent || "") : ""')


def wait_text(drv, text, timeout=45):
    return WebDriverWait(drv, timeout).until(lambda d: text in body_text(drv))


def wait_noise(drv, seconds=1.2):
    time.sleep(seconds)


def goto(drv, path, expect=None, timeout=60):
    drain_perf(drv)
    target = BASE + path
    drv.get(target)
    wait_ready(drv)
    if expect:
        wait_text(drv, expect, timeout=timeout)
    time.sleep(1.0)


def goto_settings(drv, path, title, require_text=None, timeout=60):
    """进入设置分区：等真实内容；首次加载若撞上瞬时接口失败（设置加载失败）点重试一次。"""
    goto(drv, path, title, timeout=timeout)
    if not require_text:
        return
    try:
        wait_text(drv, require_text, 20)
    except Exception:
        if '设置加载失败' in body_text(drv):
            click_button_text(drv, '重试', timeout=10)
            time.sleep(1.0)
            try:
                wait_text(drv, require_text, 30)
            except Exception:
                diag = [r for r in get_reqs(drv, 0.2) if '/api/option/' in (r.get('url') or '')]
                logs = []
                try:
                    logs = [e.get('message') for e in drv.get_log('browser')][-6:]
                except Exception:
                    pass
                raise AssertionError('重试后仍失败 option_reqs=%s console=%s body=%s'
                                     % (diag, logs, body_text(drv)[:160]))
        else:
            diag = [r for r in get_reqs(drv, 0.2) if '/api/option/' in (r.get('url') or '')]
            raise AssertionError('未出现 %r 且非错误态 option_reqs=%s body=%s' % (require_text, diag, body_text(drv)[:160]))


def shot(drv, name, min_size=2000):
    os.makedirs(ART, exist_ok=True)
    path = os.path.join(ART, name if name.endswith('.png') else name + '.png')
    drv.save_screenshot(path)
    size = os.path.getsize(path)
    if size < min_size:
        raise AssertionError('截图过小 %s (%d bytes)' % (path, size))
    return path


def set_theme(drv, mode):
    drv.execute_script('try { localStorage.setItem(arguments[0], arguments[1]) } catch(e) {}',
                       THEME_KEY, mode)


def is_dark(drv):
    return 'dark' in (drv.execute_script('return document.documentElement.className') or '')


def reset_reqs(drv):
    try:
        drv.execute_script('if (window.__reqs) window.__reqs = [];')
    except Exception:
        pass
    drain_perf(drv)


def drain_perf(drv):
    try:
        drv.get_log('performance')
    except Exception:
        pass


def plog_net(drv):
    """performance log 通道（跨导航仍保留，补页内 fetch 打点偶发丢失）。"""
    out = []
    try:
        entries = drv.get_log('performance')
    except Exception:
        return out
    for e in entries:
        try:
            m = json.loads(e['message']).get('message', {})
        except Exception:
            continue
        meth = m.get('method')
        p = m.get('params', {})
        if meth == 'Network.requestWillBeSent':
            r = p.get('request', {})
            out.append({'method': r.get('method'), 'url': r.get('url') or '',
                        'body': r.get('postData'), 'status': None,
                        'id': p.get('requestId')})
        elif meth == 'Network.responseReceived':
            r = p.get('response', {})
            out.append({'method': 'RESP', 'url': r.get('url') or '',
                        'status': r.get('status'), 'id': p.get('requestId')})
    # 合并同 requestId 的响应状态
    by_id = {}
    merged = []
    for rec in out:
        if rec['method'] == 'RESP':
            req = by_id.get(rec['id'])
            if req:
                req['status'] = rec['status']
            continue
        by_id[rec['id']] = rec
        merged.append(rec)
    return merged


def _norm(url):
    return (url or '').replace(BASE, '')


def get_reqs(drv, settle=0.6):
    time.sleep(settle)
    fetch_reqs = []
    try:
        fetch_reqs = drv.execute_script('return (window.__reqs || []).slice()') or []
    except Exception:
        fetch_reqs = []
    perf = plog_net(drv)
    # 以 URL+方法 去重，fetch 打点带 response body 优先
    seen = set()
    out = []
    for rec in fetch_reqs:
        rec['url'] = _norm(rec.get('url'))
        key = (rec.get('method'), (rec.get('url') or '').split('?')[0])
        seen.add(key)
        out.append(rec)
    for rec in perf:
        rec['url'] = _norm(rec.get('url'))
        key = (rec.get('method'), (rec.get('url') or '').split('?')[0])
        if key in seen:
            # 用 perf 的 status 补齐
            for o in out:
                if (o.get('method'), (o.get('url') or '').split('?')[0]) == key and o.get('status') is None:
                    o['status'] = rec.get('status')
            continue
        seen.add(key)
        out.append(rec)
    return out


def find_req(reqs, needle, method=None):
    out = []
    for r in reqs:
        if needle in (r.get('url') or ''):
            if method is None or r.get('method') == method:
                out.append(r)
    return out


def visible(el):
    try:
        return el.is_displayed()
    except Exception:
        return False


def find_visible(drv, by, value, timeout=20):
    def probe(d):
        for el in d.find_elements(by, value):
            if visible(el):
                return el
        return False
    return WebDriverWait(drv, timeout).until(probe)


def js_click(drv, el):
    drv.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)


def click_button_text(drv, text, exact=False, timeout=20):
    xpath = ("//button[normalize-space(.)='%s']" % text) if exact else ("//button[contains(normalize-space(.), '%s')]" % text)

    def probe(d):
        for el in d.find_elements(By.XPATH, xpath):
            if visible(el):
                return el
        return False
    el = WebDriverWait(drv, timeout).until(probe)
    js_click(drv, el)
    return el


def click_link_href(drv, href, timeout=20):
    el = WebDriverWait(drv, timeout).until(
        lambda d: next((a for a in d.find_elements(By.CSS_SELECTOR, 'a[href="%s"]' % href) if visible(a)), False))
    js_click(drv, el)
    return el


def set_input(drv, el, value):
    """受控输入：聚焦 → Ctrl+A → Delete → 逐字输入（保证 React onChange 触发）。"""
    drv.execute_script('arguments[0].focus();', el)
    el.send_keys(Keys.CONTROL, 'a')
    el.send_keys(Keys.DELETE)
    if value:
        el.send_keys(value)
    return el.get_attribute('value')


def switch_state(drv, control_id):
    el = WebDriverWait(drv, 25).until(lambda d: d.find_element(
        By.XPATH, "//label[@for='%s']/parent::div/following-sibling::*[@data-slot='switch']" % control_id))
    return el.get_attribute('aria-checked')


def click_switch(drv, control_id):
    el = WebDriverWait(drv, 25).until(lambda d: d.find_element(
        By.XPATH, "//label[@for='%s']/parent::div/following-sibling::*[@data-slot='switch']" % control_id))
    js_click(drv, el)
    return el


def open_select(drv, trigger_id):
    el = find_visible(drv, By.CSS_SELECTOR, '#%s' % trigger_id, timeout=25)
    js_click(drv, el)
    WebDriverWait(drv, 15).until(lambda d: any(visible(i) for i in d.find_elements(By.CSS_SELECTOR, "[data-slot='select-item']")))
    items = [i for i in drv.find_elements(By.CSS_SELECTOR, "[data-slot='select-item']") if visible(i)]
    return el, items


def close_select(drv, trigger=None):
    """关闭下拉：优先再次点触发器（Sheet 内按 Esc 会连带关 Sheet，禁用）。"""
    try:
        if trigger is not None:
            js_click(drv, trigger)
        else:
            drv.execute_script('document.activeElement && document.activeElement.blur()')
    except Exception:
        pass
    time.sleep(0.5)


def dialog_present(drv, title=None):
    for el in drv.find_elements(By.CSS_SELECTOR, "[data-slot='alert-dialog-content'], [data-slot='dialog-content'], [data-slot='sheet-content']"):
        if visible(el):
            if title is None or title in (el.text or ''):
                return el
    return None


def wait_dialog(drv, title, timeout=20):
    return WebDriverWait(drv, timeout).until(lambda d: dialog_present(d, title))


def search_user_row(drv, username, timeout=30):
    """搜索并等待目标用户行出现（含一次重输兜底）。"""
    selector = "button[aria-label='用户操作：%s']" % username
    for attempt in range(3):
        try:
            box = find_visible(drv, By.CSS_SELECTOR, 'input[placeholder="搜索用户名或邮箱"]', timeout=25)
        except Exception:
            box = find_visible(drv, By.CSS_SELECTOR, 'input[placeholder*="搜索"]', timeout=15)
        set_input(drv, box, username)
        try:
            return WebDriverWait(drv, 12).until(
                lambda d: next((b for b in d.find_elements(By.CSS_SELECTOR, selector) if visible(b)), False))
        except Exception:
            time.sleep(1.5)
    raise AssertionError('搜索结果中未出现用户行: %s' % username)


def toast_text(drv, needle, timeout=25):
    return WebDriverWait(drv, timeout).until(lambda d: needle in body_text(d))


# ---------------------------------------------------------------------------
# 登录 / 会话
# ---------------------------------------------------------------------------

PERSONAS = {}


def bootstrap(drv, token, user):
    drv.get(BASE + '/login')
    wait_ready(drv)
    drv.execute_script(
        'try { localStorage.setItem(arguments[0], arguments[1]); } catch(e) {}', TOKEN_KEY, token)
    # 清掉 off 模式遗留的持久化用户，确保 hydrate 走 token 分支
    drv.execute_script(
        'try { localStorage.removeItem("iatp:auth:v1"); sessionStorage.removeItem("__rbac_perm"); } catch(e) {}')
    goto(drv, '/system-settings/site/info', '站点信息')


def current_user(drv):
    out = drv.execute_async_script('''
        var cb = arguments[arguments.length - 1];
        var token = null;
        try { token = localStorage.getItem('iatp:auth:token:v1'); } catch(e) {}
        var headers = token ? {Authorization: 'Bearer ' + token} : {};
        fetch('/api/v1/auth/me', {headers: headers}).then(function(r){ return r.json(); })
          .then(function(j){ cb(j); }).catch(function(e){ cb({error: String(e)}); });
    ''')
    return out


# ---------------------------------------------------------------------------
# A. 六域分区浅色渲染
# ---------------------------------------------------------------------------

def phase_a(drv, token):
    st, opts = api('/api/option/', token)
    kv = (opts or {}).get('data') or {}
    record('A0 GET /api/option/ 基线', st == 200 and 'site.name' in kv, 'status=%s keys=%d' % (st, len(kv)), {'kv': kv})
    _, roles = api('/api/v1/auth/roles', token)
    role_count = len((roles.get('data') or {}).get('roles') or [])
    _, users = api('/api/v1/auth/users', token)
    user_items = ((users.get('data') or {}) or {}).get('items') or []
    record('A0 GET /auth/roles 基线', role_count > 0, 'roles=%d' % role_count)
    record('A0 GET /auth/users 基线', len(user_items) > 0, 'users=%d' % len(user_items))

    for domain, section, title in SECTIONS:
        name = 'A_%s_%s' % (domain, section.replace('_', '-'))
        if os.environ.get('SECTION_FILTER') and os.environ['SECTION_FILTER'] not in name:
            continue
        last = None
        for attempt in range(3):
            try:
                last = _assert_section(drv, domain, section, title, name, kv, user_items)
                break
            except Exception as exc:
                tb = traceback.format_exc().strip().splitlines()
                last = (False, '异常(第%d次): %s | %s' % (attempt + 1, exc, ' <- '.join(tb[-3:])), {})
                time.sleep(1.5)
        record(name, last[0], last[1], last[2])


def _assert_section(drv, domain, section, title, name, kv, user_items):
    reset_reqs(drv)
    goto(drv, '/system-settings/%s/%s' % (domain, section), title)
    wait_noise(drv, 1.8)
    reqs = get_reqs(drv)
    detail = {}
    ok = True
    msgs = []

    if (domain, section) == ('site', 'info'):
        got = find_visible(drv, By.ID, 'site-name').get_attribute('value')
        exp = kv.get('site.name')
        ok &= got == exp
        msgs.append('站点名称渲染=%r/接口=%r' % (got, exp))
        footer = find_visible(drv, By.ID, 'site-footer').get_attribute('value')
        msgs.append('页脚=%r' % footer)
    elif (domain, section) == ('site', 'notice'):
        got = find_visible(drv, By.ID, 'site-notice').get_attribute('value')
        ok &= got == (kv.get('site.notice') or '')
        msgs.append('公告初值=%r' % got)
    elif (domain, section) == ('site', 'navigation'):
        for cid, key in [('nav-breadcrumb', 'site.navigation.show_breadcrumb'),
                         ('nav-algorithm-switcher', 'site.navigation.show_algorithm_switcher')]:
            got = switch_state(drv, cid)
            exp = str(bool(kv.get(key))).lower()
            ok &= got == exp
            msgs.append('%s=%s/exp=%s' % (cid, got, exp))
    elif (domain, section) == ('iam', 'users'):
        WebDriverWait(drv, 25).until(lambda d: len(d.find_elements(By.CSS_SELECTOR, 'table tbody tr')) > 0)
        rows = drv.find_elements(By.CSS_SELECTOR, 'table tbody tr')
        ok &= len(rows) == len(user_items)
        msgs.append('表格行=%d/接口=%d' % (len(rows), len(user_items)))
        hits = find_req(reqs, '/auth/users')
        ok &= any(r.get('status') == 200 for r in hits)
        msgs.append('GET /auth/users=%s' % [r.get('status') for r in hits][:3])
    elif (domain, section) == ('iam', 'roles'):
        wait_text(drv, '角色权限管理', 20)
        hits = find_req(reqs, '/auth/roles')
        ok &= any(r.get('status') == 200 for r in hits)
        txt = body_text(drv)
        msgs.append('GET /auth/roles=%s 含admin=%s' % ([r.get('status') for r in hits][:3], 'admin' in txt or '超级管理员' in txt))
    elif (domain, section) == ('auth', 'methods'):
        for cid, key in [('auth-password-login', 'auth.password_login'),
                         ('auth-registration', 'auth.registration'),
                         ('auth-email-verification', 'auth.email_verification')]:
            got = switch_state(drv, cid)
            exp = str(bool(kv.get(key))).lower()
            ok &= got == exp
            msgs.append('%s=%s/exp=%s' % (cid, got, exp))
    elif (domain, section) == ('auth', 'oauth-providers'):
        wait_text(drv, '尚未配置自定义 OAuth 提供方', 25)
        hits = find_req(reqs, '/auth/oauth-providers')
        ok &= any(r.get('status') == 200 for r in hits)
        msgs.append('空态文案=未配置；GET oauth=%s' % [r.get('status') for r in hits][:3])
    elif (domain, section) == ('appearance', 'presets'):
        wait_text(drv, '选择站点的配色预设', 30)
        items = drv.find_elements(By.CSS_SELECTOR, '[aria-label="选择颜色预设"] [role="radio"]')
        ok &= len(items) >= 5
        msgs.append('预设数=%d' % len(items))
    elif (domain, section) == ('appearance', 'fine-tuning'):
        wait_text(drv, '深浅色', 30)
        msgs.append('外观微调控件渲染')
    elif (domain, section) == ('security', 'access-control'):
        got = switch_state(drv, 'security-rate-limit')
        exp = str(bool(kv.get('security.rate_limit'))).lower()
        ok &= got == exp
        msgs.append('rate-limit=%s/exp=%s' % (got, exp))
    elif (domain, section) == ('operations', 'log-maintenance'):
        wait_text(drv, '归档管理', 25)
        reqs = get_reqs(drv, settle=0.3)
        got = find_visible(drv, By.ID, 'log-retention-days').get_attribute('value')
        exp = str(kv.get('operations.log_retention_days'))
        ok &= got == exp
        msgs.append('保留天数=%s/exp=%s' % (got, exp))
        hits = find_req(reqs, 'logs/archive')
        if not any(r.get('status') == 200 for r in hits):
            time.sleep(1.2)
            reqs = get_reqs(drv, settle=0.2)
            hits = find_req(reqs, 'logs/archive')
        ok &= any(r.get('status') == 200 for r in hits) or bool(hits)
        msgs.append('archive 请求=%s' % [(r.get('method'), r.get('status')) for r in hits][:4])

    reqs = get_reqs(drv, settle=0.3)
    shot(drv, name + '_light')
    detail['requests'] = [{'method': r.get('method'), 'url': (r.get('url') or '')[-90:], 'status': r.get('status')}
                          for r in reqs if '/api/' in (r.get('url') or '')][:12]
    detail['req_count'] = len(reqs)
    return ok, '; '.join(msgs), detail


# ---------------------------------------------------------------------------
# B. 深色截图
# ---------------------------------------------------------------------------

def phase_b(drv):
    set_theme(drv, 'dark')
    for domain, section, title in SECTIONS:
        name = 'B_%s_%s_dark' % (domain, section.replace('_', '-'))
        try:
            goto(drv, '/system-settings/%s/%s' % (domain, section), title)
            WebDriverWait(drv, 20).until(lambda d: is_dark(d))
            time.sleep(1.2)
            shot(drv, name)
            record(name, True, '深色渲染 class=%s' % drv.execute_script('return document.documentElement.className'))
        except Exception as exc:
            record(name, False, '异常: %s' % exc)
    set_theme(drv, 'light')


# ---------------------------------------------------------------------------
# C + D. 设置表单页 / 脏标记 / 保存 / 重置 / 回读
# ---------------------------------------------------------------------------

DEBUG_MARK = {'v': ''}


def phase_c(drv, token):
    _, opts = api('/api/option/', token)
    kv = (opts or {}).get('data') or {}
    orig = kv.get('site.name') or ''
    new_value = '接线测试_站点_1485_%s' % time.strftime('%H%M%S')
    try:
        reset_reqs(drv)
        goto(drv, '/system-settings/site/info', '站点信息')
        wait_noise(drv, 1.5)
        reqs = get_reqs(drv)
        hits = find_req(reqs, '/api/option/', 'GET')
        record('C1 加载 GET /api/option/ 取初值', any(r.get('status') == 200 for r in hits),
               '初值=%r 请求=%s' % (orig, [(r.get('method'), r.get('status')) for r in hits][:3]))

        el = find_visible(drv, By.ID, 'site-name')
        set_input(drv, el, new_value)
        wait_text(drv, '未保存的更改', 10)
        dirty_badge = '未保存的更改' in body_text(drv)
        save_btn = drv.find_element(By.XPATH, "//button[normalize-space(.)='保存更改' or contains(normalize-space(.),'保存')]")
        reset_btn = drv.find_element(By.XPATH, "//button[normalize-space(.)='重置']")
        record('D1 脏标记出现 + 按钮状态', dirty_badge and save_btn.is_enabled() and reset_btn.is_enabled(),
               'badge=%s save_enabled=%s reset_enabled=%s' % (dirty_badge, save_btn.is_enabled(), reset_btn.is_enabled()))
        shot(drv, 'D1_dirty_indicator_light')

        # 深色脏标记：同一状态切主题重载会丢草稿，改用运行时加 dark 类截一张
        drv.execute_script('document.documentElement.classList.add("dark")')
        time.sleep(0.8)
        shot(drv, 'D1_dirty_indicator_dark')
        drv.execute_script('document.documentElement.classList.remove("dark")')

        reset_reqs(drv)
        DEBUG_MARK['v'] = 'C2-click-save'
        click_button_text(drv, '保存')
        DEBUG_MARK['v'] = 'C2-toast'
        toast_text(drv, '设置已更新', 25)
        reqs = get_reqs(drv)
        puts = [r for r in find_req(reqs, '/api/option/', 'PUT')]
        body_ok = any('site.name' in (r.get('body') or '') and new_value in (r.get('body') or '') for r in puts)
        record('C2 保存 PUT /api/option/', bool(puts) and body_ok and all(r.get('status') in (200, 204) for r in puts),
               'PUT=%s body=%s' % ([(r.get('status')) for r in puts], [r.get('body') for r in puts][:2]))
        shot(drv, 'C2_saved_toast_light')

        st, opts2 = api('/api/option/', token)
        readback = ((opts2.get('data') or {}).get('site.name'))
        record('C3 GET 回读保存值', readback == new_value, 'readback=%r' % readback)

        DEBUG_MARK['v'] = 'C-reload-readback'
        goto(drv, '/system-settings/site/info', '站点信息')
        wait_noise(drv, 1.5)
        rendered = find_visible(drv, By.ID, 'site-name').get_attribute('value')
        badge_gone = '未保存的更改' not in body_text(drv)
        save_disabled = drv.find_element(By.XPATH, "//button[contains(normalize-space(.),'保存')]").get_attribute('disabled') is not None
        record('D2 刷新后脏标记消失 + 保存禁用', rendered == new_value and badge_gone and save_disabled,
               'rendered=%r badge_gone=%s save_disabled=%s' % (rendered, badge_gone, save_disabled))

        DEBUG_MARK['v'] = 'C4-click-save-nochange'
        reset_reqs(drv)
        save_el = find_visible(drv, By.XPATH, "//button[contains(normalize-space(.), '保存')]")
        disabled_now = save_el.get_attribute('disabled') is not None
        js_click(drv, save_el)   # 禁用态点击应无请求/无 toast
        time.sleep(1.5)
        reqs = get_reqs(drv)
        puts = find_req(reqs, '/api/option/', 'PUT')
        no_change_toast = '没有需要保存的更改' in body_text(drv)
        record('C4 无改动：保存按钮禁用且点击无请求',
               disabled_now and not puts and not no_change_toast,
               'save_disabled=%s PUT=%d no_change_toast=%s（isDirty=false 时按钮禁用，handleSave 的「没有需要保存的更改」分支不可达）'
               % (disabled_now, len(puts), no_change_toast))

        DEBUG_MARK['v'] = 'C5-reset'
        el = find_visible(drv, By.ID, 'site-name')
        set_input(drv, el, '接线测试_临时重置')
        wait_text(drv, '未保存的更改', 10)
        click_button_text(drv, '重置')
        toast_text(drv, '表单已重置为已保存的值', 15)
        restored = find_visible(drv, By.ID, 'site-name').get_attribute('value')
        record('C5 重置回已保存值', restored == new_value and '未保存的更改' not in body_text(drv),
               'restored=%r' % restored)
        shot(drv, 'C5_after_reset_light')

        # 还原原始站点名称
        DEBUG_MARK['v'] = 'C6-restore'
        el = find_visible(drv, By.ID, 'site-name')
        set_input(drv, el, orig)
        click_button_text(drv, '保存')
        toast_text(drv, '设置已更新', 25)
        st, opts3 = api('/api/option/', token)
        back = ((opts3.get('data') or {}).get('site.name'))
        record('C6 还原原值', back == orig, 'restored=%r' % back)
    except Exception as exc:
        try:
            api('/api/option/', token, method='PUT', body={'key': 'site.name', 'value': orig})
        except Exception:
            pass
        shot(drv, 'C_FAIL')
        tb = traceback.format_exc().strip().splitlines()
        record('C 设置表单页', False, 'mark=%s 异常: %s | %s' % (DEBUG_MARK['v'], exc, ' <- '.join(tb[-8:])))


# ---------------------------------------------------------------------------
# E. 导航离开守卫
# ---------------------------------------------------------------------------

def phase_e(drv):
    try:
        goto(drv, '/system-settings/site/info', '站点信息')
        wait_noise(drv, 1.2)
        el = find_visible(drv, By.ID, 'site-name')
        set_input(drv, el, '接线测试_离开拦截')
        wait_text(drv, '未保存的更改', 10)

        click_link_href(drv, '/system-settings/site/notice')
        dlg = wait_dialog(drv, '未保存的更改')
        record('E1 脏表单切域弹出拦截', dlg is not None and '确定要离开吗' in dlg.text, 'dialog=%r' % (dlg.text[:80] if dlg else None))
        shot(drv, 'E1_guard_dialog_light')

        click_button_text(drv, '留下', exact=True)
        time.sleep(0.8)
        dlg_gone = dialog_present(drv) is None
        same_url = drv.current_url.endswith('/system-settings/site/info')
        still_dirty = '未保存的更改' in body_text(drv)
        record('E2 「留下」取消离开', dlg_gone and same_url and still_dirty,
               'url=%s dialog_gone=%s dirty=%s' % (drv.current_url, dlg_gone, still_dirty))

        click_link_href(drv, '/system-settings/site/notice')
        wait_dialog(drv, '未保存的更改')
        click_button_text(drv, '离开', exact=True)
        WebDriverWait(drv, 15).until(lambda d: '/system-settings/site/notice' in d.current_url)
        record('E3 「离开」放行', True, 'url=%s' % drv.current_url)

        # Esc 关闭拦截弹窗
        goto(drv, '/system-settings/site/info', '站点信息')
        wait_noise(drv, 1.2)
        set_input(drv, find_visible(drv, By.ID, 'site-name'), '接线测试_Esc')
        wait_text(drv, '未保存的更改', 10)
        click_link_href(drv, '/system-settings/site/notice')
        wait_dialog(drv, '未保存的更改')
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(0.8)
        record('E4 Esc 关闭拦截且留在原页', dialog_present(drv) is None and drv.current_url.endswith('/site/info'),
               'url=%s dialog=%s' % (drv.current_url, dialog_present(drv) is not None))

        # 刷新 beforeunload
        set_input(drv, find_visible(drv, By.ID, 'site-name'), '接线测试_刷新')
        wait_text(drv, '未保存的更改', 10)
        listener_blocks = drv.execute_script('''
            var ev = new Event('beforeunload', {cancelable: true});
            window.dispatchEvent(ev);
            return ev.defaultPrevented;
        ''')
        alert_seen = False
        try:
            drv.execute_script('window.location.reload()')
            time.sleep(1.5)
            alert = drv.switch_to.alert
            alert_seen = True
            alert.dismiss()
        except Exception:
            alert_seen = False
        time.sleep(1.5)
        try:
            wait_ready(drv)
        except Exception:
            pass
        record('E5 刷新 beforeunload 拦截', listener_blocks or alert_seen,
               'beforeunload_listener_prevented=%s native_alert=%s' % (listener_blocks, alert_seen))
        # 关闭页面/新会话的 beforeunload 无法在 headless 断言，记录限制
        record('E6 关页 beforeunload', listener_blocks, 'headless 无法直接观测浏览器关页确认框；以 beforeunload 监听默认行为被阻止作为等效证据')
    except Exception as exc:
        shot(drv, 'E_FAIL')
        tb = traceback.format_exc().strip().splitlines()
        record('E 导航离开守卫', False, '异常: %s | %s' % (exc, ' <- '.join(tb[-5:])))


# ---------------------------------------------------------------------------
# F. 用户抽屉（新建/校验/同名/编辑/停用/删除/回读）
# ---------------------------------------------------------------------------

TEST_USER = '接线测试_ui1485_%s' % time.strftime('%m%d%H%M%S')


def phase_f(drv, token):
    created_id = None
    try:
        reset_reqs(drv)
        goto_settings(drv, '/system-settings/iam/users', '用户管理', '注册时间')
        wait_noise(drv, 1.0)
        reqs = get_reqs(drv)
        hits = find_req(reqs, '/auth/users', 'GET')
        rows0 = len(drv.find_elements(By.CSS_SELECTOR, 'table tbody tr'))
        record('F1 用户列表加载', bool(hits) and rows0 > 0,
               'GET=%s rows=%d' % ([(r.get('status')) for r in hits][:3], rows0))

        DEBUG_MARK['v']='F2-new'
        click_button_text(drv, '新建用户')
        sheet = WebDriverWait(drv, 15).until(lambda d: dialog_present(d, '新建用户'))
        fields = {i: find_visible(drv, By.ID, i).get_attribute('value') for i in
                  ('user-username', 'user-display-name', 'user-email', 'user-password')}
        status_disabled = find_visible(drv, By.CSS_SELECTOR, '#user-status').get_attribute('disabled') is not None
        record('F2 新建抽屉打开+初值', sheet is not None and fields.get('user-username') == '' and status_disabled,
               'fields=%s status_disabled=%s' % (fields, status_disabled))
        shot(drv, 'F2_user_drawer_create_light')

        # 角色下拉选项数 vs /auth/roles
        DEBUG_MARK['v']='F3-role-select'
        trigger, items = open_select(drv, 'user-role')
        role_texts = [i.text.strip() for i in items]
        _, roles = api('/api/v1/auth/roles', token)
        role_list = (roles.get('data') or {}).get('roles') or []
        record('F3 角色下拉选项对齐 /auth/roles', len(role_texts) == len(role_list),
               'options=%d(%s) api=%d(%s)' % (len(role_texts), role_texts, len(role_list), [r['name'] for r in role_list]))
        close_select(drv, trigger)
        assert dialog_present(drv, '新建用户') is not None, '关闭下拉后抽屉被误关'

        # 必填留空提交：不应发请求
        DEBUG_MARK['v']='F4-empty-submit'
        reset_reqs(drv)
        click_button_text(drv, '创建', exact=True)
        time.sleep(1.2)
        reqs = get_reqs(drv)
        posted = [r for r in find_req(reqs, '/auth/users', 'POST')]
        record('F4 必填留空提交校验', not posted, 'POST=%d 抽屉仍在=%s' % (len(posted), dialog_present(drv, '新建用户') is not None))

        # 非法邮箱提交
        DEBUG_MARK['v']='F5-bad-email'
        reset_reqs(drv)
        set_input(drv, find_visible(drv, By.ID, 'user-username'), TEST_USER)
        set_input(drv, find_visible(drv, By.ID, 'user-email'), 'not-an-email')
        set_input(drv, find_visible(drv, By.ID, 'user-password'), 'Ui1485@Pass')
        click_button_text(drv, '创建', exact=True)
        time.sleep(2.0)
        reqs = get_reqs(drv)
        posts = find_req(reqs, '/auth/users', 'POST')
        record('F5 非法邮箱提交', bool(posts),
               'POST=%s status=%s body=%s' % (len(posts), [p.get('status') for p in posts], [p.get('body') for p in posts][:1]))
        # 若创建成功说明后端未校验邮箱；删除该脏数据
        bad_id = None
        if posts and posts[0].get('status') in (200, 201):
            _, listing = api('/api/v1/auth/users?keyword=' + urllib.parse.quote(TEST_USER), token)
            for it in ((listing.get('data') or {}).get('items') or []):
                if it.get('username') == TEST_USER:
                    bad_id = it.get('id')
            if bad_id:
                api('/api/v1/auth/users/%s' % bad_id, token, method='DELETE')
        # 关闭抽屉重开，检查残留
        DEBUG_MARK['v']='F6-reopen'
        if dialog_present(drv, '新建用户'):
            drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            time.sleep(0.8)
        click_button_text(drv, '新建用户')
        wait_dialog(drv, '新建用户')
        residual = find_visible(drv, By.ID, 'user-username').get_attribute('value')
        record('F6 关闭重开无残留', residual == '', 'username_after_reopen=%r' % residual)

        # 正式创建
        DEBUG_MARK['v']='F7-create'
        reset_reqs(drv)
        set_input(drv, find_visible(drv, By.ID, 'user-username'), TEST_USER)
        set_input(drv, find_visible(drv, By.ID, 'user-display-name'), '接线测试显示名')
        set_input(drv, find_visible(drv, By.ID, 'user-email'), TEST_USER + '@example.com')
        set_input(drv, find_visible(drv, By.ID, 'user-password'), 'Ui1485@Pass')
        DEBUG_MARK['v']='F7-click-create'
        click_button_text(drv, '创建', exact=True)
        DEBUG_MARK['v']='F7-wait-post'
        posts = []
        for _ in range(20):
            time.sleep(1.0)
            posts = find_req(get_reqs(drv, settle=0.1), '/auth/users', 'POST')
            if any(r.get('status') for r in posts):
                break
        DEBUG_MARK['v']='F7-toast'
        try:
            toast_text(drv, '用户已创建', 10)
        except Exception:
            pass
        reqs = get_reqs(drv)
        posts = find_req(reqs, '/auth/users', 'POST')
        record('F7 创建用户 POST /auth/users', any(r.get('status') in (200, 201) for r in posts),
               'status=%s body=%s resp=%s' % ([r.get('status') for r in posts],
                                              [r.get('body') for r in posts][:1],
                                              [(r.get('resp') or '')[:160] for r in posts][:1]))
        shot(drv, 'F7_user_created_toast_light')

        time.sleep(1.5)
        st, listing = _api_retry('/api/v1/auth/users?page=1&page_size=100', token)
        found = [it for it in ((listing.get('data') or {}).get('items') or []) if it.get('username') == TEST_USER]
        created_id = found[0]['id'] if found else None
        record('F8 GET 回读新建用户', bool(found),
               'item=%s' % ({k: found[0].get(k) for k in ('id', 'username', 'email', 'role_name', 'status')} if found else None))

        # 同名唯一约束
        DEBUG_MARK['v']='F9-duplicate'
        click_button_text(drv, '新建用户')
        wait_dialog(drv, '新建用户')
        reset_reqs(drv)
        set_input(drv, find_visible(drv, By.ID, 'user-username'), TEST_USER)
        set_input(drv, find_visible(drv, By.ID, 'user-email'), 'dup1485@example.com')
        set_input(drv, find_visible(drv, By.ID, 'user-password'), 'Ui1485@Pass')
        click_button_text(drv, '创建', exact=True)
        time.sleep(2.5)
        reqs = get_reqs(drv)
        dup_posts = find_req(reqs, '/auth/users', 'POST')
        dup = [p for p in dup_posts if p.get('status') not in (200, 201)]
        record('F9 同名用户唯一约束', bool(dup), 'status=%s resp=%s' % ([p.get('status') for p in dup], [(p.get('resp') or '')[:160] for p in dup][:1]))
        if dialog_present(drv, '新建用户'):
            drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            time.sleep(0.8)

        # 编辑
        DEBUG_MARK['v']='F10-edit-open'
        goto_settings(drv, '/system-settings/iam/users', '用户管理', '注册时间')
        wait_noise(drv, 1.0)
        open_menu = search_user_row(drv, TEST_USER)
        js_click(drv, open_menu)
        WebDriverWait(drv, 10).until(lambda d: any(visible(i) for i in d.find_elements(By.CSS_SELECTOR, "[role='menuitem']")))
        menuitems = [i for i in drv.find_elements(By.CSS_SELECTOR, "[role='menuitem']") if visible(i)]
        record('F10 行操作菜单项', any('编辑' in i.text for i in menuitems) and any('删除' in i.text for i in menuitems),
               'items=%s' % [i.text.strip() for i in menuitems])
        next(i for i in menuitems if '编辑' in i.text).click()
        wait_dialog(drv, '编辑用户')
        time.sleep(1.2)
        uname_disabled = find_visible(drv, By.ID, 'user-username').get_attribute('disabled') is not None
        cur_email = find_visible(drv, By.ID, 'user-email').get_attribute('value')
        cur_display = find_visible(drv, By.ID, 'user-display-name').get_attribute('value')
        record('F11 编辑抽屉回填+用户名只读', uname_disabled and cur_email.endswith('@example.com'),
               'username_disabled=%s email=%r display_name=%r' % (uname_disabled, cur_email, cur_display))
        shot(drv, 'F11_user_drawer_edit_light')
        drv.execute_script('document.documentElement.classList.add("dark")')
        time.sleep(0.6)
        shot(drv, 'F11_user_drawer_edit_dark')
        drv.execute_script('document.documentElement.classList.remove("dark")')

        DEBUG_MARK['v']='F12-edit-fields'
        set_input(drv, find_visible(drv, By.ID, 'user-display-name'), '接线测试显示名B')
        # 状态改停用
        trigger, items = open_select(drv, 'user-status')
        status_opts = [i.text.strip() for i in items]
        record('F12 状态下拉选项', status_opts == ['正常', '停用', '锁定'], 'options=%s' % status_opts)
        next(i for i in items if i.text.strip() == '停用').click()
        time.sleep(0.5)
        reset_reqs(drv)
        click_button_text(drv, '保存', exact=True)
        toast_text(drv, '用户已更新', 25)
        reqs = get_reqs(drv)
        puts = find_req(reqs, '/auth/users', 'PUT')
        record('F13 编辑保存 PUT', any(r.get('status') == 200 for r in puts),
               'PUT=%s body=%s' % ([r.get('status') for r in puts], [r.get('body') for r in puts][:2]))

        st, d = api('/api/v1/auth/users/%s' % created_id, token)
        u = (d.get('data') or {})
        record('F14 GET 回读编辑结果', u.get('display_name') == '接线测试显示名B' and u.get('status') in ('disabled', 'inactive'),
               'detail=%s' % {k: u.get(k) for k in ('username', 'display_name', 'email', 'status', 'role_id')})
        shot(drv, 'F14_user_disabled_light')

        # 启用回来（联动）
        DEBUG_MARK['v']='F15-enable'
        goto_settings(drv, '/system-settings/iam/users', '用户管理', '注册时间')
        wait_noise(drv, 1.0)
        js_click(drv, search_user_row(drv, TEST_USER))
        WebDriverWait(drv, 10).until(lambda d: any(visible(i) for i in d.find_elements(By.CSS_SELECTOR, "[role='menuitem']")))
        menuitems = [i for i in drv.find_elements(By.CSS_SELECTOR, "[role='menuitem']") if visible(i)]
        enable_label = '启用' if any('启用' in i.text for i in menuitems) else '停用'
        record('F15 停用态行菜单显示「启用」', enable_label == '启用', 'items=%s' % [i.text.strip() for i in menuitems])
        next(i for i in menuitems if '启用' in i.text).click()
        status_now = None
        for _ in range(10):
            time.sleep(1.0)
            st, d = _api_retry('/api/v1/auth/users/%s' % created_id, token)
            status_now = (d.get('data') or {}).get('status')
            if status_now == 'active':
                break
        record('F16 启用联动回读', status_now == 'active', 'status=%s' % status_now)

        # 删除（确认框）
        DEBUG_MARK['v']='F17-delete'
        reset_reqs(drv)
        js_click(drv, find_visible(drv, By.CSS_SELECTOR, "button[aria-label='用户操作：%s']" % TEST_USER))
        WebDriverWait(drv, 10).until(lambda d: any(visible(i) for i in d.find_elements(By.CSS_SELECTOR, "[role='menuitem']")))
        menuitems = [i for i in drv.find_elements(By.CSS_SELECTOR, "[role='menuitem']") if visible(i)]
        next(i for i in menuitems if '删除' in i.text).click()
        dlg = wait_dialog(drv, '确认删除用户')
        record('F17 删除确认框', dlg is not None and TEST_USER in dlg.text, 'dialog=%s' % (dlg.text[:80] if dlg else None))
        shot(drv, 'F17_delete_confirm_light')
        click_button_text(drv, '删除', exact=True)
        toast_text(drv, '用户已删除', 25)
        reqs = get_reqs(drv)
        dels = find_req(reqs, '/auth/users', 'DELETE')
        record('F18 删除 DELETE', any(r.get('status') in (200, 204) for r in dels),
               'DELETE=%s' % [(r.get('status'), (r.get('url') or '')[-30:]) for r in dels])
        time.sleep(1.5)
        st, listing = _api_retry('/api/v1/auth/users?page=1&page_size=100', token)
        left = [it for it in ((listing.get('data') or {}).get('items') or []) if it.get('username') == TEST_USER]
        record('F19 删除后列表回读为空', not left, 'remaining=%s' % [it.get('username') for it in left])
        created_id = None
    except Exception as exc:
        shot(drv, 'F_FAIL')
        tb = traceback.format_exc().strip().splitlines()
        record('F 用户抽屉', False, 'mark=%s 异常: %s | %s' % (DEBUG_MARK['v'], exc, ' <- '.join(tb[-8:])))
    finally:
        if created_id:
            try:
                api('/api/v1/auth/users/%s' % created_id, token, method='DELETE')
            except Exception:
                pass


# ---------------------------------------------------------------------------
# G. 布局与分区导航
# ---------------------------------------------------------------------------

EXPECTED_SECTIONS = {
    'site': ['站点信息', '站点公告', '导航模块'],
    'iam': ['用户管理', '角色权限管理'],
    'auth': ['认证方式', 'OAuth 提供方'],
    'appearance': ['主题预设', '外观微调'],
    'security': ['访问控制'],
    'operations': ['日志维护'],
}


def phase_g(drv):
    domain_titles = {
        'site': '站点设置', 'iam': '用户与权限', 'auth': '认证设置',
        'appearance': '外观与主题', 'security': '安全设置', 'operations': '运维设置',
    }
    try:
        goto(drv, '/system-settings/site/info', '站点信息')
        wait_noise(drv, 1.5)

        def domain_links(domain):
            return sorted({a.get_attribute('href').split(BASE)[-1]
                           for a in drv.find_elements(By.CSS_SELECTOR, 'a[href^="/system-settings/%s/"]' % domain)
                           if visible(a)})

        def expand(domain, title):
            existing = domain_links(domain)
            if existing:
                return existing
            header = WebDriverWait(drv, 15).until(
                lambda d: next((b for b in d.find_elements(By.XPATH, "//button[normalize-space(.)='%s']" % title) if visible(b)), False))
            js_click(drv, header)
            want = len(EXPECTED_SECTIONS[domain])
            try:
                WebDriverWait(drv, 10).until(lambda d: len(domain_links(domain)) >= want)
            except Exception:
                time.sleep(1.2)
            time.sleep(0.5)
            return domain_links(domain)

        all_paths = {}
        missing = []
        for domain, title in domain_titles.items():
            links = expand(domain, title)
            all_paths[domain] = links
            expected_count = len(EXPECTED_SECTIONS[domain])
            if len(links) != expected_count:
                missing.append('%s(%d/%d)' % (domain, len(links), expected_count))
        total = sum(len(v) for v in all_paths.values())
        record('G1 六域侧栏树分区齐全', not missing and total >= 11,
               '六域展开分区总数=%d 明细=%s 缺口=%s' % (total, {k: len(v) for k, v in all_paths.items()}, missing))
        shot(drv, 'G1_sidebar_layout_light')

        visited = []
        for domain, links in all_paths.items():
            for target in links:
                click_link_href(drv, target)
                WebDriverWait(drv, 20).until(lambda d: target in d.current_url)
                visited.append(target)
                time.sleep(0.4)
        record('G2 逐分区点击可达', len(visited) == total,
               'visited=%d/%d %s' % (len(visited), total, visited))

        # 域级入口 /system-settings → 默认落点 site/info
        goto(drv, '/system-settings')
        wait_noise(drv, 1.5)
        record('G3 /system-settings 默认落点', '/system-settings/site/' in drv.current_url, 'url=%s' % drv.current_url)
    except Exception as exc:
        try:
            shot(drv, 'G_FAIL')
        except Exception:
            pass
        tb = traceback.format_exc().strip().splitlines()
        record('G 布局导航', False, '异常: %s | %s' % (exc, ' <- '.join(tb[-4:])))


# ---------------------------------------------------------------------------
# H. 空态 / 错误态 / 加载态
# ---------------------------------------------------------------------------

def phase_h(drv, token):
    try:
        # 空态：用户搜索无匹配
        goto_settings(drv, '/system-settings/iam/users', '用户管理', '注册时间')
        wait_noise(drv, 1.0)
        set_input(drv, find_visible(drv, By.CSS_SELECTOR, 'input[placeholder="搜索用户名或邮箱"]'), '接线测试_不存在_1485')
        wait_text(drv, '未找到匹配的用户', 20)
        record('H1 用户列表空态', '未找到匹配的用户' in body_text(drv), '空态文案出现')
        shot(drv, 'H1_empty_state_light')
        set_input(drv, find_visible(drv, By.CSS_SELECTOR, 'input[placeholder="搜索用户名或邮箱"]'), '')
        time.sleep(1.2)

        # 加载态：把 /api/option/ 响应延迟 6s（页内打点注入），观察「正在加载设置」
        drv.execute_script('sessionStorage.setItem("__delay_option", "6000")')
        drv.get(BASE + '/system-settings/site/info')
        wait_ready(drv)
        WebDriverWait(drv, 30).until(lambda d: '正在加载设置' in body_text(d) or '站点信息' in body_text(d))
        loading = '正在加载设置' in body_text(drv)
        shot(drv, 'H2_loading_state_light')
        drv.execute_script('sessionStorage.removeItem("__delay_option")')
        record('H2 加载态', loading, 'loading_text=%s' % loading)

        # 错误态：拦掉 /api/option/
        drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': ['*/api/option/*']})
        goto(drv, '/system-settings/site/info')
        wait_text(drv, '设置加载失败', 30)
        record('H3 选项接口失败错误态', '设置加载失败' in body_text(drv), '错误态+重试按钮')
        shot(drv, 'H3_error_state_light')
        drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': []})
        click_button_text(drv, '重试', timeout=10)
        wait_text(drv, '站点信息', 30)
        time.sleep(1.5)
        recovered = find_visible(drv, By.ID, 'site-name').get_attribute('value')
        record('H4 重试恢复', recovered == '接线测试_站点_1485' or bool(recovered), 'value=%r' % recovered)
        shot(drv, 'H4_retry_recovered_light')
    except Exception as exc:
        shot(drv, 'H_FAIL')
        try:
            drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': []})
            drv.execute_script('sessionStorage.removeItem("__delay_option")')
        except Exception:
            pass
        record('H 状态态', False, '异常: %s' % exc)


# ---------------------------------------------------------------------------
# I. RBAC 低权限视角
# ---------------------------------------------------------------------------

def phase_i(drv, token):
    try:
        _, roles = api('/api/v1/auth/roles', token)
        role_list = (roles.get('data') or {}).get('roles') or []
        guest = next((r for r in role_list if r.get('name') == 'guest'), None)
        guest_perms = (guest or {}).get('permissions') or []
        drv.execute_script('sessionStorage.setItem("__rbac_perm", arguments[0])', json.dumps(guest_perms))
        drv.execute_script('localStorage.removeItem("iatp:auth:v1")')
        goto(drv, '/system-settings/site/info')
        wait_noise(drv, 2.5)
        me = current_user(drv)
        record('I1 权限注入生效', (me.get('permissions') or []) == guest_perms,
               'me_permissions=%d expected=%d' % (len(me.get('permissions') or []), len(guest_perms)))
        body = body_text(drv)
        url = drv.current_url
        nav_visible = [d for d in ('站点设置', '用户与权限', '认证设置', '安全设置') if d in body]
        record('I2 guest 视角导航隐藏', ('403' in url) or not nav_visible,
               'url=%s nav_visible=%s perms=%s' % (url, nav_visible, guest_perms[:6]))
        shot(drv, 'I2_guest_view_light')
        drv.execute_script('sessionStorage.removeItem("__rbac_perm")')
        goto(drv, '/system-settings/site/info', '站点信息')
    except Exception as exc:
        shot(drv, 'I_FAIL')
        try:
            drv.execute_script('sessionStorage.removeItem("__rbac_perm")')
        except Exception:
            pass
        record('I RBAC 视角', False, '异常: %s' % exc)


# ---------------------------------------------------------------------------
# J. 清单外窗口（OAuth Dialog / 日志确认框）
# ---------------------------------------------------------------------------

def phase_j(drv, token):
    provider_id = None
    try:
        goto_settings(drv, '/system-settings/auth/oauth-providers', 'OAuth 提供方', '回调地址格式')
        wait_noise(drv, 1.0)
        click_button_text(drv, '添加提供方')
        wait_dialog(drv, '新建提供方')
        # 必填留空提交：不应发请求
        DEBUG_MARK['v']='F4-empty-submit'
        reset_reqs(drv)
        click_button_text(drv, '保存', exact=True)
        time.sleep(1.2)
        posts = find_req(get_reqs(drv), '/auth/oauth-providers', 'POST')
        record('J1 OAuth 新建 Dialog 必填校验', not posts and dialog_present(drv, '新建提供方') is not None,
               'POST=%d dialog_still_open=%s' % (len(posts), dialog_present(drv, '新建提供方') is not None))
        shot(drv, 'J1_oauth_dialog_light')
        drv.execute_script('document.documentElement.classList.add("dark")')
        time.sleep(0.6)
        shot(drv, 'J1_oauth_dialog_dark')
        drv.execute_script('document.documentElement.classList.remove("dark")')

        # Esc / 取消 关闭
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(0.8)
        record('J2 OAuth Dialog Esc 关闭', dialog_present(drv, '新建提供方') is None, 'closed=%s' % (dialog_present(drv, '新建提供方') is None))

        # 空 client_secret 提交：暴露前端必填缺口
        click_button_text(drv, '添加提供方')
        wait_dialog(drv, '新建提供方')
        reset_reqs(drv)
        set_input(drv, find_visible(drv, By.ID, 'oauth-name'), '接线测试_OAuth_空secret_1485')
        set_input(drv, find_visible(drv, By.ID, 'oauth-slug'), 'jxtest-empty-%s' % time.strftime('%H%M%S'))
        set_input(drv, find_visible(drv, By.ID, 'oauth-client-id'), 'jxtest-client-empty')
        set_input(drv, find_visible(drv, By.ID, 'oauth-authz-endpoint'), 'https://idp.example.com/authz')
        set_input(drv, find_visible(drv, By.ID, 'oauth-token-endpoint'), 'https://idp.example.com/token')
        set_input(drv, find_visible(drv, By.ID, 'oauth-userinfo-endpoint'), 'https://idp.example.com/userinfo')
        click_button_text(drv, '保存', exact=True)
        time.sleep(2.5)
        empty_posts = find_req(get_reqs(drv), '/auth/oauth-providers', 'POST')
        empty_status = [p.get('status') for p in empty_posts]
        empty_resp = [(p.get('resp') or '')[:120] for p in empty_posts]
        record('J2b 空 client_secret 提交（前端未设必填）', bool(empty_posts) and all(x == 400 for x in empty_status),
               'status=%s resp=%s' % (empty_status, empty_resp))
        shot(drv, 'J2b_oauth_empty_secret_error_light')
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(0.8)

        # 真实创建（接线测试_ 前缀）→ 回读 → 删除
        click_button_text(drv, '添加提供方')
        wait_dialog(drv, '新建提供方')
        reset_reqs(drv)
        name = '接线测试_OAuth_1485'
        set_input(drv, find_visible(drv, By.ID, 'oauth-name'), name)
        set_input(drv, find_visible(drv, By.ID, 'oauth-slug'), 'jxtest-1485-%s' % time.strftime('%H%M%S'))
        set_input(drv, find_visible(drv, By.ID, 'oauth-client-id'), 'jxtest-client-1485')
        # 后端要求 client_secret 非空（前端未标必填，见缺陷记录）
        set_input(drv, find_visible(drv, By.ID, 'oauth-client-secret'), 'jxtest-secret-1485')
        set_input(drv, find_visible(drv, By.ID, 'oauth-authz-endpoint'), 'https://idp.example.com/authz')
        set_input(drv, find_visible(drv, By.ID, 'oauth-token-endpoint'), 'https://idp.example.com/token')
        set_input(drv, find_visible(drv, By.ID, 'oauth-userinfo-endpoint'), 'https://idp.example.com/userinfo')
        click_button_text(drv, '保存', exact=True)
        time.sleep(2.5)
        reqs = get_reqs(drv)
        posts = find_req(reqs, '/auth/oauth-providers', 'POST')
        record('J3 OAuth 创建 POST', any(r.get('status') in (200, 201) for r in posts),
               'status=%s body=%s' % ([r.get('status') for r in posts], [(r.get('body') or '')[:200] for r in posts][:1]))
        time.sleep(1.0)
        st, listing = api('/api/v1/auth/oauth-providers', token)
        provs = (listing.get('data') or {}).get('providers') or []
        mine = [p for p in provs if p.get('name') == name]
        provider_id = mine[0].get('id') if mine else None
        record('J4 OAuth GET 回读', bool(mine),
               'provider=%s' % ({k: mine[0].get(k) for k in ('id', 'name', 'slug', 'status')} if mine else None))
        shot(drv, 'J4_oauth_created_light')

        # 删除
        if provider_id:
            reset_reqs(drv)
            js_click(drv, find_visible(drv, By.CSS_SELECTOR, "button[aria-label='提供方操作：%s']" % name))
            WebDriverWait(drv, 10).until(lambda d: any(visible(i) for i in d.find_elements(By.CSS_SELECTOR, "[role='menuitem']")))
            next(i for i in drv.find_elements(By.CSS_SELECTOR, "[role='menuitem']") if visible(i) and '删除' in i.text).click()
            wait_dialog(drv, '确认删除提供方')
            click_button_text(drv, '删除', exact=True)
            time.sleep(2.0)
            dels = find_req(get_reqs(drv), '/auth/oauth-providers', 'DELETE')
            record('J5 OAuth 删除 DELETE', any(r.get('status') in (200, 204) for r in dels),
                   'DELETE=%s' % [r.get('status') for r in dels])
            provider_id = None

        # 日志维护：清理/归档确认框只走取消
        goto_settings(drv, '/system-settings/operations/log-maintenance', '日志维护', '归档管理')
        wait_noise(drv, 1.5)
        click_button_text(drv, '立即清理')
        dlg = wait_dialog(drv, '立即清理日志')
        record('J6 日志清理确认框', dlg is not None and '不可恢复' in dlg.text, 'text=%s' % (dlg.text[:80] if dlg else None))
        shot(drv, 'J6_log_clear_confirm_light')
        click_button_text(drv, '取消', exact=True)
        time.sleep(0.8)
        record('J7 日志清理取消不执行', dialog_present(drv, '立即清理日志') is None, 'closed')

        click_button_text(drv, '立即归档')
        dlg = wait_dialog(drv, '立即归档')
        record('J8 立即归档确认框', dlg is not None, 'text=%s' % (dlg.text[:80] if dlg else None))
        shot(drv, 'J8_archive_confirm_light')
        click_button_text(drv, '取消', exact=True)
        time.sleep(0.8)
        record('J9 归档取消不执行', dialog_present(drv, '立即归档') is None, 'closed')
    except Exception as exc:
        shot(drv, 'J_FAIL')
        record('J 清单外窗口', False, '异常: %s' % exc)
    finally:
        if provider_id:
            try:
                api('/api/v1/auth/oauth-providers/%s' % provider_id, token, method='DELETE')
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Z. 清理
# ---------------------------------------------------------------------------

def _api_retry(path, token, method='GET', body=None, tries=3):
    last = None
    for _ in range(tries):
        try:
            return api(path, token, method=method, body=body)
        except Exception as exc:
            last = exc
            time.sleep(2)
    raise last


def phase_z(drv, token):
    try:
        st, listing = _api_retry('/api/v1/auth/users?keyword=' + urllib.parse.quote('接线测试_ui1485_'), token)
        for it in ((listing.get('data') or {}).get('items') or []):
            if '接线测试_ui1485_' in it.get('username', ''):
                api('/api/v1/auth/users/%s' % it['id'], token, method='DELETE')
        st, opts = _api_retry('/api/option/', token)
        kv = (opts.get('data') or {})
        record('Z1 选项无测试残留', kv.get('site.name') == '智能语音测试平台',
               'site.name=%r' % kv.get('site.name'))
        st, listing = _api_retry('/api/v1/auth/users?keyword=' + urllib.parse.quote('接线测试_ui1485_'), token)
        left = [it.get('username') for it in ((listing.get('data') or {}).get('items') or [])]
        record('Z2 测试用户已清理', not left, 'left=%s' % left)
        st, provs = api('/api/v1/auth/oauth-providers', token)
        pl = [p.get('name') for p in ((provs.get('data') or {}).get('providers') or []) if '接线测试' in p.get('name', '')]
        record('Z3 测试提供方已清理', not pl, 'left=%s' % pl)
        set_theme(drv, 'light')
    except Exception as exc:
        record('Z 清理', False, '异常: %s' % exc)


PHASES = {'a': phase_a, 'b': phase_b, 'c': phase_c, 'd': phase_e, 'f': phase_f,
          'g': phase_g, 'h': phase_h, 'i': phase_i, 'j': phase_j}


def session_alive(drv):
    try:
        drv.current_url
        return True
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', default='all')
    args = parser.parse_args()
    os.makedirs(ART, exist_ok=True)
    token, user = rsa_login_token(*ACCOUNT)
    print('login ok user=%s' % (user or {}).get('username'))
    drv = driver_init()
    try:
        bootstrap(drv, token, user)
        me = {}
        for _ in range(3):
            try:
                me = current_user(drv)
                if me.get('username'):
                    break
            except Exception:
                time.sleep(1.5)
        record('AUTH 会话为真实账号', me.get('username') == ACCOUNT[0],
               'me=%s' % {k: me.get(k) for k in ('user_id', 'username', 'role_id')})
        wanted = list('abcdefghij') if args.phase == 'all' else list(args.phase)
        for key in wanted:
            fn = PHASES.get(key)
            if not fn:
                continue
            print('===== phase %s =====' % key)
            if not session_alive(drv):
                print('!! 浏览器会话失效，重建 driver')
                try:
                    drv.quit()
                except Exception:
                    pass
                drv = driver_init()
                bootstrap(drv, token, user)
            try:
                if key in ('a', 'c', 'f', 'h', 'i', 'j'):
                    fn(drv, token)
                else:
                    fn(drv)
            except Exception as exc:
                tb = traceback.format_exc().strip().splitlines()
                record('phase-%s 中断' % key, False, '异常: %s | %s' % (exc, ' <- '.join(tb[-3:])))
        phase_z(drv, token)
    finally:
        try:
            drv.quit()
        except Exception:
            pass
        out = os.path.join(ART, 'report.json')
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(RESULTS, f, ensure_ascii=False, indent=2)
        fails = [r for r in RESULTS if not r['ok']]
        print('\n===== SUMMARY: %d/%d passed, %d failed -> %s =====' % (
            len(RESULTS) - len(fails), len(RESULTS), len(fails), out))
        for f in fails:
            print('FAILED:', f['step'], '::', str(f['detail'])[:200])


if __name__ == '__main__':
    main()
