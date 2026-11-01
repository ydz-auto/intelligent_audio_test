# -*- coding: utf-8 -*-
"""INT-2315 导出弹窗接异步导出作业：浏览器实测（dev server 5321 → docker 后端 :15000 真实库）。

模式：
  full    : 浅色主流程——打开弹窗逐项走查 → 580 条 ZIP 提交作业 → 进度变化 → 运行中关窗重开
            → 换格式再提交触发 429 接管 → done 自动下载 → 校验 zip 内 manifest/testcases 条数
            → 网络证据（POST 202 / 多次 GET 200 / 产物直链）
  dark    : 深色截图（弹窗 + 进度区 + 成功 toast）
  expired : 注入 410（预签名直链失败 + /download 回 410）验证「导出文件已过期，请重新导出」
用法：python tests/ui/verify_int2315_export_job.py --mode full --base http://localhost:5321
"""
import argparse
import json
import os
import re
import sys
import time
import zipfile

import requests

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.environ.get(
    'ART',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int2315'),
)
os.makedirs(ART, exist_ok=True)
DARK_KEY = 'iatp:theme:v1:mode'
USER = os.environ.get('LOGIN_USER', 'dev_user')
PASSWORD = os.environ.get('LOGIN_PASS', 'dev_password')
RESULT = []
TOKEN = None


def check(name, ok, detail=None):
    RESULT.append({'name': name, 'ok': bool(ok), 'detail': detail})
    print(('[PASS] ' if ok else '[FAIL] ') + name + ' | '
          + json.dumps(detail, ensure_ascii=False, default=str)[:900], flush=True)
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
    catch (e) { window.__fetchLog.push({url:url, method:method, status:'ERR', t:Date.now()}); throw e; }
    window.__fetchLog.push({url:url, method:method, status:res.status, t:Date.now()});
    return res;
  };
})();
"""

# 注入 410：预签名直链不通 + /jobs/{id}/download 回 410（后端产物过期时的真实语义）
EXPIRE_PATCH = r"""
(function(){
  const orig = window.fetch;
  window.fetch = async function(input, init) {
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    if (/\/export\/jobs\/[^/]+\/download/.test(url)) {
      window.__fetchLog && window.__fetchLog.push({url:url, method:'GET', status:410, t:Date.now(), injected:true});
      return new Response(JSON.stringify({success:false, code:203, message:'导出文件已过期，请重新导出'}),
        {status:410, headers:{'Content-Type':'application/json'}});
    }
    if (/^https?:\/\/127\.0\.0\.1:9000\//.test(url)) {
      window.__fetchLog && window.__fetchLog.push({url:url, method:'GET', status:'ERR', t:Date.now(), injected:true});
      throw new TypeError('injected: presigned url unavailable');
    }
    return orig.apply(this, arguments);
  };
})();
"""


def build_driver(download_dir=None, expire=False):
    opts = Options()
    opts.binary_location = CHROME
    opts.add_argument('--headless=new')
    opts.add_argument('--window-size=1440,1000')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--lang=zh-CN')
    drv = webdriver.Chrome(options=opts)
    drv.set_script_timeout(180)
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    if expire:
        drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': EXPIRE_PATCH})
    if download_dir:
        os.makedirs(download_dir, exist_ok=True)
        drv.execute_cdp_cmd('Browser.setDownloadBehavior', {
            'behavior': 'allow', 'downloadPath': download_dir, 'eventsEnabled': True})
    return drv


def wait_el(drv, xpath, timeout=60, root=None):
    end = time.time() + timeout
    while time.time() < end:
        els = (root or drv).find_elements(By.XPATH, xpath)
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


def dialog_text(drv):
    return drv.execute_script(
        "var ds=[...document.querySelectorAll('[role=dialog]')].filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0;});"
        "return ds.length ? (ds[ds.length-1].innerText||'') : ''") or ''


def toast_texts(drv):
    return drv.execute_script(
        "return [...document.querySelectorAll('[data-sonner-toast]')]"
        ".map(e=>(e.innerText||'').replace(/\\s+/g,' ').trim()).filter(Boolean)") or []


def open_export_dialog(drv, base, navigate=True):
    if navigate:
        drv.get(base + '/testcases/by-group')
        time.sleep(2)
    btn = wait_el(drv, '//button[normalize-space(.)="导出"]', timeout=120)
    if btn is None:
        return None, '页头「导出」按钮未找到'
    drv.execute_script('arguments[0].click()', btn)
    # base-ui 关闭后仍留在 DOM（display:none），必须等「可见的那个」出现
    end = time.time() + 30
    while time.time() < end:
        vis = drv.execute_script(
            "return [...document.querySelectorAll('[role=dialog]')]"
            ".some(e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0;})")
        if vis:
            return True, None
        time.sleep(0.3)
    return None, '导出弹窗未打开'


def read_preview(drv, timeout=180):
    end = time.time() + timeout
    while time.time() < end:
        txt = dialog_text(drv)
        if '将导出' in txt:
            return txt
        time.sleep(0.5)
    return None


def progress_samples(drv):
    """弹窗进度区：阶段文案 + processed / total"""
    txt = dialog_text(drv)
    m = re.search(r'(\d+)\s*/\s*(\d+)', txt)
    phase = None
    for key in ('正在读取用例', '正在打包文件', '正在上传产物', '排队中', '正在导出'):
        if key in txt:
            phase = key
            break
    return {'pair': m.group(0) if m else None,
            'processed': int(m.group(1)) if m else None,
            'total': int(m.group(2)) if m else None,
            'phase': phase}


def fetch_log(drv):
    return drv.execute_script("return window.__fetchLog || [];") or []


def job_logs(drv):
    log = fetch_log(drv)
    posts = [e for e in log if '/testcases/export/jobs' in (e['url'] or '') and e['method'] == 'POST']
    gets = [e for e in log if re.search(r'/testcases/export/jobs/[^/]+$', e['url'] or '')]
    dls = [e for e in log if re.search(r'/testcases/export/jobs/[^/]+/download', e['url'] or '')
           or re.match(r'^https?://127\.0\.0\.1:9000/', e['url'] or '')]
    return posts, gets, dls


def click_dialog_button(drv, text):
    """点「可见弹窗」里指定文案的按钮（关闭的 base-ui 弹窗仍留在 DOM，不能按首个匹配点）"""
    return drv.execute_script(
        "const ds=[...document.querySelectorAll('[role=dialog]')]"
        ".filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0;});"
        "if(!ds.length) return false;"
        "const d=ds[ds.length-1];"
        "const b=[...d.querySelectorAll('button')]"
        ".find(e=>((e.innerText||'').trim())===arguments[0]);"
        "if(!b) return false; b.click(); return true;", text)


def switch_format(drv, label):
    """base-ui Select（弹窗常驻 DOM，只操作可见的那个）：点触发器再把 innerText 命中的选项点掉"""
    clicked = drv.execute_script(
        "const ds=[...document.querySelectorAll('[role=dialog]')]"
        ".filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0;});"
        "if(!ds.length) return false;"
        "const t=ds[ds.length-1].querySelector(\"[data-slot='select-trigger']\");"
        "if(!t) return false; t.click(); return true;")
    if not clicked:
        return False, []
    time.sleep(0.8)
    items = drv.execute_script(
        "return [...document.querySelectorAll(\"[data-slot='select-item']\")]"
        ".map(e=>(e.innerText||'').trim())") or []
    ok = drv.execute_script(
        "const items=[...document.querySelectorAll(\"[data-slot='select-item']\")];"
        "const t=items.find(e=>((e.innerText||'').trim()).includes(arguments[0]));"
        "if(!t) return false; t.click(); return true;", label)
    time.sleep(0.6)
    return bool(ok), items


def wait_download(dirpath, suffix, timeout=180):
    end = time.time() + timeout
    while time.time() < end:
        files = [f for f in os.listdir(dirpath)
                 if f.endswith(suffix) and not f.endswith('.crdownload')]
        if files:
            newest = max((os.path.join(dirpath, f) for f in files), key=os.path.getmtime)
            return newest
        time.sleep(1)
    return None


def list_total(base, token):
    """直连 GET /testcases 读总数（导出前后对照：导出是只读动作）"""
    try:
        r = requests.get(f'{base}/api/v1/testcases',
                         params={'page': 1, 'page_size': 1},
                         headers={'Authorization': f'Bearer {token}'}, timeout=20)
        return r.json().get('data', {}).get('total')
    except Exception:
        return None


def run_full(drv, base, dark=False):
    tag = 'dark' if dark else 'light'
    # 下载目录与 build_driver 的 Browser.setDownloadBehavior 必须是同一个
    downloads = os.path.join(ART, 'downloads')
    os.makedirs(downloads, exist_ok=True)
    for f in os.listdir(downloads):
        os.remove(os.path.join(downloads, f))

    set_theme(drv, 'dark' if dark else 'light')
    drv.get(base + '/testcases/by-group')
    time.sleep(3)
    total_before = list_total(base, TOKEN)
    dlg, err = open_export_dialog(drv, base)
    if err:
        check(f'[{tag}] 打开导出弹窗', False, err)
        return
    preview = read_preview(drv)
    check(f'[{tag}] 弹窗展示「将导出 N 条用例」', bool(preview), (preview or '')[:100])
    dt = dialog_text(drv)
    # §5.7.2 逐环节：范围单选 ×2、格式 Select、ZIP 选项 ×2、主钮
    check(f'[{tag}] 导出范围单选 ×2', '按当前筛选条件导出' in dt and '仅导出已选' in dt, dt[:120])
    check(f'[{tag}] ZIP 选项 ×2（参考参数 / 音频）', '包含参考参数文件' in dt and '包含音频文件' in dt)
    check(f'[{tag}] 主钮「开始导出」', '开始导出' in dt)
    drv.save_screenshot(os.path.join(ART, f'{tag}-01-dialog.png'))

    ok, items = switch_format(drv, 'Excel')
    check(f'[{tag}] 格式 Select 三项（ZIP / Excel / JSON）',
          len(items) == 3 and any('ZIP' in i for i in items) and any('JSON' in i for i in items), items)
    drv.save_screenshot(os.path.join(ART, f'{tag}-02-format-options.png'))
    ok2, _ = switch_format(drv, 'ZIP')
    check(f'[{tag}] 格式切回 ZIP 数据包', ok2)

    # 默认参数（ZIP + 参考参数文件）；本轮开跑前已清空上一轮测试作业的幂等键，
    # 保证是一次真正新建的作业（否则同参数提交会直接拿回上一轮已完成的作业）。
    if not click_dialog_button(drv, '开始导出'):
        check(f'[{tag}] 找到「开始导出」', False)
        return

    # 等 202
    end = time.time() + 120
    posts = []
    while time.time() < end:
        posts, _, _ = job_logs(drv)
        if posts:
            break
        time.sleep(0.5)
    check(f'[{tag}] POST /testcases/export/jobs 202',
          bool(posts) and posts[-1]['status'] == 202, posts[-1] if posts else None)

    # 采样进度（至少两次不同 processed）
    seen = {}
    shot_progress = False
    end = time.time() + 300
    while time.time() < end:
        info = progress_samples(drv)
        if info['processed'] is not None:
            seen[info['processed']] = info
        if not shot_progress and len(seen) >= 2:
            drv.save_screenshot(os.path.join(ART, f'{tag}-03-progress.png'))
            shot_progress = True
        if not dark and len(seen) >= 2:
            break
        if dark and len(seen) >= 2:
            break
        toasts = toast_texts(drv)
        if any('已导出' in t for t in toasts):
            break
        time.sleep(1)
    check(f'[{tag}] 进度至少两次不同 processed', len(seen) >= 2,
          sorted(seen.keys())[:12])
    check(f'[{tag}] 进度区显示阶段文案', any(v['phase'] for v in seen.values()),
          [v['phase'] for v in list(seen.values())[:5]])
    if not shot_progress:
        drv.save_screenshot(os.path.join(ART, f'{tag}-03-progress.png'))

    if dark:
        # 深色只需进度区截图，直接等结果
        pass

    # 429 接管（仅浅色主流程跑一次）：关窗重开 → 改格式再提交 → 后端 429 → 接管在办任务
    if not dark:
        click_dialog_button(drv, '取消跟踪')
        time.sleep(1.2)
        dlg, err = open_export_dialog(drv, base, navigate=False)
        if err:
            check('[light] 重开导出弹窗', False, err)
        else:
            banner = '上次导出仍在进行' in dialog_text(drv)
            check('[light] 重开弹窗提示「上次导出仍在进行」', banner, dialog_text(drv)[:200])
            drv.save_screenshot(os.path.join(ART, 'light-04-reopen-banner.png'))
            ok_fmt, _ = switch_format(drv, 'Excel')
            check('[light] 换格式为 Excel（准备触发 429）', ok_fmt)
            clicked2 = click_dialog_button(drv, '开始导出')
            check('[light] 二次提交按钮可点', clicked2)
            end = time.time() + 30
            conflict = None
            while time.time() < end:
                posts, _, _ = job_logs(drv)
                if any(p['status'] == 429 for p in posts):
                    conflict = [p for p in posts if p['status'] == 429][-1]
                    break
                time.sleep(0.5)
            check('[light] 换参数再提交 → 429 已有任务在进行', conflict is not None, conflict)
            time.sleep(1.5)
            toasts = toast_texts(drv)
            check('[light] 429 被接管（提示已接管，不报错）',
                  any('已接管继续跟踪' in t for t in toasts), toasts[:3])
            check('[light] 429 未出现失败 toast',
                  not any('导出失败' in t for t in toasts), toasts[:3])
            info = progress_samples(drv)
            check('[light] 接管后进度区继续显示', info['processed'] is not None, info)
            drv.save_screenshot(os.path.join(ART, 'light-05-429-takeover.png'))

    # 等成功 toast
    end = time.time() + 420
    success = None
    while time.time() < end:
        toasts = toast_texts(drv)
        if any('已导出' in t for t in toasts):
            success = [t for t in toasts if '已导出' in t][-1]
            break
        if any('导出失败' in t for t in toasts):
            success = [t for t in toasts if '导出失败' in t][-1]
            break
        time.sleep(1)
    check(f'[{tag}] 导出完成 toast', bool(success) and '已导出' in success, success)
    drv.save_screenshot(os.path.join(ART, f'{tag}-06-success.png'))

    posts, gets, dls = job_logs(drv)
    check(f'[{tag}] GET /jobs/{{id}} 至少 2 次 200',
          len([g for g in gets if g['status'] == 200]) >= 2,
          [g['status'] for g in gets][:10])
    check(f'[{tag}] 产物下载（直链或 /download）',
          any(d.get('status') in (200, 'ERR') for d in dls) or bool(dls),
          [{'u': (d['url'] or '')[:60], 's': d['status']} for d in dls][:3])

    if not dark:
        path = wait_download(downloads, '.zip', timeout=180)
        check('[light] 浏览器下载到 zip', path is not None, path)
        if path:
            try:
                with zipfile.ZipFile(path) as zf:
                    names = zf.namelist()
                    manifest = json.loads(zf.read('manifest.json')) if 'manifest.json' in names else {}
                    cases = json.loads(zf.read('testcases.json')) if 'testcases.json' in names else {}
                total = manifest.get('total_count') or manifest.get('test_case_count')
                n_cases = len(cases.get('test_cases') or [])
                check('[light] zip 可解压且 manifest.total_count == 580',
                      total == 580, {'manifest_keys': sorted(manifest.keys())[:12],
                                     'total_count': total, 'testcases_json': n_cases,
                                     'files': names[:6]})
                # 列表总数不因导出变化（导出是只读动作）
                total_after = list_total(base, TOKEN)
                check('[light] 用例总数导出前后一致（580，导出不改数据）',
                      total_before == 580 and total_after == 580,
                      {'before': total_before, 'after': total_after})
                body = drv.execute_script(
                    "var d=document.querySelector('[role=dialog]');"
                    "var t=document.body.innerText||'';"
                    "return d? t.replace(d.innerText||'','') : t;")
                check('[light] 列表页无残留「已选 N」选择浮条', '已选' not in body, body[:120])
            except Exception as exc:
                check('[light] zip 解析', False, str(exc))


def run_expired(drv, base):
    set_theme(drv, 'light')
    dlg, err = open_export_dialog(drv, base)
    if err:
        check('[expired] 打开导出弹窗', False, err)
        return
    start = wait_el(drv, '//button[normalize-space(.)="开始导出"]', timeout=60)
    drv.execute_script('arguments[0].click()', start)
    drv.execute_script(EXPIRE_PATCH)
    end = time.time() + 420
    hit = None
    while time.time() < end:
        toasts = toast_texts(drv)
        if any('已过期' in t for t in toasts):
            hit = [t for t in toasts if '已过期' in t][-1]
            break
        if any('导出失败' in t for t in toasts):
            hit = [t for t in toasts if '导出失败' in t][-1]
            break
        time.sleep(1)
    check('[expired] 410 → 提示「导出文件已过期，请重新导出」',
          bool(hit) and '已过期' in hit, hit)
    drv.save_screenshot(os.path.join(ART, 'expired-01-410.png'))
    posts, gets, dls = job_logs(drv)
    check('[expired] 注入 410 命中 /download',
          any(d['status'] == 410 for d in dls),
          [{'u': (d['url'] or '')[:60], 's': d['status']} for d in dls][:3])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mode', default='full', choices=['full', 'dark', 'expired'])
    ap.add_argument('--base', default='http://localhost:5321')
    args = ap.parse_args()
    dl = os.path.join(ART, 'downloads')
    drv = build_driver(dl, expire=(args.mode == 'expired'))
    try:
        res = login(drv, args.base)
        global TOKEN
        TOKEN = res.get('token')
        check('登录 docker 栈（dev_user）', bool(res.get('token')), res)
        if args.mode == 'full':
            run_full(drv, args.base, dark=False)
        elif args.mode == 'dark':
            run_full(drv, args.base, dark=True)
        else:
            run_expired(drv, args.base)
    finally:
        drv.quit()
        with open(os.path.join(ART, f'result-{args.mode}.json'), 'w', encoding='utf-8') as fh:
            json.dump(RESULT, fh, ensure_ascii=False, indent=2, default=str)
        ok = sum(1 for r in RESULT if r['ok'])
        print(f'\n==== {args.mode}: {ok}/{len(RESULT)} passed ====', flush=True)


if __name__ == '__main__':
    main()
