# -*- coding: utf-8 -*-
"""INT-1584 独立复核（测试工程师）：用户抽屉密码 8–128 位前端校验。

环境：docker 真实库栈，后端 http://127.0.0.1:15000（库 intelligent_audio_test，AUTH_MODE=off），
前端 = 本卡交付 diff 本地 pnpm build 的 dist 起的旁路 nginx 容器（默认 15284）。
覆盖卡面 A1–A8 + C 中的密码相关项，额外补 128 位边界、trim 语义、聚焦与 aria 关联。
密码是否真正生效：直接取 DB password_hash 用 bcrypt 校验（登录接口要求 RSA 密文，不走）。
写数据纪律：只建「接线测试_」前缀用户，结束删除并复查。
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import bcrypt
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15284')
API = os.environ.get('BACKEND_BASE', 'http://127.0.0.1:15000')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.environ.get('ART_DIR', r'D:\00_user_data\int1584_review_artifacts')
PG = os.environ.get('PG_CONTAINER', 'intelligent-audio-test-postgres-1')
PREFIX = '接线测试_'
USERS_PATH = '/system-settings/iam/users'

SHEET = "//*[@data-slot='sheet-content']"
PWD = SHEET + "//input[@id='user-password']"
PWD_LABEL = SHEET + "//label[@for='user-password']"
CREATE_BTN = SHEET + "//button[normalize-space(.)='创建']"
SAVE_BTN = SHEET + "//button[normalize-space(.)='保存']"
CANCEL_BTN = SHEET + "//button[normalize-space(.)='取消']"
SEARCH = "//input[@placeholder='搜索用户名或邮箱']"
LEN_MSG = '密码长度需为 8–128 位'
REQ_MSG = '请输入密码'

RESULT = []
JS_ERRORS = []


def check(name, ok, detail=''):
    RESULT.append({'name': name, 'ok': bool(ok), 'detail': str(detail)})
    print(('[PASS] ' if ok else '[FAIL] ') + name + (' | ' + str(detail) if detail else ''))
    return ok


# ---------- 驱动 ----------

def chrome_major():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            return int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        return 0


def build_driver():
    opts = Options()
    opts.binary_location = CHROME_BINARY
    opts.add_argument('--headless=new')
    opts.add_argument('--window-size=1680,1050')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--lang=zh-CN')
    opts.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    major = chrome_major()
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    exe = ''
    if major and os.path.isdir(cache):
        cands = []
        for ver in os.listdir(cache):
            p = os.path.join(cache, ver, 'chromedriver.exe')
            if os.path.isfile(p):
                try:
                    nums = tuple(int(x) for x in ver.split('.') if x.isdigit())
                    cands.append((nums, p))
                except ValueError:
                    pass
        same = [p for v, p in cands if v and v[0] == major]
        if same:
            exe = max(same)
    srv = Service(executable_path=exe) if exe else Service()
    drv = webdriver.Chrome(options=opts, service=srv)
    drv.set_page_load_timeout(60)
    return drv


def drain(drv):
    try:
        for entry in drv.get_log('browser'):
            if entry.get('level') == 'SEVERE':
                msg = entry.get('message', '')
                if 'Failed to load resource' in msg:
                    continue
                JS_ERRORS.append(msg)
    except Exception:
        pass


def goto(drv, path, wait=3.0):
    drv.get(BASE + path)
    WebDriverWait(drv, 40).until(
        lambda d: d.execute_script('return document.readyState') == 'complete'
    )
    time.sleep(wait)
    drain(drv)


def body_text(drv):
    return drv.execute_script('return document.body.textContent || ""') or ''


def shot(drv, name, note=''):
    os.makedirs(ART, exist_ok=True)
    p = os.path.join(ART, name + '.png')
    drv.save_screenshot(p)
    print('shot:', p, note)
    return p


def js_click(drv, xpath, wait=0.6):
    el = WebDriverWait(drv, 20).until(lambda d: d.find_element(By.XPATH, xpath))
    drv.execute_script(
        "arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", el
    )
    time.sleep(wait)


def set_value(drv, xpath, value, wait=0.4):
    el = WebDriverWait(drv, 20).until(lambda d: d.find_element(By.XPATH, xpath))
    drv.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].focus();", el)
    time.sleep(0.2)
    el.send_keys(Keys.CONTROL, 'a')
    el.send_keys(Keys.DELETE)
    time.sleep(0.15)
    if value:
        el.send_keys(value)
    time.sleep(wait)


# ---------- Network ----------

def perf_events(drv):
    out = []
    try:
        for entry in drv.get_log('performance'):
            try:
                data = json.loads(entry.get('message', '{}'))
            except Exception:
                continue
            msg = data.get('message') or {}
            method = msg.get('method') or ''
            params = msg.get('params') or {}
            if method == 'Network.requestWillBeSent':
                rq = params.get('request') or {}
                out.append({
                    'kind': 'req', 'id': params.get('requestId'),
                    'method': rq.get('method'), 'url': rq.get('url', ''),
                    'body': rq.get('postData'),
                })
            elif method == 'Network.responseReceived':
                rs = params.get('response') or {}
                out.append({
                    'kind': 'res', 'id': params.get('requestId'),
                    'url': rs.get('url', ''), 'status': rs.get('status'),
                })
    except Exception:
        pass
    return out


def user_calls(events):
    req = {}
    out = []
    for ev in events:
        if ev['kind'] == 'req':
            req[ev['id']] = ev
        else:
            r = req.get(ev['id']) or {}
            url = ev.get('url') or r.get('url') or ''
            if '/api/v1/auth/users' in url:
                out.append({
                    'method': r.get('method') or '?', 'url': url,
                    'status': ev.get('status'), 'body': r.get('body'),
                })
    return out


def capture(drv, action, wait=2.0):
    drv.get_log('performance')
    action()
    time.sleep(wait)
    drain(drv)
    return user_calls(perf_events(drv))


def writes(calls, method):
    return [c for c in calls if c['method'] == method]


# ---------- 页面对象 ----------

def drawer_open(drv):
    return bool(drv.find_elements(By.XPATH, SHEET))


def wait_drawer(drv, timeout=20):
    WebDriverWait(drv, timeout).until(lambda d: drawer_open(d))
    time.sleep(0.5)


def wait_drawer_closed(drv, timeout=20):
    WebDriverWait(drv, timeout).until(lambda d: not drawer_open(d))
    time.sleep(0.5)


def open_create(drv):
    btn = WebDriverWait(drv, 25).until(
        lambda d: [b for b in d.find_elements(By.XPATH, '//button') if '新建用户' in (b.text or '')]
    )
    drv.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", btn[0])
    wait_drawer(drv)


def search_user(drv, username):
    set_value(drv, SEARCH, username, wait=2.0)
    WebDriverWait(drv, 25).until(lambda d: username in body_text(d))
    time.sleep(0.5)


def open_edit(drv, username):
    search_user(drv, username)
    js_click(drv, "//button[@aria-label='用户操作：%s']" % username, wait=0.8)
    menu = "//*[@role='menuitem'][normalize-space(.)='编辑']"
    WebDriverWait(drv, 10).until(lambda d: d.find_elements(By.XPATH, menu))
    js_click(drv, menu, wait=0.8)
    wait_drawer(drv)


def pwd_state(drv):
    el = drv.find_element(By.XPATH, PWD)
    alerts = [
        a.text.strip()
        for a in drv.find_elements(By.XPATH, SHEET + "//*[@role='alert']")
    ]
    return {
        'value': el.get_attribute('value'),
        'placeholder': el.get_attribute('placeholder'),
        'aria_invalid': el.get_attribute('aria-invalid'),
        'aria_describedby': el.get_attribute('aria-describedby'),
        'label': (drv.find_element(By.XPATH, PWD_LABEL).get_attribute('textContent') or '').strip(),
        'alerts': alerts,
        'type': el.get_attribute('type'),
    }


def active_id(drv):
    try:
        return drv.switch_to.active_element.get_attribute('id')
    except Exception:
        return None


# ---------- 后端 / DB ----------

def http_json(method, path, payload=None):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(API + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            return resp.status, resp.read().decode('utf-8')
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode('utf-8', 'replace')


def list_users(keyword=None):
    qs = 'page=1&page_size=100'
    if keyword:
        qs += '&keyword=' + urllib.parse.quote(keyword)
    status, raw = http_json('GET', '/api/v1/auth/users?' + qs)
    try:
        payload = json.loads(raw)
    except Exception:
        payload = {}
    data = payload.get('data') if isinstance(payload.get('data'), dict) else payload
    return status, (data or {}).get('items', [])


def db_hash(username):
    out = subprocess.run(
        ['docker', 'exec', PG, 'psql', '-U', 'intelligent_audio_test',
         '-d', 'intelligent_audio_test', '-tAc',
         "select password_hash from users where username='%s'" % username],
        capture_output=True, text=True, encoding='utf-8', timeout=40,
    )
    return (out.stdout or '').strip()


def bcrypt_ok(password, hashed):
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except Exception:
        return False


# ---------- 证据截图 ----------

def network_shot(drv, rows, name, title):
    cells = ''.join(
        '<tr><td>%s</td><td class="u">%s</td><td class="s%s">%s</td><td><pre>%s</pre></td></tr>'
        % (r.get('method') or '', (r.get('url') or '').replace('&', '&amp;'),
           ' ok' if (r.get('status') or 0) < 400 else ' bad', r.get('status'),
           (r.get('body') or '-').replace('<', '&lt;'))
        for r in rows
    )
    html = (
        '<html><head><meta charset="utf-8"><style>'
        'body{font-family:Consolas,monospace;font-size:13px;background:#0f172a;color:#e2e8f0;padding:16px}'
        'table{border-collapse:collapse;width:100%}td,th{border:1px solid #334155;padding:6px 8px;vertical-align:top}'
        'th{background:#1e293b;text-align:left}.u{color:#93c5fd;word-break:break-all}'
        '.ok{color:#4ade80}.bad{color:#f87171}pre{margin:0;white-space:pre-wrap;word-break:break-all;color:#fde68a}'
        '</style></head><body><h3>' + title + '</h3>'
        '<table><tr><th>Method</th><th>URL</th><th>Status</th><th>Request Body</th></tr>'
        + (cells or '<tr><td colspan="4">（窗口内无 /api/v1/auth/users 请求）</td></tr>')
        + '</table></body></html>'
    )
    os.makedirs(ART, exist_ok=True)
    p = os.path.join(ART, name + '.png')
    drv.get('data:text/html;charset=utf-8,' + urllib.parse.quote(html))
    time.sleep(0.6)
    drv.save_screenshot(p)
    print('shot:', p)
    goto(drv, USERS_PATH, 2.5)
    return p


def set_theme(drv, mode):
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", mode)


# ---------- 主流程 ----------

def main():
    stamp = time.strftime('%m%d%H%M%S')
    username = PREFIX + 'review' + stamp
    email = 'wiring_review_%s@example.com' % stamp
    created_id = None
    old_pwd = 'Abcd1234'          # A5 建用户时的密码（提交带首尾空格，验证 trim）
    typed_pwd = '  Abcd1234  '
    pwd128 = 'P' * 128
    new_pwd = 'Newpass123'

    status, raw_health = http_json('GET', '/health')
    health = json.loads(raw_health) if raw_health else {}
    check('环境：后端 /health 连的是真实库 intelligent_audio_test',
          health.get('database') == 'intelligent_audio_test', health.get('database'))
    st, items = list_users()
    check('环境：GET /auth/users 可用', st == 200, 'status=%s count=%s' % (st, len(items)))
    # 共享库里存在其他卡/其他 run 遗留的「接线测试_」用户（RBAC 角色矩阵等），
    # 不是本 run 写的；收尾只要求本 run 的用户消失、集合回到开工时。
    pre_existing = {u.get('username') for u in items if (u.get('username') or '').startswith(PREFIX)}
    print('pre-existing prefix users:', sorted(pre_existing))

    drv = build_driver()
    try:
        goto(drv, USERS_PATH, 5.0)
        WebDriverWait(drv, 45).until(lambda d: '新建用户' in body_text(d))
        check('页面就绪：用户管理列表加载成功', '用户管理' in body_text(drv))

        # ---- A1 ----
        open_create(drv)
        s = pwd_state(drv)
        check('A1 新建抽屉密码占位「输入密码（8–128 位）」', s['placeholder'] == '输入密码（8–128 位）', s['placeholder'])
        check('A1 新建标签含「密码」与必填星号', '密码' in s['label'] and '*' in s['label'], s['label'])
        check('A1 密码框 type=password', s['type'] == 'password', s['type'])
        set_value(drv, SHEET + "//input[@id='user-username']", username)
        set_value(drv, SHEET + "//input[@id='user-email']", email)
        shot(drv, '01_create_drawer_light', '新建抽屉（浅色）')

        # ---- A2 1/7/129 ----
        for label, value in [('1 位', 'x'), ('7 位', 'x' * 7), ('129 位', 'x' * 129)]:
            set_value(drv, PWD, value)
            calls = capture(drv, lambda: js_click(drv, CREATE_BTN, wait=0.8))
            s = pwd_state(drv)
            check('A2 %s：零 POST /api/v1/auth/users' % label,
                  not writes(calls, 'POST'),
                  [(c['method'], c['status']) for c in calls])
            check('A2 %s：红字「%s」' % (label, LEN_MSG), LEN_MSG in s['alerts'], s['alerts'])
            check('A2 %s：aria-invalid=true' % label, str(s['aria_invalid']).lower() == 'true', s['aria_invalid'])
            check('A2 %s：aria-describedby 指向错误节点' % label,
                  s['aria_describedby'] == 'user-password-error', s['aria_describedby'])
            check('A2 %s：提交后焦点在密码框' % label, active_id(drv) == 'user-password', active_id(drv))
            if label == '1 位':
                shot(drv, '02_error_length_light', '1 位密码错误态（浅色）')

        # ---- A6a 改回合法值，错误即时消失（未提交） ----
        set_value(drv, PWD, old_pwd, wait=0.7)
        s = pwd_state(drv)
        check('A6 改回合法值：错误提示即时消失', not s['alerts'] and str(s['aria_invalid']).lower() != 'true', s)

        # ---- A4 纯空格 ----
        set_value(drv, PWD, '    ', wait=0.5)
        calls = capture(drv, lambda: js_click(drv, CREATE_BTN, wait=0.8))
        s = pwd_state(drv)
        check('A4 纯空格密码：零 POST', not writes(calls, 'POST'), [(c['method'], c['status']) for c in calls])
        check('A4 纯空格密码：提示「%s」' % REQ_MSG, REQ_MSG in s['alerts'], s['alerts'])

        # ---- A3 留空 ----
        set_value(drv, PWD, '', wait=0.4)
        calls = capture(drv, lambda: js_click(drv, CREATE_BTN, wait=0.8))
        s = pwd_state(drv)
        check('A3 密码留空：零 POST', not writes(calls, 'POST'), [(c['method'], c['status']) for c in calls])
        check('A3 密码留空：提示「%s」' % REQ_MSG, REQ_MSG in s['alerts'], s['alerts'])

        # ---- A5 合法 8 位（带首尾空格，验证 trim）----
        set_value(drv, PWD, typed_pwd, wait=0.6)
        calls = capture(drv, lambda: js_click(drv, CREATE_BTN, wait=0.8), wait=4.5)
        posts = writes(calls, 'POST')
        created = posts[0] if posts else None
        check('A5 合法密码：POST /api/v1/auth/users 201',
              bool(created) and created['status'] == 201,
              (created or {}).get('status'))
        body = {}
        if created and created.get('body'):
            try:
                body = json.loads(created['body'])
            except Exception:
                body = {}
        check('A5 提交体 password 已 trim（"Abcd1234"）', body.get('password') == old_pwd, body.get('password'))
        try:
            wait_drawer_closed(drv)
            closed = True
        except Exception:
            closed = False
        check('A5 创建成功后抽屉关闭', closed)
        network_shot(drv, calls, '03_network_create_201', 'INT-1584 创建用户 Network（POST 201）')

        goto(drv, USERS_PATH, 3.0)
        search_user(drv, username)
        check('A5 列表出现新用户', username in body_text(drv), username)
        shot(drv, '04_created_in_list_light', '创建成功后列表（浅色）')
        st, items = list_users(username)
        row = next((u for u in items if u.get('username') == username), None)
        check('A5 GET /auth/users 接口核对含新用户', row is not None, 'status=%s count=%s' % (st, len(items)))
        if row:
            created_id = row.get('id')
        print('created_id =', created_id)
        hash0 = db_hash(username)
        check('A5 用户落库密码 bcrypt 校验（原密码可用）', bool(hash0) and bcrypt_ok(old_pwd, hash0), hash0[:20])

        # ---- A6b 关闭重开：密码清空、错误不残留 ----
        open_create(drv)
        s = pwd_state(drv)
        check('A6 重开新建抽屉：密码为空', (s['value'] or '') == '', s['value'])
        check('A6 重开新建抽屉：无错误残留', not s['alerts'], s['alerts'])
        js_click(drv, CANCEL_BTN, wait=0.8)
        try:
            wait_drawer_closed(drv)
        except Exception:
            pass

        # ---- A7 编辑态留空保存 ----
        open_edit(drv, username)
        s = pwd_state(drv)
        check('A7 编辑占位「留空表示不修改密码」', s['placeholder'] == '留空表示不修改密码', s['placeholder'])
        check('A7 编辑态标签无必填星号', '*' not in s['label'], s['label'])
        calls = capture(drv, lambda: js_click(drv, SAVE_BTN, wait=0.8), wait=4.5)
        puts = writes(calls, 'PUT')
        put = puts[0] if puts else None
        check('A7 留空保存：PUT 200', bool(put) and put['status'] == 200, (put or {}).get('status'))
        pb = {}
        if put and put.get('body'):
            try:
                pb = json.loads(put['body'])
            except Exception:
                pb = {}
        check('A7 留空保存：PUT body 无 password 键', put is not None and 'password' not in pb, pb)
        hash1 = db_hash(username)
        check('A7 留空保存后密码哈希不变', bool(hash0) and hash0 == hash1, (hash0[:16], hash1[:16]))
        check('A7 留空保存后原密码仍有效（bcrypt）', bcrypt_ok(old_pwd, hash1), '')
        network_shot(drv, calls, '05_network_edit_no_password', 'INT-1584 编辑留空 Network（PUT 无 password 键）')

        # ---- A8 编辑态非法 / 边界 / 合法 ----
        open_edit(drv, username)
        set_value(drv, PWD, 'x' * 7)
        calls = capture(drv, lambda: js_click(drv, SAVE_BTN, wait=0.8))
        s = pwd_state(drv)
        check('A8 编辑 7 位：零 PUT', not writes(calls, 'PUT'), [(c['method'], c['status']) for c in calls])
        check('A8 编辑 7 位：红字「%s」' % LEN_MSG, LEN_MSG in s['alerts'], s['alerts'])
        shot(drv, '06_edit_error_light', '编辑态 7 位错误（浅色）')

        set_value(drv, PWD, 'x' * 129)
        calls = capture(drv, lambda: js_click(drv, SAVE_BTN, wait=0.8))
        s = pwd_state(drv)
        check('A8 编辑 129 位：零 PUT', not writes(calls, 'PUT'), [(c['method'], c['status']) for c in calls])
        check('A8 编辑 129 位：红字「%s」' % LEN_MSG, LEN_MSG in s['alerts'], s['alerts'])

        # 128 位边界应放行
        set_value(drv, PWD, pwd128)
        calls = capture(drv, lambda: js_click(drv, SAVE_BTN, wait=0.8), wait=4.5)
        puts = writes(calls, 'PUT')
        put = puts[0] if puts else None
        pb = {}
        if put and put.get('body'):
            try:
                pb = json.loads(put['body'])
            except Exception:
                pb = {}
        check('A8 编辑 128 位：UI 放行并原样提交（body password 长度 128）',
              len(pb.get('password') or '') == 128, len(pb.get('password') or ''))
        if put and put['status'] == 200:
            hash2 = db_hash(username)
            check('A8 编辑 128 位（上边界）：PUT 200', True, 200)
            check('A8 128 位保存后哈希变化', bool(hash1) and hash1 != hash2, (hash1[:16], hash2[:16]))
            check('A8 128 位新密码可校验通过（bcrypt）', bcrypt_ok(pwd128, hash2), '')
            check('A8 原密码已被替换（bcrypt 失败）', not bcrypt_ok(old_pwd, hash2), '')
        else:
            # 已知后端口径：auth_service 用 bcrypt，上限 72 字节，>72 位直接 400
            # （code=203 password cannot be longer than 72 bytes）。属于 INT-1590
            # 的后端校验口径，不在本卡（前端 8–128）范围内；这里只记录事实。
            hash2 = db_hash(username)
            check('A8 编辑 128 位：后端拒收 400（已知 bcrypt 72 字节上限，见交付结论）',
                  bool(put) and put['status'] == 400, (put or {}).get('status'))
            check('A8 128 位被拒后哈希不变（无半成功写入）', hash1 == hash2, (hash1[:16], hash2[:16]))

        # 8 位合法改密
        open_edit(drv, username)
        set_value(drv, PWD, new_pwd)
        set_value(drv, SHEET + "//input[@id='user-display-name']", '接线测试_改名')
        calls = capture(drv, lambda: js_click(drv, SAVE_BTN, wait=0.8), wait=4.5)
        puts = writes(calls, 'PUT')
        put = puts[0] if puts else None
        pb = {}
        if put and put.get('body'):
            try:
                pb = json.loads(put['body'])
            except Exception:
                pb = {}
        check('A8 编辑 8 位：PUT 200', bool(put) and put['status'] == 200, (put or {}).get('status'))
        check('A8 编辑 8 位：body 带 password', pb.get('password') == new_pwd, pb.get('password'))
        hash3 = db_hash(username)
        check('A8 8 位改密后哈希变化', bool(hash2) and hash2 != hash3, (hash2[:16], hash3[:16]))
        check('A8 新密码可校验通过（bcrypt）', bcrypt_ok(new_pwd, hash3), '')
        check('A8 前一密码已被替换（bcrypt 失败）', not bcrypt_ok(pwd128, hash3), '')
        network_shot(drv, calls, '07_network_edit_password', 'INT-1584 编辑改密 Network（PUT 带 password）')

        # ---- C 跨组件同步：列表随更新刷新 ----
        goto(drv, USERS_PATH, 3.5)
        search_user(drv, username)
        check('C 编辑成功后列表刷新（显示名已更新）', '接线测试_改名' in body_text(drv), '')
        st, items = list_users(username)
        row = next((u for u in items if u.get('username') == username), None)
        check('C 接口核对显示名已更新', bool(row) and row.get('display_name') == '接线测试_改名',
              (row or {}).get('display_name'))

        # ---- 深色截图 ----
        set_theme(drv, 'dark')
        goto(drv, USERS_PATH, 4.0)
        open_create(drv)
        set_value(drv, PWD, 'x')
        js_click(drv, CREATE_BTN, wait=0.9)
        s = pwd_state(drv)
        check('深色模式：错误态红字仍在', LEN_MSG in s['alerts'], s['alerts'])
        shot(drv, '08_create_error_dark', '新建抽屉错误态（深色）')
        js_click(drv, CANCEL_BTN, wait=0.6)
        set_theme(drv, 'light')
        goto(drv, USERS_PATH, 3.0)

        check('全程无 JS SEVERE 错误', not JS_ERRORS, JS_ERRORS[:3])
    finally:
        if created_id:
            code, raw = http_json('DELETE', '/api/v1/auth/users/%s' % created_id)
            print('DELETE user', created_id, code, raw[:120])
        try:
            st, items = list_users(username)
            names = [u.get('username') for u in items]
            check('收尾：GET /auth/users 无本 run 残留', username not in names, names)
            st, items = list_users(PREFIX)
            now_prefix = {u.get('username') for u in items}
            leftover = now_prefix - pre_existing
            check('收尾：本 run 未在「接线测试_」前缀下新增残留',
                  not leftover, sorted(leftover))
        except Exception as exc:
            print('cleanup verify error:', exc)
        drv.quit()
        os.makedirs(ART, exist_ok=True)
        with open(os.path.join(ART, 'result.json'), 'w', encoding='utf-8') as fh:
            json.dump(RESULT, fh, ensure_ascii=False, indent=2)
        failed = [r for r in RESULT if not r['ok']]
        print('\n==== %d checks, %d failed ====' % (len(RESULT), len(failed)))
        for r in failed:
            print('FAIL:', r['name'], r['detail'])
        sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
