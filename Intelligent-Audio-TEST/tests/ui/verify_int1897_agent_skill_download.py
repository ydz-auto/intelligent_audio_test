# -*- coding: utf-8 -*-
"""INT-1897 验收浏览器实测：「连接你的 agent」下载 skill 包接真实 GET /api/v1/agent/skill。

对照卡面验收标准：
1. 点「下载 skill」→ Network 出现 GET /api/v1/agent/skill?base_url=...，200 + application/zip；
   zip 含 SKILL.md + mcp.json，mcp.json 的服务地址 = 页面默认地址；
2. 改「服务地址」后再下载，包内 mcp.json 地址跟着变（证明 base_url 生效）；
3. 请求失败（拦截真实请求模拟后端不可达）→ 红色失败提示，不出现假成功、不产出文件；
4. 浅色 + 深色 + Network 截图。

运行前提：dev server http://127.0.0.1:5631（frontend/，VITE_API_TARGET=localhost:15000 docker 后端），
后端为 docker 真实库栈（/health database=intelligent_audio_test），AUTH_MODE=off。
"""
import base64
import json
import os
import shutil
import sys
import time
import zipfile

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, OSError):
        pass

BASE = os.environ.get('INT1897_BASE', 'http://127.0.0.1:5631')
CHROME_BIN = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
DRIVER_CACHE = r'C:\Users\public.DESKTOP-3SNNDSS\.cache\selenium\chromedriver\win64'
ART_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1897')
DL_DIR = os.path.join(ART_DIR, 'downloads')
for d in (ART_DIR, DL_DIR):
    os.makedirs(d, exist_ok=True)

RESULTS = []


def record(name, ok, detail=''):
    RESULTS.append({'name': name, 'ok': ok, 'detail': detail})
    print(f'{"PASS" if ok else "FAIL"} | {name} | {detail}')


def resolve_driver():
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    if chrome_major:
        for ver in os.listdir(DRIVER_CACHE):
            if ver.startswith(str(chrome_major)):
                exe = os.path.join(DRIVER_CACHE, ver, 'chromedriver.exe')
                if os.path.isfile(exe):
                    return exe
    for ver in sorted(os.listdir(DRIVER_CACHE), reverse=True):
        exe = os.path.join(DRIVER_CACHE, ver, 'chromedriver.exe')
        if os.path.isfile(exe):
            return exe
    return ''


def new_driver(width=1600, height=1000):
    opts = Options()
    opts.binary_location = CHROME_BIN
    opts.add_argument(f'--window-size={width},{height}')
    opts.add_argument('--headless=new')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--hide-scrollbars')
    opts.add_argument('--lang=zh-CN')
    opts.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    opts.add_experimental_option('prefs', {
        'download.default_directory': DL_DIR,
        'download.prompt_for_download': False,
        'download.directory_upgrade': True,
        'safebrowsing.enabled': True,
    })
    drv = webdriver.Chrome(service=Service(resolve_driver()), options=opts)
    drv.set_page_load_timeout(60)
    return drv


def inject_login(driver, username='dev_user', permissions=('*',)):
    """AUTH_MODE=off：localStorage 注入 auth_user 后整页重载。"""
    driver.get(f'{BASE}/#/login')
    WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, '.login-card')))
    payload = json.dumps({
        'id': 1, 'username': username, 'roleId': None,
        'roleName': 'dev_user', 'permissions': list(permissions),
    })
    driver.execute_script(
        'window.localStorage.setItem(arguments[0], arguments[1]);'
        'window.localStorage.setItem(arguments[2], arguments[3]);',
        'auth_token', 'dev-token', 'auth_user', payload,
    )
    driver.refresh()
    time.sleep(1.5)


def shot(driver, name):
    p = os.path.join(ART_DIR, name)
    driver.save_screenshot(p)
    print(f'shot: {p}')
    return p


def clear_downloads():
    for f in os.listdir(DL_DIR):
        try:
            os.remove(os.path.join(DL_DIR, f))
        except OSError:
            pass


def wait_download(before, timeout=25):
    """等新增的 zip 落盘（排除 .crdownload），返回路径。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        files = [f for f in os.listdir(DL_DIR)
                 if f.lower().endswith('.zip') and f not in before
                 and not f.endswith('.crdownload')]
        if files:
            time.sleep(0.6)  # 等写盘完成
            return os.path.join(DL_DIR, files[0])
        time.sleep(0.4)
    return ''


def read_mcp_zip(path):
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        mcp = json.loads(z.read('mcp.json').decode('utf-8'))
        skill_len = len(z.read('SKILL.md')) if 'SKILL.md' in names else 0
    return names, mcp, skill_len


PERF = []  # 累积 performance 条目（get_log 每次调用会清空缓冲区）


def collect_perf(driver):
    """把 performance log 累积到 PERF；必须每次取样都调一次，否则丢条目。"""
    for e in driver.get_log('performance'):
        try:
            PERF.append(json.loads(e['message']).get('message', {}))
        except Exception:
            pass


def skill_requests():
    """从累积的 performance 条目提取 /api/v1/agent/skill 的 请求 URL + 响应状态/类型。"""
    reqs, resps = {}, {}
    for m in PERF:
        method = m.get('method', '')
        params = m.get('params', {})
        if method == 'Network.requestWillBeSent':
            url = params.get('request', {}).get('url', '')
            if '/api/v1/agent/skill' in url:
                reqs[params.get('requestId')] = {
                    'url': url,
                    'method': params.get('request', {}).get('method'),
                }
        elif method == 'Network.responseReceived':
            rid = params.get('requestId')
            if rid in reqs:
                r = params.get('response', {})
                resps[rid] = {'status': r.get('status'), 'mime': r.get('mimeType')}
    out = []
    for rid, req in reqs.items():
        out.append({**req, **resps.get(rid, {})})
    return out


def set_input_value(driver, selector, value):
    el = driver.find_element(By.CSS_SELECTOR, selector)
    driver.execute_script(
        'arguments[0].value = arguments[1];'
        'arguments[0].dispatchEvent(new Event("input", {bubbles: true}));',
        el, value,
    )
    time.sleep(0.3)
    return el


def toggle_dark(driver):
    driver.execute_script('document.documentElement.classList.add("dark");')
    time.sleep(0.6)


def toggle_light(driver):
    driver.execute_script('document.documentElement.classList.remove("dark");')
    time.sleep(0.6)


def main():
    drv = new_driver()
    try:
        inject_login(drv)
        WebDriverWait(drv, 20)

        # ── 进入页面 ──
        drv.get(f'{BASE}/#/agent-connect')
        WebDriverWait(drv, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '.agent-connect-page')))
        time.sleep(1.2)
        page_origin = drv.execute_script('return window.location.origin;')
        default_url = drv.find_element(By.CSS_SELECTOR, '.url-input').get_attribute('value')
        record('① 页面加载，服务地址默认取地址栏', default_url == page_origin,
               f'default={default_url} origin={page_origin}')
        note_txt = drv.find_element(By.CSS_SELECTOR, '.download-note').text
        record('①b 已删「契约示例包」用户可见口径', '示例' not in note_txt and '契约' not in note_txt,
               f'note={note_txt}')
        drv.execute_script(
            'document.querySelector(".download-row").scrollIntoView({block: "center"});')
        time.sleep(0.6)
        shot(drv, '01_light.png')
        toggle_dark(drv)
        shot(drv, '02_dark.png')
        toggle_light(drv)

        # ── ① 默认地址下载 ──
        clear_downloads()
        before = set(os.listdir(DL_DIR))
        drv.find_element(By.CSS_SELECTOR, '.skill-download-button').click()
        zip_path = wait_download(before)
        record('①c 点击下载产出 zip 文件', bool(zip_path), f'{os.path.basename(zip_path)}')
        if zip_path:
            names, mcp, skill_len = read_mcp_zip(zip_path)
            record('①d zip 含 SKILL.md + mcp.json', names == ['SKILL.md', 'mcp.json'],
                   f'namelist={names}, SKILL.md={skill_len}B')
            expect = page_origin.rstrip('/') + '/api/v1/mcp'
            record('①e mcp.json 服务地址 = 页面默认地址', mcp.get('url') == expect,
                   f'url={mcp.get("url")} expect={expect}')
        time.sleep(0.8)
        collect_perf(drv)
        reqs = skill_requests()
        default_req = next((r for r in reqs if 'base_url=' in r['url']), None)
        enc_origin = page_origin.replace(':', '%3A').replace('/', '%2F')
        record('①f Network: GET /api/v1/agent/skill?base_url=...',
               bool(default_req) and default_req['method'] == 'GET'
               and ('base_url=' in default_req['url'])
               and default_req.get('status') == 200
               and 'zip' in (default_req.get('mime') or ''),
               f'{default_req}')

        # ── ② 改服务地址后再下载 ──
        new_url = 'https://agent.example.com'
        set_input_value(drv, '.url-input', new_url)
        clear_downloads()
        before = set(os.listdir(DL_DIR))
        drv.find_element(By.CSS_SELECTOR, '.skill-download-button').click()
        zip_path2 = wait_download(before)
        ok2 = False
        detail2 = 'no file'
        if zip_path2:
            _, mcp2, _ = read_mcp_zip(zip_path2)
            expect2 = new_url + '/api/v1/mcp'
            ok2 = mcp2.get('url') == expect2
            detail2 = f'url={mcp2.get("url")} expect={expect2}'
        record('② 改服务地址后下载，包内地址跟着变', ok2, detail2)
        time.sleep(0.8)
        collect_perf(drv)
        reqs2 = skill_requests()
        custom_req = next((r for r in reqs2 if 'agent.example.com' in r['url']), None)
        record('②b Network 带 base_url=https%3A%2F%2Fagent.example.com',
               bool(custom_req) and custom_req.get('status') == 200,
               f'{custom_req}')

        # ── 正常下载路径的 console 检查（失败态之前的干净快照） ──
        sev = [e for e in drv.get_log('browser')
               if e['level'] == 'SEVERE'
               and 'favicon' not in e.get('message', '')
               and '/api/option/' not in e.get('message', '')]
        record('④ console 无 SEVERE（正常下载路径；排除已知 /api/option/ 与 favicon 缺口）',
               len(sev) == 0, f'{len(sev)} 条: {[e["message"][:120] for e in sev[:3]]}')

        # ── ③ 失败态：拦截真实请求 ──
        clear_downloads()
        before_fail = set(os.listdir(DL_DIR))
        drv.execute_cdp_cmd('Network.enable', {})
        drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': ['*/api/v1/agent/skill*']})
        drv.find_element(By.CSS_SELECTOR, '.skill-download-button').click()
        toast = None
        try:
            WebDriverWait(drv, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '.notification--error')))
            toast = drv.find_element(By.CSS_SELECTOR, '.notification--error .notification-message').text
        except Exception:
            pass
        record('③ 请求失败 → 红色失败提示', bool(toast) and '失败' in (toast or ''), f'toast={toast!r}')
        files_after_fail = [f for f in os.listdir(DL_DIR)
                            if f.lower().endswith('.zip') and f not in before_fail]
        record('③b 失败时无文件产出（不假成功）', not files_after_fail, f'files={files_after_fail}')
        toggle_dark(drv)
        shot(drv, '05_dark_error.png')
        toggle_light(drv)
        drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': []})

        # ── Network 汇总截图 ──
        collect_perf(drv)
        all_reqs = skill_requests()
        rows = ''.join(
            '<tr>'
            f'<td style="padding:3px 8px;border-bottom:1px solid #ddd;font:11px monospace">{i + 1}</td>'
            f'<td style="padding:3px 8px;border-bottom:1px solid #ddd;font:11px monospace">{r.get("method")}</td>'
            f'<td style="padding:3px 8px;border-bottom:1px solid #ddd;font:11px monospace">{r.get("status")}</td>'
            f'<td style="padding:3px 8px;border-bottom:1px solid #ddd;font:11px monospace">{r.get("mime")}</td>'
            f'<td style="padding:3px 8px;border-bottom:1px solid #ddd;font:11px monospace">{r.get("url")}</td>'
            '</tr>'
            for i, r in enumerate(all_reqs))
        html = (
            '<html><body style="margin:0;background:#fff">'
            '<div style="padding:10px;font:bold 13px sans-serif">'
            'Network — GET /api/v1/agent/skill（INT-1897 真实 skill 包下载）</div>'
            '<table style="border-collapse:collapse;width:100%">'
            '<tr>'
            '<th style="text-align:left;padding:3px 8px;border-bottom:2px solid #666;font:11px sans-serif">#</th>'
            '<th style="text-align:left;padding:3px 8px;border-bottom:2px solid #666;font:11px sans-serif">Method</th>'
            '<th style="text-align:left;padding:3px 8px;border-bottom:2px solid #666;font:11px sans-serif">Status</th>'
            '<th style="text-align:left;padding:3px 8px;border-bottom:2px solid #666;font:11px sans-serif">MIME</th>'
            '<th style="text-align:left;padding:3px 8px;border-bottom:2px solid #666;font:11px sans-serif">URL</th>'
            '</tr>'
            f'{rows}</table></body></html>')
        drv.execute_script("window.open('about:blank','_blank');")
        drv.switch_to.window(drv.window_handles[-1])
        drv.get('data:text/html;charset=utf-8;base64,'
                + base64.b64encode(html.encode('utf-8')).decode())
        time.sleep(0.8)
        shot(drv, '07_network.png')
        drv.close()
        drv.switch_to.window(drv.window_handles[0])

        # ── 失败态 console 只应有一条本卡改动前的请求失败日志（错误路径保留，非缺陷） ──
        sev_fail = [e for e in drv.get_log('browser')
                    if e['level'] == 'SEVERE'
                    and 'favicon' not in e.get('message', '')
                    and '/api/option/' not in e.get('message', '')]
        unexpected = [e for e in sev_fail if '[API Fetch Error]' not in e.get('message', '')]
        record('④b 失败态只产生该请求的错误日志（无其他异常）', len(unexpected) == 0,
               f'异常 {len(unexpected)} 条')

    finally:
        drv.quit()

    print('\n==== 汇总 ====')
    ok = sum(1 for r in RESULTS if r['ok'])
    for r in RESULTS:
        print(f'{"✅" if r["ok"] else "❌"} {r["name"]} — {r["detail"]}')
    print(f'{ok}/{len(RESULTS)} passed')
    with open(os.path.join(ART_DIR, 'results.json'), 'w', encoding='utf-8') as f:
        json.dump(RESULTS, f, ensure_ascii=False, indent=2)
    return 0 if ok == len(RESULTS) else 1


if __name__ == '__main__':
    sys.exit(main())
