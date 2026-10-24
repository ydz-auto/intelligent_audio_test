# -*- coding: utf-8 -*-
"""INT-1686 验收（测试工程师独立脚本）：批量三窗 Select 闭合态 + 算法参数字段去重。

覆盖卡内验收 + 追加项：
  1. 批量调整分组：选完目标分组后触发器显示分组名，不显示 36 位 UUID（浅/深截图）；
  2. 批量设置专属参数：选完算法后触发器显示算法中文名（非 type 码），
     schema 同时含顶层 fields 与 groups[].fields 时同一字段只出现一个控件（浅/深截图）；
  3. 用例抽屉「算法参数」步骤同一字段只出现一个控件（浅/深截图）；
  4. 追加项：批量设置播放设备窗选完设备后触发器显示设备名，不显示设备 id（浅/深截图）；
  5. Network：form-schema 响应同时含 fields 与 groups。

夹具：临时算法定义 `wire_test_int1686b`（2 个 case_params，status=online），
收尾 DELETE 并核对 options / form-schema 均查不到。

用法（固定跑 docker 后端 + 旁路前端）：
  set REACT_BASE=http://127.0.0.1:15296 && set RUN_TAG=fix && python -I tests/ui/verify_int1686_accept.py
  set REACT_BASE=http://127.0.0.1:15173 && set RUN_TAG=old && python -I tests/ui/verify_int1686_accept.py
"""
import json
import os
import re
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15296')
RUN_TAG = os.environ.get('RUN_TAG', 'fix')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1686_accept_' + RUN_TAG)
os.makedirs(ART, exist_ok=True)

LOGIN_USER = os.environ.get('IAT_LOGIN_USER', '接线测试_admin')
LOGIN_PASS = os.environ.get('IAT_LOGIN_PASS', 'JieXianTest@2026')

ALGO_TYPE = 'wire_test_int1686b'
ALGO_NAME = '接线测试_验收去重算法1686b'
DUP_FIELD_LABEL = '接线测试阈值'
GROUP_ID = 'dec6503f-a86e-4b5d-b60e-7f4801b82325'  # 音频上传生成（3 条真实用例）
DEVICE_NAME = '设备正左侧（1m-90°）'
DEVICE_ID = '8'

LOGIN_JS = r"""
return (async () => {
  const keyResp = await fetch('/api/v1/auth/login/encryption-key').then(r=>r.json());
  const d = keyResp.data || keyResp;
  if(!d.enabled) return {step:'disabled'};
  const pem = d.public_key.replace(/-----[^-]+-----/g,'').replace(/\s+/g,'');
  const bin = Uint8Array.from(atob(pem), c=>c.charCodeAt(0));
  const key = await crypto.subtle.importKey('spki', bin, {name:'RSA-OAEP', hash:'SHA-256'}, false, ['encrypt']);
  const enc = await crypto.subtle.encrypt({name:'RSA-OAEP'}, key, new TextEncoder().encode(arguments[0]));
  const b64 = btoa(String.fromCharCode(...new Uint8Array(enc)));
  const body = new URLSearchParams({username: arguments[1], password_encrypted: b64, encryption_key_id: d.kid});
  const r = await fetch('/api/v1/auth/login', {method:'POST', headers:{'Content-Type':'application/x-www-form-urlencoded'}, body});
  const txt = await r.text();
  let j = {}; try { j = JSON.parse(txt); } catch(e) {}
  if (r.ok && j.access_token) localStorage.setItem('iatp:auth:token:v1', j.access_token);
  return {status: r.status, token: j.access_token || null, user: j.user || null};
})()
"""

API_JS = r"""
const cfg = arguments[0];
return (async () => {
  const token = localStorage.getItem('iatp:auth:token:v1');
  const headers = {};
  if (token) headers.Authorization = 'Bearer ' + token;
  if (cfg.body) headers['Content-Type'] = 'application/json';
  const r = await fetch(cfg.path, {
    method: cfg.method,
    headers: headers,
    body: cfg.body ? JSON.stringify(cfg.body) : undefined,
  });
  const t = await r.text();
  return {status: r.status, body: t};
})()
"""

FETCH_PATCH = r"""
window.__fetchLog = [];
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = ((init || {}).method || 'GET').toUpperCase();
  const res = await __origFetch.apply(this, arguments);
  const entry = {url: url, method: method, status: res.status, t: Date.now()};
  if (url.indexOf('/api/v1') !== -1) {
    try { entry.resBody = await res.clone().text(); } catch (e) {}
  }
  window.__fetchLog.push(entry);
  return res;
};
"""


def log(msg):
    print(msg, flush=True)


def make_driver():
    o = Options()
    o.binary_location = CHROME_BINARY
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1050')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--force-prefers-reduced-motion')
    o.add_argument('--disable-dev-shm-usage')
    import winreg
    major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:  # noqa: BLE001
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
                    continue
        same = [p for ver, p in cands if ver and ver[0] == major]
        if same:
            exe = max(same)
    d = webdriver.Chrome(options=o, service=Service(executable_path=exe) if exe else Service())
    d.set_page_load_timeout(60)
    d.set_script_timeout(120)
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    return d


def shot(drv, name):
    path = os.path.join(ART, name + '.png')
    drv.save_screenshot(path)
    log('shot -> ' + os.path.basename(path))
    return path


def set_dark(drv, dark):
    drv.execute_script(
        "document.documentElement.classList.remove('light','dark');"
        "document.documentElement.classList.add(arguments[0]);"
        "document.documentElement.style.colorScheme = arguments[0];",
        'dark' if dark else 'light',
    )
    time.sleep(1.2)


def body_text(drv):
    return drv.execute_script('return document.body ? document.body.innerText : "";') or ''


def js_click(drv, el):
    drv.execute_script(
        'arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el
    )


def text_of(drv, el):
    return (drv.execute_script('return arguments[0].textContent || "";', el) or '').strip()


def is_uuid(s):
    return bool(re.fullmatch(r'[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', s or ''))


def api(drv, path, method='GET', body=None):
    res = drv.execute_script(API_JS, {'path': path, 'method': method, 'body': body})
    try:
        payload = json.loads(res.get('body') or '{}')
    except ValueError:
        payload = {'raw': res.get('body')}
    return {'status': res.get('status'), 'json': payload}


def data_of(result):
    """取 api() 结果里的 data 段（兼容直接给已解析 payload 的情况）。"""
    if not isinstance(result, dict):
        return {}
    j = result.get('json')
    if not isinstance(j, dict):
        j = result
    return j.get('data', j)


def login(drv):
    for attempt in range(3):
        drv.get(BASE + '/login')
        time.sleep(3)
        res = drv.execute_script(LOGIN_JS, LOGIN_PASS, LOGIN_USER)
        if res.get('token'):
            log('login ok user=%s' % (res.get('user') or {}).get('username'))
            return res
        log('login attempt %d failed: %r' % (attempt + 1, res))
        time.sleep(2)
    raise SystemExit('login failed')


def visible_dialogs(drv):
    return drv.execute_script(
        "return Array.from(document.querySelectorAll('[role=\\\"dialog\\\"]'))"
        ".filter(d => { const s = getComputedStyle(d);"
        " return s.display !== 'none' && s.visibility !== 'hidden'"
        " && d.getBoundingClientRect().width > 0; });"
    )


def top_dialog(drv):
    ds = visible_dialogs(drv)
    return ds[-1] if ds else None


def wait_text(drv, needle, timeout=60):
    WebDriverWait(drv, timeout).until(lambda d: needle in body_text(d))


def open_case_page(drv):
    """按分组视图展开第一个分组（首屏偶发瞬时空态，重试 3 次）。"""
    last_body = ''
    for attempt in range(3):
        drv.get(BASE + '/testcases/by-group')
        wait_text(drv, '用例', 90)
        rows = []
        deadline = time.time() + 60
        while time.time() < deadline:
            rows = [e for e in drv.find_elements(By.CSS_SELECTOR, "div[class*='cursor-pointer']")
                    if '条' in text_of(drv, e)]
            if rows:
                break
            time.sleep(2)
        if rows:
            target = rows[0]
            for r in rows:
                if '音频上传生成' in text_of(drv, r):
                    target = r
                    break
            js_click(drv, target)
            log('expanded group: %r' % text_of(drv, target)[:24])
            WebDriverWait(drv, 240).until(
                lambda d: d.find_elements(By.CSS_SELECTOR, '[aria-label^="选择 "]'))
            time.sleep(1.0)
            return
        last_body = body_text(drv)[:300]
        log('case page empty (attempt %d), retry' % (attempt + 1))
        time.sleep(3)
    raise SystemExit('no group row; body=%r' % last_body)


def select_two_cases(drv):
    boxes = drv.find_elements(By.CSS_SELECTOR, '[aria-label^="选择 "]')
    if not boxes:
        raise SystemExit('no case checkboxes')
    for box in boxes[:2]:
        js_click(drv, box)
        time.sleep(0.4)
    time.sleep(1.0)
    log('selected %d case(s)' % min(len(boxes), 2))


def bulk_button(drv, label):
    for b in drv.find_elements(By.TAG_NAME, 'button'):
        try:
            if text_of(drv, b) == label and b.is_displayed():
                return b
        except Exception:  # noqa: BLE001
            continue
    raise SystemExit('bulk button not found: ' + label)


def open_bulk(drv, label):
    js_click(drv, bulk_button(drv, label))
    WebDriverWait(drv, 30).until(lambda d: top_dialog(d) is not None)
    time.sleep(0.8)
    return top_dialog(drv)


def close_top_dialog(drv):
    d = top_dialog(drv)
    if d is None:
        return
    for b in d.find_elements(By.TAG_NAME, 'button'):
        if text_of(drv, b) == '取消':
            js_click(drv, b)
            break
    else:
        drv.execute_script("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));")
    time.sleep(1.0)


def open_trigger(drv, dlg):
    trig = dlg.find_element(By.CSS_SELECTOR, '[role="combobox"]')
    js_click(drv, trig)
    WebDriverWait(drv, 20).until(
        lambda d: d.find_elements(By.CSS_SELECTOR, '[role="option"]'))
    time.sleep(0.5)
    return trig


def pick_option(drv, needle):
    def find(d):
        for o in d.find_elements(By.CSS_SELECTOR, '[role="option"]'):
            if needle in text_of(d, o):
                return o
        return None
    opt = WebDriverWait(drv, 20).until(find)
    js_click(drv, opt)
    time.sleep(1.0)


def count_exact_text(drv, root, needle):
    return len(root.find_elements(By.XPATH, ".//*[normalize-space(text())='%s']" % needle))


def logs(drv):
    entries = drv.execute_script('return window.__fetchLog || [];') or []
    return [e for e in entries if '/api/v1' in e.get('url', '')]


def ensure_fixture(drv):
    """夹具复用优先：已存在且在线就直接用（type 有唯一约束，软删后不能重建同名）。"""
    cur = api(drv, '/api/v1/algorithm/definitions/' + ALGO_TYPE)
    exists = cur['status'] == 200 and bool(data_of(cur))
    create_status = None
    if not exists:
        payload = {
            'type': ALGO_TYPE,
            'name': ALGO_NAME,
            'status': 'online',
            'description': 'INT-1686 验收临时算法（收尾删除）',
            'case_params': [
                {
                    'param_code': 'wire1686b_threshold',
                    'param_name': DUP_FIELD_LABEL,
                    'label': DUP_FIELD_LABEL,
                    'param_type': 'number',
                    'default_value': '0.5',
                    'ui_order': 1,
                    'scope': 'common',
                    'required': False,
                },
                {
                    'param_code': 'wire1686b_flag',
                    'param_name': '接线测试开关',
                    'label': '接线测试开关',
                    'param_type': 'boolean',
                    'default_value': 'false',
                    'ui_order': 2,
                    'scope': 'common',
                    'required': False,
                },
            ],
        }
        res = api(drv, '/api/v1/algorithm/definitions', 'POST', payload)
        create_status = res['status']
        log('create fixture: status=%s body=%r' % (res['status'], str(res['json'])[:300]))
    else:
        log('fixture exists, reuse: %r' % (data_of(cur) or {}).get('name'))
    # 新建定义后 gRPC 侧 schema 读取有短暂滞后：轮询到 fields 非空（必要时 reload 一次）
    schema = {}
    for attempt in range(12):
        schema = api(drv, '/api/v1/algorithm/form-schema/' + ALGO_TYPE)
        data = data_of(schema) or {}
        log('schema poll #%d status=%r fields=%d'
            % (attempt + 1, schema['status'], len(data.get('fields') or [])))
        if data.get('fields'):
            break
        if attempt == 3:
            api(drv, '/api/v1/algorithm/reload', 'POST', {})
        time.sleep(2.5)
    data = data_of(schema) or {}
    fields = data.get('fields') or []
    group_fields = [f for g in (data.get('groups') or []) for f in (g.get('fields') or [])]
    codes_flat = [f.get('fieldCode') for f in fields]
    codes_grouped = [f.get('fieldCode') for f in group_fields]
    ev = {
        'reused': exists,
        'create_status': create_status,
        'schema_status': schema['status'],
        'schema_raw': (schema.get('json') or {}).get('raw', '')[:300],
        'fields': len(fields),
        'groups': len(data.get('groups') or []),
        'group_fields': len(group_fields),
        'codes_flat': codes_flat,
        'codes_grouped': codes_grouped,
        'duplicated_codes': sorted(set(codes_flat) & set(codes_grouped)),
    }
    log('fixture schema: %r' % ev)
    return ev


def teardown_fixture(drv):
    res = api(drv, '/api/v1/algorithm/definitions/' + ALGO_TYPE, 'DELETE')
    schema = api(drv, '/api/v1/algorithm/form-schema/' + ALGO_TYPE)
    opts = api(drv, '/api/v1/algorithm/options')
    opt_list = data_of(opts)
    if isinstance(opt_list, dict):
        opt_list = opt_list.get('items') or opt_list.get('options') or []
    types = []
    for o in opt_list or []:
        if isinstance(o, dict):
            types.append(o.get('value') or o.get('type') or o.get('algorithmType'))
    schema_data = data_of(schema) or {}
    return {
        'delete_status': res['status'],
        'schema_status': schema['status'],
        'schema_fields_after': len(schema_data.get('fields') or []) if isinstance(schema_data, dict) else None,
        'still_in_options': ALGO_TYPE in types,
    }


def main():
    ev = {'base': BASE, 'run_tag': RUN_TAG}
    drv = make_driver()
    try:
        login(drv)
        ev['fixture'] = ensure_fixture(drv)
        open_case_page(drv)
        select_two_cases(drv)

        # ---------- 1. 批量调整分组 ----------
        dlg = open_bulk(drv, '批量调整分组')
        trig = open_trigger(drv, dlg)
        pick_option(drv, '')  # 第一个 = 真实分组
        trig = dlg.find_element(By.CSS_SELECTOR, '[role="combobox"]')
        shown = text_of(drv, trig)
        ev['group_trigger'] = shown
        ev['group_is_uuid'] = is_uuid(shown)
        ev['group_pass'] = (not is_uuid(shown)) and len(shown) > 0
        log('batch group trigger = %r (uuid=%s)' % (shown, is_uuid(shown)))
        shot(drv, '01_batch_group_light')
        set_dark(drv, True)
        shot(drv, '02_batch_group_dark')
        set_dark(drv, False)
        close_top_dialog(drv)

        # ---------- 2. 批量设置专属参数 ----------
        dlg = open_bulk(drv, '批量设置专属参数')
        open_trigger(drv, dlg)
        pick_option(drv, ALGO_NAME)
        time.sleep(0.5)
        dlg = top_dialog(drv)
        trig = dlg.find_element(By.CSS_SELECTOR, '[role="combobox"]')
        shown = text_of(drv, trig)
        wait_text(drv, DUP_FIELD_LABEL, 60)
        time.sleep(0.8)
        dlg = top_dialog(drv)
        ev['algo_trigger'] = shown
        ev['algo_trigger_is_type'] = shown == ALGO_TYPE
        ev['batch_dup_text_count'] = count_exact_text(drv, dlg, DUP_FIELD_LABEL)
        ev['batch_number_inputs'] = len(dlg.find_elements(By.CSS_SELECTOR, 'input[type="number"]'))
        ev['batch_pass'] = (
            shown == ALGO_NAME
            and ev['batch_dup_text_count'] == 1
            and ev['batch_number_inputs'] == 1
        )
        net = [e for e in logs(drv) if 'form-schema' in e['url']]
        ev['schema_network'] = [
            {
                'url': e['url'],
                'status': e['status'],
                'hasTopFields': '"fields"' in (e.get('resBody') or ''),
                'hasGroups': '"groups"' in (e.get('resBody') or ''),
            }
            for e in net[-2:]
        ]
        log('batch algo trigger = %r dupText=%s numInputs=%s'
            % (shown, ev['batch_dup_text_count'], ev['batch_number_inputs']))
        shot(drv, '03_batch_params_light')
        set_dark(drv, True)
        shot(drv, '04_batch_params_dark')
        set_dark(drv, False)
        close_top_dialog(drv)

        # ---------- 3. 批量设置播放设备（追加项）----------
        dlg = open_bulk(drv, '批量设置播放设备')
        # 设备列表加载完成前 combobox 是 disabled（真实库设备接口可能慢，给 120s）
        def device_ready(d):
            dl = top_dialog(d)
            if dl is None:
                return False
            for t in dl.find_elements(By.CSS_SELECTOR, '[role="combobox"]'):
                return t.is_enabled()
            return False

        WebDriverWait(drv, 120).until(device_ready)
        dlg = top_dialog(drv)
        open_trigger(drv, dlg)
        pick_option(drv, DEVICE_NAME)
        dlg = top_dialog(drv)
        trig = dlg.find_element(By.CSS_SELECTOR, '[role="combobox"]')
        shown = text_of(drv, trig)
        ev['device_trigger'] = shown
        ev['device_shows_id'] = shown.strip() == DEVICE_ID
        ev['device_shows_name'] = DEVICE_NAME in shown
        ev['device_pass'] = ev['device_shows_name'] and not ev['device_shows_id']
        log('batch device trigger = %r' % shown)
        shot(drv, '05_batch_device_light')
        set_dark(drv, True)
        shot(drv, '06_batch_device_dark')
        set_dark(drv, False)
        close_top_dialog(drv)

        # ---------- 4. 用例抽屉「算法参数」步骤 ----------
        edit_btn = WebDriverWait(drv, 30).until(
            lambda d: d.find_elements(By.CSS_SELECTOR, "button[aria-label='编辑用例']"))
        js_click(drv, edit_btn[0])
        WebDriverWait(drv, 30).until(lambda d: len(visible_dialogs(d)) > 0)
        time.sleep(2.0)
        drawer = top_dialog(drv)
        algo_sel = drawer.find_element(
            By.XPATH,
            ".//*[normalize-space(text())='关联算法']/ancestor::section[1]//*[@role='combobox']")
        js_click(drv, algo_sel)
        WebDriverWait(drv, 20).until(
            lambda d: d.find_elements(By.CSS_SELECTOR, '[role="option"]'))
        time.sleep(0.5)
        pick_option(drv, ALGO_NAME)
        wait_text(drv, DUP_FIELD_LABEL, 60)
        time.sleep(1.0)
        drawer = top_dialog(drv)
        ev['drawer_dup_text_count'] = count_exact_text(drv, drawer, DUP_FIELD_LABEL)
        ev['drawer_number_inputs'] = len(drawer.find_elements(By.CSS_SELECTOR, 'input[type="number"]'))
        # 抽屉里还有别的 number 输入（声压等），判据取本字段标签出现次数
        ev['drawer_pass'] = ev['drawer_dup_text_count'] == 1
        log('drawer dupText=%s numInputs=%s'
            % (ev['drawer_dup_text_count'], ev['drawer_number_inputs']))
        shot(drv, '07_drawer_params_light')
        set_dark(drv, True)
        shot(drv, '08_drawer_params_dark')
        set_dark(drv, False)
        close_top_dialog(drv)  # 不保存

        if os.environ.get('TEARDOWN', '1') != '0':
            ev['teardown'] = teardown_fixture(drv)
            log('teardown: %r' % ev['teardown'])
        else:
            log('teardown skipped (TEARDOWN=0)')
        ev['summary'] = {
            'group': ev.get('group_pass'),
            'batch_algo': ev.get('batch_pass'),
            'batch_device': ev.get('device_pass'),
            'drawer': ev.get('drawer_pass'),
        }
        log('SUMMARY ' + json.dumps(ev['summary'], ensure_ascii=False))
    finally:
        try:
            drv.quit()
        except Exception:  # noqa: BLE001
            pass
        out = os.path.join(ART, 'evidence.json')
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(ev, f, ensure_ascii=False, indent=2)
        log('evidence -> ' + out)


if __name__ == '__main__':
    main()
