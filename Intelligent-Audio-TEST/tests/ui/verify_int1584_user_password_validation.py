# -*- coding: utf-8 -*-
"""INT-1584 验收：系统设置·用户管理抽屉密码 8–128 位前端校验。

真实库栈（docker）：前端用本卡交付 diff 本地 `pnpm build` 的 dist 起旁路 nginx 容器
（默认 http://127.0.0.1:15284），后端网关 http://127.0.0.1:15000
（库 intelligent_audio_test，AUTH_MODE=off + admin 369）。

覆盖卡面 A1–A8：
A1 新建抽屉占位「输入密码（8–128 位）」+ 标签「密码 *」
A2 1/7/129 位 → 零 POST /auth/users、aria-invalid、红字「密码长度需为 8–128 位」
A3 密码留空 → 零请求 + 「请输入密码」
A4 密码只填空格 → 按空处理，零请求
A5 8 位合法密码 → 201、抽屉关闭、列表出现新用户
A6 改回合法值错误即时消失；关闭重开密码清空、错误不残留
A7 编辑态留空保存 → PUT body 无 password 键，密码哈希不变
A8 编辑态 7 位 → 零 PUT + 红字；8 位 → PUT 带 password、200、哈希变化

写数据纪律：只建「接线测试_」前缀用户，run 结束前删除。
"""
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15284')
API = os.environ.get('BACKEND_BASE', 'http://127.0.0.1:15000')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.environ.get(
    'ART_DIR', os.path.join(os.environ.get('TEMP', '/tmp'), 'int1584_artifacts')
)
PG = os.environ.get('PG_CONTAINER', 'intelligent-audio-test-postgres-1')
PREFIX = '接线测试_'
USERS_PATH = '/system-settings/iam/users'

SHEET = "//*[@data-slot='sheet-content']"
PWD_INPUT = SHEET + "//input[@id='user-password']"
PWD_LABEL = SHEET + "//label[@for='user-password']"
CREATE_BTN = SHEET + "//button[normalize-space(.)='创建']"
SAVE_BTN = SHEET + "//button[normalize-space(.)='保存']"
CANCEL_BTN = SHEET + "//button[normalize-space(.)='取消']"
SEARCH = "//input[@placeholder='搜索用户名或邮箱']"

RESULT = []
JS_ERRORS = []


def check(name, ok, detail=''):
    RESULT.append({'name': name, 'ok': bool(ok), 'detail': detail})
    print(('[PASS] ' if ok else '[FAIL] ') + name + (' | ' + str(detail) if detail else ''))
    return ok


def build_driver():
    opts = Options()
    opts.binary_location = CHROME_BINARY
    opts.add_argument('--headless=new')
    opts.add_argument('--window-size=1680,1050')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--lang=zh-CN')
    opts.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    import winreg
    major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    exe = ''
    if major and os.path.isdir(cache):
        cands = []
        for ver in os.listdir(cache):
            p = os.path.join(cache, ver, 'chromedriver.exe')
            if os.path.isfile(p):
                try:
                    cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), p))
                except ValueError:
                    pass
        same = [p for v, p in cands if v and v[0] == major]
        if same:
            exe = max(same)
    srv = Service(executable_path=exe) if exe else Service()
    drv = webdriver.Chrome(options=opts, service=srv)
    drv.set_page_load_timeout(60)
    return drv


def drain_browser(drv):
    try:
        for entry in drv.get_log('browser'):
            msg = entry.get('message', '')
            if 'Failed to load resource' in msg and 'Uncaught' not in msg:
                continue
            if entry.get('level') == 'SEVERE':
                JS_ERRORS.append(msg)
    except Exception:
        pass


def goto(drv, path, wait=3.0):
    drv.get(BASE + path)
    WebDriverWait(drv, 40).until(
        lambda d: d.execute_script('return document.readyState') == 'complete'
    )
    time.sleep(wait)
    drain_browser(drv)


def body_text(drv):
    return drv.execute_script('return document.body.textContent || ""') or ''


def shot(drv, name, note=''):
    os.makedirs(ART, exist_ok=True)
    p = os.path.join(ART, name + '.png')
    drv.save_screenshot(p)
    print('shot:', p, note)
    return p


def js_click(drv, xpath, wait=0.6):
    el = drv.find_element(By.XPATH, xpath)
    drv.execute_script(
        "arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", el
    )
    time.sleep(wait)


def set_value(drv, xpath, value, wait=0.4):
    """真实输入：聚焦 → Ctrl+A → Delete → 逐字输入（React onChange 必然触发）。"""
    el = drv.find_element(By.XPATH, xpath)
    drv.execute_script(
        "arguments[0].scrollIntoView({block:'center'}); arguments[0].focus();", el
    )
    time.sleep(0.2)
    el.send_keys(Keys.CONTROL, 'a')
    el.send_keys(Keys.DELETE)
    time.sleep(0.15)
    if value:
        el.send_keys(value)
    time.sleep(wait)


def perf_events(drv):
    events = []
    try:
        for entry in drv.get_log('performance'):
            try:
                data = json.loads(entry.get('message', ''))
            except Exception:
                continue
            inner = data.get('message', data)
            if not isinstance(inner, dict):
                continue
            method = inner.get('method', '')
            params = inner.get('params', {}) or {}
            if method == 'Network.requestWillBeSent':
                rq = params.get('request', {}) or {}
                events.append(
                    {
                        'kind': 'req',
                        'id': params.get('requestId'),
                        'method': rq.get('method'),
                        'url': rq.get('url', ''),
                        'body': rq.get('postData'),
                    }
                )
            elif method == 'Network.responseReceived':
                rs = params.get('response', {}) or {}
                events.append(
                    {
                        'kind': 'res',
                        'id': params.get('requestId'),
                        'url': rs.get('url', ''),
                        'status': rs.get('status'),
                    }
                )
    except Exception:
        pass
    return events


def api_calls(events, url_part='/api/v1/auth/users'):
    req = {}
    out = []
    for ev in events:
        if ev['kind'] == 'req':
            req[ev['id']] = ev
        else:
            r = req.get(ev['id'], {})
            url = ev.get('url') or r.get('url') or ''
            if url_part in url:
                out.append(
                    {
                        'method': r.get('method') or '?',
                        'url': url,
                        'status': ev.get('status'),
                        'body': r.get('body'),
                    }
                )
    return out


def capture_action(drv, action, wait=2.0):
    """执行动作并只返回该动作期间的 /api/v1/auth/users 调用。"""
    drv.get_log('performance')
    action()
    time.sleep(wait)
    drain_browser(drv)
    return api_calls(perf_events(drv))


def dialog_present(drv):
    return bool(drv.find_elements(By.XPATH, SHEET))


def wait_dialog(drv, timeout=15):
    WebDriverWait(drv, timeout).until(lambda d: dialog_present(d))
    time.sleep(0.5)


def wait_dialog_closed(drv, timeout=15):
    WebDriverWait(drv, timeout).until(lambda d: not dialog_present(d))
    time.sleep(0.6)


def password_state(drv):
    el = drv.find_element(By.XPATH, PWD_INPUT)
    return {
        'value': el.get_attribute('value'),
        'placeholder': el.get_attribute('placeholder'),
        'aria_invalid': el.get_attribute('aria-invalid'),
        'label': drv.find_element(By.XPATH, PWD_LABEL).get_attribute('textContent'),
        'alerts': [
            a.text.strip()
            for a in drv.find_elements(By.XPATH, SHEET + "//*[@role='alert']")
        ],
    }


def open_create(drv):
    btn = WebDriverWait(drv, 20).until(
        lambda d: [
            b for b in d.find_elements(By.XPATH, '//button') if '新建用户' in (b.text or '')
        ]
    )
    drv.execute_script(
        "arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", btn[0]
    )
    wait_dialog(drv)


def find_row_action(drv, username):
    xpath = f"//button[@aria-label='用户操作：{username}']"
    WebDriverWait(drv, 20).until(
        lambda d: d.find_elements(By.XPATH, xpath)
    )
    return xpath


def search_user(drv, username):
    set_value(drv, SEARCH, username, wait=2.0)
    WebDriverWait(drv, 25).until(
        lambda d: username in body_text(d)
    )
    time.sleep(0.5)


def open_edit(drv, username):
    search_user(drv, username)
    js_click(drv, find_row_action(drv, username), wait=0.8)
    menu = "//*[@role='menuitem'][normalize-space(.)='编辑']"
    WebDriverWait(drv, 10).until(lambda d: d.find_elements(By.XPATH, menu))
    js_click(drv, menu, wait=0.8)
    wait_dialog(drv)


def db_hash(username):
    try:
        out = subprocess.run(
            [
                'docker', 'exec', PG, 'psql', '-U', 'intelligent_audio_test',
                '-d', 'intelligent_audio_test', '-tAc',
                f"select password_hash from users where username='{username}'",
            ],
            capture_output=True, text=True, encoding='utf-8', timeout=30,
        )
        return (out.stdout or '').strip()
    except Exception as exc:  # noqa: BLE001
        print('db_hash error:', exc)
        return ''


def http_json(method, path, payload=None):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(API + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode('utf-8')
            return resp.status, raw
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode('utf-8', 'replace')


def list_users(keyword=None):
    """GET /auth/users（统一信封：{success, data:{items}}）；keyword 走服务端过滤。"""
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


def network_screenshot(drv, rows, name):
    cells = ''.join(
        '<tr><td>%s</td><td class="u">%s</td><td class="s%s">%s</td><td><pre>%s</pre></td></tr>'
        % (
            r.get('method') or '',
            (r.get('url') or '').replace('&', '&amp;'),
            ' ok' if (r.get('status') or 0) < 400 else ' bad',
            r.get('status'),
            (r.get('body') or '-').replace('<', '&lt;'),
        )
        for r in rows
    )
    html = (
        '<html><head><meta charset="utf-8"><style>'
        'body{font-family:Consolas,monospace;font-size:13px;background:#0f172a;color:#e2e8f0;padding:16px}'
        'table{border-collapse:collapse;width:100%}td,th{border:1px solid #334155;padding:6px 8px;vertical-align:top}'
        'th{background:#1e293b;text-align:left}.u{color:#93c5fd;word-break:break-all}'
        '.ok{color:#4ade80}.bad{color:#f87171}pre{margin:0;white-space:pre-wrap;word-break:break-all;color:#fde68a}'
        '</style></head><body><h3>INT-1584 Network（本次动作期间 /api/v1/auth/users）</h3>'
        '<table><tr><th>Method</th><th>URL</th><th>Status</th><th>Request Body</th></tr>'
        + cells
        + '</table></body></html>'
    )
    os.makedirs(ART, exist_ok=True)
    p = os.path.join(ART, name + '.png')
    drv.get('data:text/html;charset=utf-8,' + urllib.parse.quote(html))
    time.sleep(0.6)
    drv.save_screenshot(p)
    print('shot:', p)
    # 截图后回到被测页面，避免后续步骤落在 data: 文档上
    goto(drv, USERS_PATH, 2.5)
    return p


def set_theme(drv, mode):
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", mode)


def main():
    username = PREFIX + 'pw' + time.strftime('%m%d%H%M%S')
    email = 'wiring_pw_%s@example.com' % time.strftime('%m%d%H%M%S')
    created_id = None
    drv = build_driver()
    try:
        goto(drv, USERS_PATH, 5.0)
        WebDriverWait(drv, 40).until(lambda d: '新建用户' in body_text(d))
        WebDriverWait(drv, 40).until(lambda d: '加载失败' not in body_text(d))
        check('页面就绪：用户管理列表加载成功', '用户管理' in body_text(drv))

        # ---- A1 新建抽屉：占位 + 必填星号 ----
        open_create(drv)
        st = password_state(drv)
        check(
            'A1 新建占位「输入密码（8–128 位）」',
            st['placeholder'] == '输入密码（8–128 位）',
            st['placeholder'],
        )
        check('A1 标签含必填星号「密码 *」', '*' in (st['label'] or '') and '密码' in (st['label'] or ''), st['label'])
        set_value(drv, SHEET + "//input[@id='user-username']", username)
        set_value(drv, SHEET + "//input[@id='user-email']", email)
        shot(drv, '01_create_drawer_light', '新建抽屉（浅色）')

        # ---- A2 1/7/129 位 → 零请求 + 红字 ----
        cases = [('1 位', 'x'), ('7 位', 'x' * 7), ('129 位', 'x' * 129)]
        for label, value in cases:
            set_value(drv, PWD_INPUT, value)
            calls = capture_action(drv, lambda: js_click(drv, CREATE_BTN, wait=0.8))
            creates = [c for c in calls if c['method'] == 'POST']
            st = password_state(drv)
            check(
                'A2 %s 密码：零 POST /auth/users' % label,
                not creates,
                [c['method'] + ' ' + str(c['status']) for c in calls],
            )
            check(
                'A2 %s 密码：红字「密码长度需为 8–128 位」' % label,
                any('密码长度需为 8–128 位' in a for a in st['alerts']),
                st['alerts'],
            )
            check(
                'A2 %s 密码：aria-invalid=true' % label,
                str(st['aria_invalid']).lower() == 'true',
                st['aria_invalid'],
            )
            if label == '1 位':
                shot(drv, '02_error_length_light', '1 位密码错误态（浅色）')

        # ---- A3 留空 ----
        set_value(drv, PWD_INPUT, '')
        calls = capture_action(drv, lambda: js_click(drv, CREATE_BTN, wait=0.8))
        st = password_state(drv)
        check('A3 密码留空：零请求', not [c for c in calls if c['method'] == 'POST'], calls)
        check('A3 密码留空：提示「请输入密码」', any('请输入密码' in a for a in st['alerts']), st['alerts'])

        # ---- A4 只填空格 ----
        set_value(drv, PWD_INPUT, '    ')
        calls = capture_action(drv, lambda: js_click(drv, CREATE_BTN, wait=0.8))
        st = password_state(drv)
        check('A4 纯空格密码：零请求', not [c for c in calls if c['method'] == 'POST'], calls)
        check('A4 纯空格密码：按空处理提示「请输入密码」', any('请输入密码' in a for a in st['alerts']), st['alerts'])

        # ---- A6a 改回合法值错误即时消失 ----
        set_value(drv, PWD_INPUT, 'Abcd1234', wait=0.6)
        st = password_state(drv)
        check('A6 输入合法密码后错误即时消失', not st['alerts'] and str(st['aria_invalid']).lower() != 'true', st)

        # ---- A5 合法 8 位 → 201 + 抽屉关闭 + 列表出现 ----
        calls = capture_action(drv, lambda: js_click(drv, CREATE_BTN, wait=0.8), wait=4.0)
        creates = [c for c in calls if c['method'] == 'POST']
        created = creates[0] if creates else None
        check('A5 合法密码：POST /auth/users 201', bool(created) and created['status'] == 201, created)
        if created and created.get('body'):
            try:
                payload = json.loads(created['body'])
                check(
                    'A5 提交体 password 为 trim 后的原值',
                    payload.get('password') == 'Abcd1234',
                    payload.get('password'),
                )
            except Exception:
                pass
        try:
            wait_dialog_closed(drv)
            closed = True
        except Exception:
            closed = False
        check('A5 创建成功后抽屉关闭', closed)
        network_screenshot(drv, calls, '03_network_create_201')
        goto(drv, USERS_PATH, 3.0)
        search_user(drv, username)
        check('A5 列表出现新用户', username in body_text(drv), username)
        shot(drv, '04_created_in_list_light', '创建成功后列表')
        status, items = list_users(username)
        names = [u.get('username') for u in items]
        check('A5 GET /auth/users 含新用户（接口核对）', username in names, 'status=%s count=%s' % (status, len(names)))
        for u in items:
            if u.get('username') == username:
                created_id = u.get('id')
        print('created_id =', created_id)
        hash_initial = db_hash(username)

        # ---- A6b 关闭重开：密码清空、错误不残留 ----
        open_create(drv)
        st = password_state(drv)
        check('A6 重开新建抽屉：密码为空', (st['value'] or '') == '', st['value'])
        check('A6 重开新建抽屉：无错误残留', not st['alerts'], st['alerts'])
        js_click(drv, CANCEL_BTN, wait=0.8)
        try:
            wait_dialog_closed(drv)
        except Exception:
            pass

        # ---- A7 编辑态留空保存：PUT body 无 password ----
        open_edit(drv, username)
        st = password_state(drv)
        check('A7 编辑占位「留空表示不修改密码」', st['placeholder'] == '留空表示不修改密码', st['placeholder'])
        check('A7 编辑标签无必填星号', '*' not in (st['label'] or ''), st['label'])
        calls = capture_action(drv, lambda: js_click(drv, SAVE_BTN, wait=0.8), wait=4.0)
        puts = [c for c in calls if c['method'] == 'PUT']
        put = puts[0] if puts else None
        ok_put = bool(put) and put['status'] == 200
        body_has_password = bool(put and put.get('body') and 'password' in json.loads(put['body']))
        check('A7 留空保存：PUT 200', ok_put, put)
        check('A7 留空保存：PUT body 不含 password 键', put is not None and not body_has_password, put.get('body') if put else None)
        hash_after_empty = db_hash(username)
        check('A7 留空保存后密码哈希不变', hash_initial and hash_initial == hash_after_empty, (hash_initial[:16], hash_after_empty[:16]))
        network_screenshot(drv, calls, '05_network_edit_no_password')

        # ---- A8 编辑态 7 位 → 零 PUT；8 位 → PUT 带 password ----
        open_edit(drv, username)
        set_value(drv, PWD_INPUT, 'x' * 7)
        calls = capture_action(drv, lambda: js_click(drv, SAVE_BTN, wait=0.8))
        st = password_state(drv)
        check('A8 编辑 7 位：零 PUT', not [c for c in calls if c['method'] == 'PUT'], calls)
        check('A8 编辑 7 位：红字「密码长度需为 8–128 位」', any('密码长度需为 8–128 位' in a for a in st['alerts']), st['alerts'])
        shot(drv, '06_edit_error_light', '编辑态 7 位错误（浅色）')
        set_value(drv, PWD_INPUT, 'Newpass123')
        calls = capture_action(drv, lambda: js_click(drv, SAVE_BTN, wait=0.8), wait=4.0)
        puts = [c for c in calls if c['method'] == 'PUT']
        put = puts[0] if puts else None
        payload_ok = False
        if put and put.get('body'):
            try:
                payload_ok = json.loads(put['body']).get('password') == 'Newpass123'
            except Exception:
                payload_ok = False
        check('A8 编辑 8 位：PUT 200', bool(put) and put['status'] == 200, put)
        check('A8 编辑 8 位：PUT body 带 password', payload_ok, put.get('body') if put else None)
        hash_after_new = db_hash(username)
        check('A8 改密后密码哈希变化', hash_initial and hash_after_new and hash_initial != hash_after_new, (hash_after_empty[:16], hash_after_new[:16]))
        network_screenshot(drv, calls, '07_network_edit_password')

        # ---- 深浅色截图 ----
        set_theme(drv, 'dark')
        goto(drv, USERS_PATH, 4.0)
        open_create(drv)
        set_value(drv, PWD_INPUT, 'x')
        js_click(drv, CREATE_BTN, wait=0.8)
        shot(drv, '08_create_error_dark', '新建抽屉错误态（深色）')
        js_click(drv, CANCEL_BTN, wait=0.6)
        set_theme(drv, 'light')
        goto(drv, USERS_PATH, 3.0)

        check('全程无 JS SEVERE 错误', not JS_ERRORS, JS_ERRORS[:3])
    finally:
        # 清理：只删本 run 建的「接线测试_」用户
        try:
            if created_id:
                status, raw = http_json('DELETE', '/api/v1/auth/users/%s' % created_id)
                print('DELETE user', created_id, status, raw[:120])
        except Exception as exc:  # noqa: BLE001
            print('cleanup error:', exc)
        try:
            status, items = list_users(username)
            names = [u.get('username') for u in items]
            check('收尾：GET /auth/users 无本 run 残留', username not in names, username)
        except Exception as exc:  # noqa: BLE001
            print('verify cleanup error:', exc)
        drv.quit()
        with open(os.path.join(ART, 'result.json'), 'w', encoding='utf-8') as fh:
            json.dump(RESULT, fh, ensure_ascii=False, indent=2)
        failed = [r for r in RESULT if not r['ok']]
        print('\n==== %d checks, %d failed ====' % (len(RESULT), len(failed)))
        for r in failed:
            print('FAIL:', r['name'], r['detail'])


if __name__ == '__main__':
    main()
