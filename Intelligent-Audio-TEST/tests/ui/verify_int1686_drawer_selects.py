# -*- coding: utf-8 -*-
"""INT-1686 第三轮复测：抽屉内三处同根因 Select（批量设备 / 标签设备 / 音频行播放设备）+ 评估策略选择。

范围：实施者本轮「同根因顺带收口」的四处中，浏览器可实测的三处（抽屉内）+ 评估策略一处。
判据：选完后触发器文案是名称，不是原始 value（设备 id / 策略 id）。
只选择不保存（抽屉「取消」关闭），不做任何数据写入。

用法：
  set REACT_BASE=http://127.0.0.1:15296 && set RUN_TAG=fix && python tests/ui/verify_int1686_drawer_selects.py
  set REACT_BASE=http://127.0.0.1:15173 && set RUN_TAG=old && python tests/ui/verify_int1686_drawer_selects.py
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
ART = os.path.join(HERE, 'artifacts', 'int1686_drawer_' + RUN_TAG)
os.makedirs(ART, exist_ok=True)

LOGIN_USER = os.environ.get('IAT_LOGIN_USER', '接线测试_admin')
LOGIN_PASS = os.environ.get('IAT_LOGIN_PASS', 'JieXianTest@2026')
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
    method: cfg.method || 'GET',
    headers: headers,
    body: cfg.body ? JSON.stringify(cfg.body) : undefined,
  });
  const t = await r.text();
  return {status: r.status, body: t};
})()
"""

STRATEGY_NAME = '接线测试_验收策略1686'


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
    drv.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)


def text_of(drv, el):
    return (drv.execute_script('return arguments[0].textContent || "";', el) or '').strip()


def is_uuid(s):
    return bool(re.fullmatch(r'[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', s or ''))


def visible(el):
    try:
        return drv_rect(el)
    except Exception:  # noqa: BLE001
        return False


def drv_rect(el):
    r = el.rect
    return r.get('width', 0) > 0 and r.get('height', 0) > 0


def api(drv, path, method='GET', body=None):
    res = drv.execute_script(API_JS, {'path': path, 'method': method, 'body': body})
    try:
        payload = json.loads(res.get('body') or '{}')
    except ValueError:
        payload = {'raw': res.get('body')}
    return {'status': res.get('status'), 'json': payload}


def strategy_list(drv):
    res = api(drv, '/api/v1/evaluation-strategies?per_page=200')
    data = res['json'].get('data', res['json']) if isinstance(res['json'], dict) else {}
    items = data.get('items') if isinstance(data, dict) else None
    return res['status'], items or []


def ensure_strategy(drv):
    """真实库无策略时建一条临时策略（收尾删除）；返回 (id, name, created)。"""
    status, items = strategy_list(drv)
    log('strategies: status=%r count=%d' % (status, len(items)))
    for it in items:
        if it.get('name') == STRATEGY_NAME:
            log('reuse strategy id=%r' % it.get('id'))
            return str(it.get('id')), STRATEGY_NAME, False
    if items:
        # 已有其它策略：直接用第一条，无需写库
        log('use existing strategy %r id=%r' % (items[0].get('name'), items[0].get('id')))
        return str(items[0].get('id')), items[0].get('name'), False
    payload = {
        'name': STRATEGY_NAME,
        'description': 'INT-1686 验收临时策略（收尾删除）',
        'algorithm_type': None,
        'enabled': True,
        'config': {'dimensions': [], 'background_noise': None},
    }
    res = api(drv, '/api/v1/evaluation-strategies', 'POST', payload)
    log('create strategy: status=%r body=%r' % (res['status'], str(res['json'])[:200]))
    data = res['json'].get('data', res['json']) if isinstance(res['json'], dict) else {}
    sid = data.get('id') if isinstance(data, dict) else None
    if not sid:
        raise SystemExit('strategy create failed: %r' % (res,))
    return str(sid), STRATEGY_NAME, True


def delete_strategy(drv, sid, created):
    """收尾：优先 API 删除，删不掉就报告（由外层用 SQL 兜底）。"""
    if not created:
        return {'skipped': 'not created by this run'}
    res = api(drv, '/api/v1/evaluation-strategies/' + str(sid), 'DELETE')
    _, items = strategy_list(drv)
    still = [it.get('name') for it in items if it.get('name') == STRATEGY_NAME]
    return {'delete_status': res['status'], 'still_listed': still}


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


def open_trigger_in(drv, root):
    """在 root 内点开第一个可见 combobox，返回触发器元素。"""
    for t in root.find_elements(By.CSS_SELECTOR, '[role="combobox"]'):
        if drv_rect(t) and t.is_enabled():
            js_click(drv, t)
            WebDriverWait(drv, 20).until(
                lambda d: d.find_elements(By.CSS_SELECTOR, '[role="option"]'))
            time.sleep(0.6)
            return t
    raise SystemExit('no enabled combobox in root')


def pick_option(drv, needle, index=None):
    def find(d):
        opts = [o for o in d.find_elements(By.CSS_SELECTOR, '[role="option"]') if drv_rect(o)]
        if index is not None:
            return opts[index] if len(opts) > index else None
        for o in opts:
            if needle in text_of(d, o):
                return o
        return None
    opt = WebDriverWait(drv, 20).until(find)
    picked = text_of(drv, opt)
    js_click(drv, opt)
    time.sleep(1.0)
    return picked


def open_case_page(drv):
    last_body = ''
    for attempt in range(3):
        drv.get(BASE + '/testcases/by-group')
        WebDriverWait(drv, 90).until(lambda d: '用例' in body_text(d))
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


def open_drawer(drv):
    btns = WebDriverWait(drv, 30).until(
        lambda d: d.find_elements(By.CSS_SELECTOR, "button[aria-label='编辑用例']"))
    js_click(drv, btns[0])
    WebDriverWait(drv, 30).until(
        lambda d: d.find_elements(By.CSS_SELECTOR, '[role="dialog"]'))
    time.sleep(2.5)
    return top_dialog(drv)


def top_dialog(drv):
    ds = drv.execute_script(
        "return Array.from(document.querySelectorAll('[role=\\\"dialog\\\"]'))"
        ".filter(d => { const s = getComputedStyle(d);"
        " return s.display !== 'none' && s.visibility !== 'hidden'"
        " && d.getBoundingClientRect().width > 0; });"
    )
    return ds[-1] if ds else None


def click_tab(drv, sheet, label):
    for t in sheet.find_elements(By.CSS_SELECTOR, '[role="tab"]'):
        if text_of(drv, t) == label:
            js_click(drv, t)
            time.sleep(1.5)
            return
    raise SystemExit('tab not found: ' + label)


def click_button_text(drv, root, label):
    for b in root.find_elements(By.TAG_NAME, 'button'):
        try:
            if text_of(drv, b) == label and drv_rect(b):
                js_click(drv, b)
                time.sleep(1.2)
                return b
        except Exception:  # noqa: BLE001
            continue
    raise SystemExit('button not found: ' + label)


def main():
    ev = {'base': BASE, 'run_tag': RUN_TAG}
    drv = make_driver()
    strategy_state = None
    try:
        login(drv)
        try:
            sid, sname, created = ensure_strategy(drv)
            strategy_state = (sid, created)
            ev['strategy_fixture'] = {'id': sid, 'name': sname, 'created': created}
        except SystemExit as exc:
            ev['strategy_fixture_error'] = str(exc)
            log('strategy fixture error: %s' % exc)
        open_case_page(drv)
        drawer = open_drawer(drv)
        click_tab(drv, drawer, '音频列表')
        time.sleep(1.5)
        shot(drv, '01_drawer_audio_step_light')

        # ---------- A. 工具栏「批量设备」----------
        drawer = top_dialog(drv)
        click_button_text(drv, drawer, '批量设备')
        WebDriverWait(drv, 30).until(
            lambda d: any('批量设置播放设备' in text_of(d, x)
                          for x in d.find_elements(By.CSS_SELECTOR, '[role="dialog"]')))
        panel = top_dialog(drv)
        open_trigger_in(drv, panel)
        pick_option(drv, DEVICE_NAME)
        panel = top_dialog(drv)
        trig = panel.find_element(By.CSS_SELECTOR, '[role="combobox"]')
        shown = text_of(drv, trig)
        ev['batch_device_panel_trigger'] = shown
        ev['batch_device_panel_pass'] = DEVICE_NAME in shown and shown.strip() != DEVICE_ID
        log('抽屉批量设备触发器 = %r' % shown)
        shot(drv, '02_drawer_batch_device_light')
        set_dark(drv, True)
        shot(drv, '03_drawer_batch_device_dark')
        set_dark(drv, False)
        click_button_text(drv, panel, '取消')
        time.sleep(1.0)

        # ---------- B. 工具栏「标签设备」----------
        drawer = top_dialog(drv)
        click_button_text(drv, drawer, '标签设备')
        WebDriverWait(drv, 30).until(
            lambda d: any('标签设备' in text_of(d, x)
                          for x in d.find_elements(By.CSS_SELECTOR, '[role="dialog"]')))
        panel = top_dialog(drv)
        combos = [c for c in panel.find_elements(By.CSS_SELECTOR, '[role="combobox"]') if drv_rect(c)]
        if len(combos) < 2:
            raise SystemExit('标签设备面板 combobox 数量异常: %d' % len(combos))
        js_click(drv, combos[1])
        WebDriverWait(drv, 20).until(lambda d: d.find_elements(By.CSS_SELECTOR, '[role="option"]'))
        time.sleep(0.6)
        pick_option(drv, DEVICE_NAME)
        panel = top_dialog(drv)
        combos = [c for c in panel.find_elements(By.CSS_SELECTOR, '[role="combobox"]') if drv_rect(c)]
        shown = text_of(drv, combos[1])
        ev['tag_device_panel_trigger'] = shown
        ev['tag_device_panel_pass'] = DEVICE_NAME in shown and shown.strip() != DEVICE_ID
        log('抽屉标签设备-目标设备触发器 = %r' % shown)
        shot(drv, '04_drawer_tag_device_light')
        set_dark(drv, True)
        shot(drv, '05_drawer_tag_device_dark')
        set_dark(drv, False)
        click_button_text(drv, panel, '取消')
        time.sleep(1.0)

        # ---------- C. 音频行播放设备 ----------
        drawer = top_dialog(drv)
        step_body = drawer.find_element(By.CSS_SELECTOR, "[data-testid='case-step-body']")
        row_combo = None
        for c in step_body.find_elements(By.CSS_SELECTOR, '[role="combobox"]'):
            if drv_rect(c) and c.is_enabled():
                row_combo = c
                break
        if row_combo is None:
            ev['audio_row_trigger'] = None
            ev['audio_row_pass'] = None
            log('音频行无可用设备 Select（可能本用例无音频行）')
        else:
            js_click(drv, row_combo)
            WebDriverWait(drv, 20).until(lambda d: d.find_elements(By.CSS_SELECTOR, '[role="option"]'))
            time.sleep(0.6)
            pick_option(drv, DEVICE_NAME)
            drawer = top_dialog(drv)
            step_body = drawer.find_element(By.CSS_SELECTOR, "[data-testid='case-step-body']")
            shown = text_of(drv, step_body.find_elements(By.CSS_SELECTOR, '[role="combobox"]')[0])
            ev['audio_row_trigger'] = shown
            ev['audio_row_pass'] = DEVICE_NAME in shown and shown.strip() != DEVICE_ID
            log('音频行播放设备触发器 = %r' % shown)
            shot(drv, '06_drawer_audio_row_light')
            set_dark(drv, True)
            shot(drv, '07_drawer_audio_row_dark')
            set_dark(drv, False)

        # ---------- D. 评估策略「选择策略」----------
        drawer = top_dialog(drv)
        # 抽屉正文是可滚动容器：滚到底再展开「评估策略」折叠节
        drv.execute_script(
            "const ds=[...document.querySelectorAll('[role=\"dialog\"]')].filter(d=>d.getBoundingClientRect().width>0);"
            "const root=ds[ds.length-1]; if(!root) return;"
            "const cands=[...root.querySelectorAll('*')].filter(e=>e.scrollHeight-e.clientHeight>200);"
            "cands.forEach(e=>{e.scrollTop=e.scrollHeight;});"
        )
        time.sleep(1.0)
        opened = False
        for el in drawer.find_elements(By.XPATH, ".//button[starts-with(normalize-space(.),'评估策略')]"):
            try:
                if drv_rect(el):
                    js_click(drv, el)
                    time.sleep(1.2)
                    opened = True
                    break
            except Exception:  # noqa: BLE001
                continue
        ev['strategy_section_opened'] = opened
        if opened:
            try:
                radio = WebDriverWait(drv, 15).until(
                    lambda d: d.find_elements(
                        By.XPATH,
                        ".//label[contains(normalize-space(.),'引用已有策略')]//input"))
                js_click(drv, radio[0])
                time.sleep(1.5)
                drawer = top_dialog(drv)
                # 「选择策略」标签所在的表单行内的 combobox（避免误选别处的 Select）
                sel_combo = WebDriverWait(drv, 15).until(
                    lambda d: d.find_elements(
                        By.XPATH,
                        ".//*[normalize-space(text())='选择策略']/ancestor::div[1]//*[@role='combobox']"))
                sel = sel_combo[0]
                drv.execute_script(
                    'arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', sel)
                time.sleep(1.0)
                picked_label = pick_option(drv, STRATEGY_NAME)
                time.sleep(0.8)
                drawer = top_dialog(drv)
                sel_combo = drawer.find_elements(
                    By.XPATH,
                    ".//*[normalize-space(text())='选择策略']/ancestor::div[1]//*[@role='combobox']")
                shown = text_of(drv, sel_combo[0]) if sel_combo else ''
                ev['strategy_option_picked'] = picked_label
                ev['strategy_trigger'] = shown
                ev['strategy_pass'] = (STRATEGY_NAME in shown) and (not is_uuid(shown))
                log('评估策略触发器 = %r (picked=%r)' % (shown, picked_label))
                shot(drv, '08_drawer_strategy_light')
                set_dark(drv, True)
                shot(drv, '09_drawer_strategy_dark')
                set_dark(drv, False)
            except Exception as exc:  # noqa: BLE001
                ev['strategy_error'] = repr(exc)
                log('strategy check error: %r' % (exc,))

        # 关闭抽屉，不保存
        try:
            click_button_text(drv, top_dialog(drv), '取消')
        except Exception:  # noqa: BLE001
            pass
        if strategy_state:
            ev['strategy_teardown'] = delete_strategy(drv, strategy_state[0], strategy_state[1])
            log('strategy teardown: %r' % ev['strategy_teardown'])
            strategy_state = None
        ev['summary'] = {
            'batch_device_panel': ev.get('batch_device_panel_pass'),
            'tag_device_panel': ev.get('tag_device_panel_pass'),
            'audio_row': ev.get('audio_row_pass'),
            'strategy': ev.get('strategy_pass'),
        }
        log('SUMMARY ' + json.dumps(ev['summary'], ensure_ascii=False))
    finally:
        if strategy_state:
            try:
                ev['strategy_teardown'] = delete_strategy(drv, strategy_state[0], strategy_state[1])
                log('strategy teardown (finally): %r' % ev['strategy_teardown'])
            except Exception as exc:  # noqa: BLE001
                ev['strategy_teardown_error'] = repr(exc)
                log('strategy teardown failed: %r' % (exc,))
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
