# -*- coding: utf-8 -*-
"""INT-1686 验收：批量「调整分组 / 用例专属参数」Select 闭合态文案 + 算法参数字段去重。

覆盖：
  1. 批量调整分组：选完目标分组后触发器显示分组名（不显示分组 UUID），浅/深截图；
  2. 批量设置用例专属参数：选完算法后触发器显示算法中文名（不显示算法 type 码），浅/深截图；
  3. 算法参数表单：schema 同时给顶层 fields 与 groups[].fields 时同一字段只出现一个控件
     （批量窗 + 用例抽屉各一次）；
  4. 上述两次 schema 请求的 Network 记录。

前端：本 worktree `pnpm dev --port 5361 -c <临时代理配置>`（/api → docker 网关 15000，
库 intelligent_audio_test）。用法：`python tests/ui/verify_int1686_selects.py`。
需要临时算法定义 `wire_test_int1686`（带 case_params，见卡内交付说明），实测后删除。
"""
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:5361')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1686')
os.makedirs(ART, exist_ok=True)

LOGIN_USER = os.environ.get('IAT_LOGIN_USER', '接线测试_admin')
LOGIN_PASS = os.environ.get('IAT_LOGIN_PASS', 'JieXianTest@2026')

TEST_ALGO_TYPE = 'wire_test_int1686'
TEST_ALGO_NAME = '接线测试_参数去重算法'
DUP_FIELD_LABEL = '接线测试阈值'
# 音频上传生成（3 条真实用例，展开快）
GROUP_ID = 'dec6503f-a86e-4b5d-b60e-7f4801b82325'

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

FETCH_PATCH = r"""
window.__fetchLog = [];
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const init2 = init || {};
  const method = (init2.method || 'GET').toUpperCase();
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
    log('shot -> ' + name + '.png')
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


def login(drv):
    for attempt in range(3):
        drv.get(BASE + '/login')
        time.sleep(3)
        res = drv.execute_script(LOGIN_JS, LOGIN_PASS, LOGIN_USER)
        if res.get('token'):
            log('login ok user=%s' % (res.get('user') or {}).get('username'))
            return res
        log('login attempt %d failed' % (attempt + 1))
        time.sleep(2)
    raise SystemExit('login failed')


def dialogs(drv):
    return drv.find_elements(By.CSS_SELECTOR, '[role="dialog"]')


def top_dialog(drv):
    ds = dialogs(drv)
    return ds[-1] if ds else None


def wait_text(drv, needle, timeout=60):
    WebDriverWait(drv, timeout).until(lambda d: needle in body_text(d))


def open_case_page(drv, group_id=None):
    """用例页默认按分组视图且分组卡收起：URL 直链「分组=<id>」只渲染该分组，再展开组头出用例卡。"""
    url = BASE + '/testcases/by-group'
    if group_id:
        url += '?group=' + group_id
    drv.get(url)
    wait_text(drv, '用例', 90)
    rows = []
    deadline = time.time() + 90
    while time.time() < deadline:
        rows = [e for e in drv.find_elements(By.CSS_SELECTOR, "div[class*='cursor-pointer']")
                if '条' in text_of(drv, e)]
        if rows:
            break
        time.sleep(2)
    if not rows:
        raise SystemExit('no group row; body=%r' % body_text(drv)[:400])
    js_click(drv, rows[0])
    log('expanded group: %r' % text_of(drv, rows[0])[:24])
    WebDriverWait(drv, 120).until(
        lambda d: d.find_elements(By.CSS_SELECTOR, '[aria-label^="选择 "]'))
    time.sleep(1.0)


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


def pick_option(drv, dlg, name):
    trig = dlg.find_element(By.CSS_SELECTOR, '[role="combobox"]')
    js_click(drv, trig)
    time.sleep(0.6)
    opt = WebDriverWait(drv, 20).until(
        lambda d: next(
            (o for o in d.find_elements(By.CSS_SELECTOR, '[role="option"]')
             if name in text_of(d, o)), None)
    )
    js_click(drv, opt)
    time.sleep(1.0)
    return trig


def count_text(drv, dlg, needle):
    return len(dlg.find_elements(
        By.XPATH, ".//*[normalize-space(text())='%s']" % needle))


def logs(drv):
    """Network 证据：本页注入的 fetch 打点。"""
    entries = drv.execute_script('return window.__fetchLog || [];') or []
    return [e for e in entries if '/api/v1' in e.get('url', '')]


def main():
    ev = {}
    drv = make_driver()
    try:
        login(drv)
        open_case_page(drv, GROUP_ID)
        select_two_cases(drv)

        # ---------- 1. 批量调整分组 ----------
        dlg = open_bulk(drv, '批量调整分组')
        group_names = [text_of(drv, o) for o in dlg.find_elements(By.CSS_SELECTOR, '[role="option"]')]
        log('group options: %d' % len(group_names))
        trig = pick_option(drv, dlg, '')  # 第一个选项（真实分组）
        trig = dlg.find_element(By.CSS_SELECTOR, '[role="combobox"]')
        shown = text_of(drv, trig)
        ev['group_trigger'] = shown
        log('group trigger closed text = %r' % shown)
        uuid_like = len(shown) == 36 and shown.count('-') == 4
        ev['group_trigger_is_uuid'] = uuid_like
        shot(drv, '01_batch_group_light')
        set_dark(drv, True)
        shot(drv, '02_batch_group_dark')
        set_dark(drv, False)
        close_top_dialog(drv)

        # ---------- 2/3. 批量设置专属参数 ----------
        dlg = open_bulk(drv, '批量设置专属参数')
        trig = pick_option(drv, dlg, TEST_ALGO_NAME)
        shown = text_of(drv, trig)
        ev['algo_trigger'] = shown
        log('algo trigger closed text = %r' % shown)
        wait_text(drv, DUP_FIELD_LABEL, 60)
        time.sleep(0.5)
        n = count_text(drv, dlg, DUP_FIELD_LABEL)
        n_inputs = len(dlg.find_elements(By.CSS_SELECTOR, 'input[type="number"]'))
        ev['batch_dup_count'] = n
        ev['batch_number_inputs'] = n_inputs
        log('batch dialog field %r count = %d, number inputs = %d'
            % (DUP_FIELD_LABEL, n, n_inputs))
        net = [e for e in logs(drv) if 'form-schema' in e['url']]
        ev['form_schema_requests'] = [
            {'url': e['url'], 'status': e['status'],
             'hasTopFields': '"fields"' in (e.get('resBody') or ''),
             'hasGroups': '"groups"' in (e.get('resBody') or '')}
            for e in net
        ]
        shot(drv, '03_batch_params_light')
        set_dark(drv, True)
        shot(drv, '04_batch_params_dark')
        set_dark(drv, False)
        close_top_dialog(drv)

        # ---------- 4. 用例抽屉「算法参数」步骤同一字段只出现一个控件 ----------
        edit_btn = WebDriverWait(drv, 30).until(
            lambda d: d.find_elements(By.CSS_SELECTOR, "button[aria-label='编辑用例']"))
        js_click(drv, edit_btn[0])
        WebDriverWait(drv, 30).until(
            lambda d: d.find_elements(By.CSS_SELECTOR, '[role="dialog"]'))
        time.sleep(2.0)
        drawer = drv.find_elements(By.CSS_SELECTOR, '[role="dialog"]')[-1]
        algo_sel = drawer.find_element(
            By.XPATH, ".//*[normalize-space(text())='关联算法']/ancestor::section[1]//*[@role='combobox']")
        js_click(drv, algo_sel)
        time.sleep(0.6)
        opt = WebDriverWait(drv, 20).until(
            lambda d: next((o for o in d.find_elements(By.CSS_SELECTOR, '[role="option"]')
                            if TEST_ALGO_NAME in text_of(d, o)), None))
        js_click(drv, opt)
        wait_text(drv, DUP_FIELD_LABEL, 60)
        time.sleep(0.8)
        drawer = drv.find_elements(By.CSS_SELECTOR, '[role="dialog"]')[-1]
        ev['drawer_dup_count'] = count_text(drv, drawer, DUP_FIELD_LABEL)
        log('drawer field %r count = %d'
            % (DUP_FIELD_LABEL, ev['drawer_dup_count']))
        net2 = [e for e in logs(drv) if 'form-schema' in e['url']]
        ev['form_schema_requests_drawer'] = [
            {'url': e['url'], 'status': e['status'],
             'hasTopFields': '"fields"' in (e.get('resBody') or ''),
             'hasGroups': '"groups"' in (e.get('resBody') or '')}
            for e in net2[-1:]
        ]
        shot(drv, '05_drawer_params_light')
        set_dark(drv, True)
        shot(drv, '06_drawer_params_dark')
        set_dark(drv, False)
        close_top_dialog(drv)  # 抽屉是 role=dialog，取消关闭（不保存，真实用例不变）

        json.dump(ev, open(os.path.join(ART, 'evidence_batch.json'), 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=2)
        log(json.dumps(ev, ensure_ascii=False))
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
