# -*- coding: utf-8 -*-
"""INT-2191 验收：用例导出经 nginx 60s 反代超时（504）时给出可读文案。

背景：15173 容器 nginx `/api/` 未设 proxy_read_timeout（默认 60s），全量 580 条导出
后端要约 94s → 504，且 nginx 返回 HTML，旧版 toast 只有空的「导出失败：」。

本脚本对「交付旁路容器」（同一份 nginx 配置 + 本卡 dist）实测：
  1) 浅色：/testcases/by-group → 导出弹窗预览条数 → 开始导出 → 等 60s
     → 断言 POST /testcases/export 返回 504、toast = 「导出失败：导出超时，请缩小筛选范围后重试」
  2) 深色：同一路径再跑一次（主题切 dark 后刷新），断言同上

用法：
  REACT_BASE=http://localhost:15291 python verify_int2191_export_504_copy.py
"""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

BASE = os.environ.get('REACT_BASE', 'http://localhost:15291').rstrip('/')
USER = os.environ.get('LOGIN_USER', 'dev_user')
PASSWORD = os.environ.get('LOGIN_PASS', 'dev_password')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.environ.get(
    'ART',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int2191'),
)
os.makedirs(ART, exist_ok=True)

DARK_KEY = 'iatp:theme:v1:mode'
EXPECT_TOAST = '导出失败：导出超时，请缩小筛选范围后重试'
RESULT = []


def check(name, ok, detail=None):
    RESULT.append({'name': name, 'ok': bool(ok), 'detail': detail})
    print(('[PASS] ' if ok else '[FAIL] ') + name + ' | '
          + json.dumps(detail, ensure_ascii=False, default=str)[:800], flush=True)
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
  return {status: r.status, token: j.access_token || null, body: r.ok ? 'ok' : txt.slice(0,200)};
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
    catch (e) {
      window.__fetchLog.push({url:url, method:method, status:'ERR', error:String(e)});
      throw e;
    }
    let body = null;
    try { body = await res.clone().text(); } catch(e) {}
    window.__fetchLog.push({url:url, method:method, status:res.status, body:(body||'').slice(0,300)});
    return res;
  };
})();
"""


def build_driver():
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
    drv.execute_cdp_cmd(
        'Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    return drv


def wait_text(drv, xpath, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        els = drv.find_elements(By.XPATH, xpath)
        if els:
            return els[0]
        time.sleep(0.4)
    return None


def login(drv):
    res = {}
    for _ in range(3):
        try:
            drv.get(BASE + '/login')
            time.sleep(3)
            res = drv.execute_script(LOGIN_JS, PASSWORD, USER)
            if res.get('token'):
                return res
        except Exception as exc:
            print('login retry:', exc, flush=True)
            time.sleep(2)
    return res


def set_theme(drv, mode):
    drv.execute_script(
        "localStorage.setItem(arguments[0], arguments[1])", DARK_KEY, mode)


def export_once(drv, tag):
    """打开用例分组页 → 导出 → 等 504 → 返回 (preview, toast, exportStatus, body, shot)"""
    drv.get(BASE + '/testcases/by-group')
    btn = wait_text(drv, '//button[normalize-space(.)="导出"]', timeout=90)
    if btn is None:
        return {'error': '未找到页头「导出」按钮'}
    btn.click()
    # 弹窗范围预览：等「将导出 N 条用例」
    preview = None
    end = time.time() + 180
    while time.time() < end:
        txt = drv.execute_script(
            "return (document.body.innerText||'')")
        if '将导出' in txt and '条用例' in txt:
            preview = txt
            break
        time.sleep(0.5)
    start = wait_text(drv, '//button[normalize-space(.)="开始导出"]', timeout=30)
    if start is None:
        drv.save_screenshot(os.path.join(ART, f'{tag}-no-start.png'))
        return {'error': '未找到「开始导出」按钮', 'preview': preview}
    start.click()
    # 等 toast（nginx 60s 后 504）
    toast = None
    end = time.time() + 120
    while time.time() < end:
        t = drv.execute_script(
            "var e=document.querySelector('[data-sonner-toast]');"
            "return e ? (e.innerText||'').trim() : null;")
        if t:
            toast = t
            break
        time.sleep(0.4)
    shot = os.path.join(ART, f'{tag}-export-504-toast.png')
    drv.save_screenshot(shot)
    log = drv.execute_script("return window.__fetchLog || [];")
    exports = [e for e in log if '/testcases/export' in (e.get('url') or '')]
    status = exports[-1]['status'] if exports else None
    body = (exports[-1].get('body') or '')[:160] if exports else ''
    return {'preview': preview, 'toast': toast, 'status': status,
            'body': body, 'shot': shot, 'exports': exports}


def run(drv, tag):
    print(f'--- {tag} ---', flush=True)
    set_theme(drv, 'dark' if tag == 'dark' else 'light')
    drv.get(BASE + '/testcases/by-group')
    time.sleep(1)
    out = export_once(drv, tag)
    print(json.dumps(out, ensure_ascii=False, default=str)[:1200], flush=True)
    ok = (out.get('status') == 504 and out.get('toast') == EXPECT_TOAST)
    check(f'{tag}: POST /testcases/export = 504 且 toast 文案可读', ok,
          {k: out.get(k) for k in ('status', 'toast', 'body')})
    if out.get('preview'):
        check(f'{tag}: 弹窗展示导出范围预览（将导出 N 条）', '将导出' in out['preview'],
              out['preview'].split('将导出')[-1][:60] if '将导出' in out['preview'] else None)
    return out


def main():
    drv = build_driver()
    try:
        res = login(drv)
        check('登录 dev_user 拿到 token', bool(res.get('token')), res.get('status'))
        if not res.get('token'):
            return
        run(drv, 'light')
        # 深色：切主题后整页重载再跑一遍
        set_theme(drv, 'dark')
        run(drv, 'dark')
    finally:
        drv.quit()
        summary = {
            'passed': sum(1 for r in RESULT if r['ok']),
            'total': len(RESULT),
            'failed': [r['name'] for r in RESULT if not r['ok']],
        }
        print('SUMMARY ' + json.dumps(summary, ensure_ascii=False), flush=True)
        with open(os.path.join(ART, 'result.json'), 'w', encoding='utf-8') as f:
            json.dump({'summary': summary, 'results': RESULT}, f,
                      ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
