# -*- coding: utf-8 -*-
"""INT-2191 测试工程师浏览器验收（导出 504 修复）。

两个模式：
  success : 连 15173（反代 300s，含 INT-2200），走导出弹窗「全量」范围 → 预览条数
            → 开始导出 → 断言成功 toast + 实际下载的 zip 内 testcases.json 条数。
  timeout : 连旁路容器（15173 同款 nginx 配置但 proxy_read_timeout=60s + 本卡 dist），
            全量导出被 60s 掐断 → 断言 POST /testcases/export=504 且 toast 为可读文案；
            浅色 / 深色各跑一次并截图。

用法：
  python tests/ui/verify_int2191_accept.py --mode success --base http://localhost:15173
  python tests/ui/verify_int2191_accept.py --mode timeout --base http://localhost:15293
"""
import argparse
import json
import os
import sys
import time
import zipfile

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.environ.get(
    'ART',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int2191'),
)
os.makedirs(ART, exist_ok=True)
DARK_KEY = 'iatp:theme:v1:mode'
EXPECT_TIMEOUT_TOAST = '导出失败：导出超时，请缩小筛选范围后重试'
USER = os.environ.get('LOGIN_USER', 'dev_user')
PASSWORD = os.environ.get('LOGIN_PASS', 'dev_password')
RESULT = []


def check(name, ok, detail=None):
    RESULT.append({'name': name, 'ok': bool(ok), 'detail': detail})
    print(('[PASS] ' if ok else '[FAIL] ') + name + ' | '
          + json.dumps(detail, ensure_ascii=False, default=str)[:1200], flush=True)
    return ok


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
  return {status: r.status, token: j.access_token || null};
})()
"""

FETCH_PATCH = r"""
window.__fetchLog = [];
(function(){
  const orig = window.fetch;
  window.fetch = async function(input, init) {
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    const method = ((init && init.method) || (input && input.method) || 'GET').toUpperCase();
    let res;
    try { res = await orig.apply(this, arguments); }
    catch (e) { window.__fetchLog.push({url:url, method:method, status:'ERR'}); throw e; }
    window.__fetchLog.push({url:url, method:method, status:res.status});
    return res;
  };
})();
"""


def build_driver(download_dir=None):
    opts = Options()
    opts.binary_location = CHROME
    opts.add_argument('--headless=new')
    opts.add_argument('--window-size=1440,900')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--lang=zh-CN')
    drv = webdriver.Chrome(options=opts)
    drv.set_script_timeout(120)
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    if download_dir:
        os.makedirs(download_dir, exist_ok=True)
        drv.execute_cdp_cmd('Browser.setDownloadBehavior', {
            'behavior': 'allow', 'downloadPath': download_dir, 'eventsEnabled': True})
    return drv


def wait_el(drv, xpath, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        els = drv.find_elements(By.XPATH, xpath)
        if els:
            return els[0]
        time.sleep(0.3)
    return None


def login(drv, base):
    for _ in range(3):
        try:
            drv.get(base + '/login')
            time.sleep(2.5)
            res = drv.execute_script(LOGIN_JS, PASSWORD, USER)
            if res.get('token'):
                return res
        except Exception as exc:
            print('login retry:', exc, flush=True)
            time.sleep(2)
    return {}


def set_theme(drv, mode):
    drv.execute_script("localStorage.setItem(arguments[0], arguments[1])", DARK_KEY, mode)


def open_export_dialog(drv, base):
    drv.get(base + '/testcases/by-group')
    btn = wait_el(drv, '//button[normalize-space(.)="导出"]', timeout=90)
    if btn is None:
        return None, '页头「导出」按钮未找到'
    btn.click()
    dlg = wait_el(drv, '//*[@role="dialog"]', timeout=20)
    if dlg is None:
        return None, '导出弹窗未打开'
    return dlg, None


def read_preview(drv):
    """读弹窗里的「将导出 N 条用例」文案"""
    end = time.time() + 180
    while time.time() < end:
        txt = drv.execute_script(
            "var d=document.querySelector('[role=dialog]');return d?(d.innerText||''):''")
        if '将导出' in txt:
            return txt.strip()
        time.sleep(0.5)
    return None


def toast_text(drv):
    return drv.execute_script(
        "var e=document.querySelector('[data-sonner-toast]');"
        "return e ? (e.innerText||'').trim() : null;")


def export_status(drv):
    log = drv.execute_script("return window.__fetchLog || [];")
    exp = [e for e in log if '/testcases/export' in (e.get('url') or '')]
    return exp[-1]['status'] if exp else None


def run_success(drv, base, tag):
    print(f'--- success {tag} ---', flush=True)
    set_theme(drv, 'light')
    dlg, err = open_export_dialog(drv, base)
    if err:
        check(f'{tag} 打开导出弹窗', False, err)
        return
    preview = read_preview(drv)
    check(f'{tag} 弹窗展示「将导出 N 条用例」预览', bool(preview), (preview or '')[:80])
    shot_dialog = os.path.join(ART, f'{tag}-export-dialog.png')
    drv.save_screenshot(shot_dialog)
    start = wait_el(drv, '//button[normalize-space(.)="开始导出"]', timeout=30)
    if start is None:
        check(f'{tag} 找到「开始导出」', False)
        return
    start.click()
    ok_toast = None
    end = time.time() + 320
    while time.time() < end:
        t = toast_text(drv)
        if t:
            ok_toast = t
            break
        time.sleep(0.5)
    st = export_status(drv)
    shot = os.path.join(ART, f'{tag}-export-success.png')
    drv.save_screenshot(shot)
    check(f'{tag} POST /testcases/export 200', st == 200, {'status': st})
    check(f'{tag} 成功 toast 显示已导出 580 个用例',
          bool(ok_toast) and '已导出' in ok_toast and '580' in ok_toast, ok_toast)
    # 等下载落地
    dl = os.path.join(ART, 'downloads')
    files = [f for f in os.listdir(dl)] if os.path.isdir(dl) else []
    end = time.time() + 90
    while time.time() < end and not any(f.endswith('.zip') for f in files):
        time.sleep(1)
        files = [f for f in os.listdir(dl)] if os.path.isdir(dl) else []
    zips = [f for f in files if f.endswith('.zip')]
    cnt = None
    zpath = None
    if zips:
        zpath = os.path.join(dl, zips[-1])
        try:
            with zipfile.ZipFile(zpath) as zf:
                data = json.loads(zf.read('testcases.json').decode('utf-8'))
                cases = data.get('test_cases') if isinstance(data, dict) else data
                cnt = len(cases or [])
        except Exception as e:
            print('zip parse error', e, flush=True)
    check(f'{tag} 实际下载 zip 内 testcases.json 条数 == 预览 580',
          cnt == 580, {'zip': zips[-1] if zips else None, 'count': cnt})
    return {'preview': preview, 'toast': ok_toast, 'status': st, 'zip': zpath,
            'count': cnt, 'shots': [shot_dialog, shot]}


def run_timeout(drv, base, tag):
    print(f'--- timeout {tag} ---', flush=True)
    set_theme(drv, 'dark' if tag == 'dark' else 'light')
    dlg, err = open_export_dialog(drv, base)
    if err:
        check(f'{tag} 打开导出弹窗', False, err)
        return
    preview = read_preview(drv)
    check(f'{tag} 弹窗展示「将导出 N 条用例」预览', bool(preview), (preview or '')[:80])
    start = wait_el(drv, '//button[normalize-space(.)="开始导出"]', timeout=30)
    if start is None:
        check(f'{tag} 找到「开始导出」', False)
        return
    start.click()
    toast = None
    end = time.time() + 130
    while time.time() < end:
        t = toast_text(drv)
        if t:
            toast = t
            break
        time.sleep(0.4)
    st = export_status(drv)
    shot = os.path.join(ART, f'tester-{tag}-export-504-toast.png')
    drv.save_screenshot(shot)
    check(f'{tag} POST /testcases/export 被 60s 反代掐断 = 504', st == 504, {'status': st})
    check(f'{tag} 504 toast 可读且不再为空「导出失败：」',
          toast == EXPECT_TIMEOUT_TOAST, {'toast': toast})
    return {'preview': preview, 'toast': toast, 'status': st, 'shot': shot}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mode', choices=['success', 'timeout'], required=True)
    ap.add_argument('--base', default='http://localhost:15173')
    args = ap.parse_args()
    base = args.base.rstrip('/')
    dl_dir = os.path.join(ART, 'downloads') if args.mode == 'success' else None
    out = {'base': base, 'mode': args.mode}
    drv = build_driver(dl_dir)
    try:
        res = login(drv, base)
        check('登录 dev_user 拿到 token', bool(res.get('token')), res.get('status'))
        if not res.get('token'):
            return 1
        if args.mode == 'success':
            out['success'] = run_success(drv, base, 'light')
        else:
            out['timeout_light'] = run_timeout(drv, base, 'light')
            out['timeout_dark'] = run_timeout(drv, base, 'dark')
    finally:
        drv.quit()
    ok = all(x['ok'] for x in RESULT)
    out['result'] = 'PASS' if ok else 'FAIL'
    out['checks'] = RESULT
    fn = 'tester_browser_success.json' if args.mode == 'success' else 'tester_browser_timeout.json'
    with open(os.path.join(ART, fn), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print('\nresult=' + out['result'], flush=True)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
