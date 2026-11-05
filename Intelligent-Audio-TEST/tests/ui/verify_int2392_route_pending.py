# -*- coding: utf-8 -*-
"""INT-2392 验收：SPA 路由 pending 加载态（React 接线基座）。

被测前端：本卡 dist 起的旁路容器 http://127.0.0.1:15273
（iat-react-frontend:int2392-verify，nginx conf 取自共享 15173，/api 反代同一
api_gateway；共享 15173 按 2026-10-23 口径固定跑 wiring/react，不替换）。
后端：docker 真实库栈 http://localhost:15000（/health database=intelligent_audio_test）。
登录：RSA-OAEP 加密登录（dev_user/dev_password）→ 写 localStorage iatp:auth:token:v1。

用例：
A. 节流（CDP Network.emulateNetworkConditions）下点报告中心行：
   - 必须出现 [data-testid=route-pending]（浅色截图）；
   - 待定期间侧栏/头部仍可用（不被遮挡）；
   - CDP Network 事件证明详情路由 chunk 请求被拖慢（附瀑布图截图 + timing JSON）。
B. 深色主题重复 A（深色截图）。
C. 正常网络：
   - 同 chunk 二次进入详情：pending 不闪；
   - 侧栏切到另一个路由（新 chunk）：pending 不闪、不残留；
   - 落地后 DOM 无 loading 残留。
D. 浏览器 console 无 SEVERE。
"""
import base64
import json
import os
import sys
import time
import urllib.parse
import urllib.request

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15273').rstrip('/')
API = os.environ.get('BACKEND_BASE', 'http://localhost:15000').rstrip('/')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int2392')
USERNAME = os.environ.get('REACT_USER', 'dev_user')
PASSWORD = os.environ.get('REACT_PWD', 'dev_password')
TOKEN_KEY = 'iatp:auth:token:v1'
THEME_KEY = 'iatp:theme:v1:mode'

# 节流参数：2s 往返延迟 + 500KB/s（弱网档；正常本机 chunk 几十 ms，节流后到秒级）
THROTTLE_LATENCY_MS = 2000
THROTTLE_THROUGHPUT = 500 * 1024

RESULT = []
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass


def check(name, ok, detail=''):
    RESULT.append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:600]})
    print(('[PASS] ' if ok else '[FAIL] ') + name + (' | ' + str(detail)[:600] if detail else ''))


def get_token():
    with urllib.request.urlopen(API + '/api/v1/auth/encryption-key', timeout=60) as r:
        key_data = json.loads(r.read().decode('utf-8'))
    pub = serialization.load_pem_public_key(key_data['public_key'].encode())
    enc = pub.encrypt(
        PASSWORD.encode('utf-8'),
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
    )
    body = urllib.parse.urlencode({
        'username': USERNAME,
        'password_encrypted': base64.b64encode(enc).decode(),
        'encryption_key_id': key_data['kid'],
    }).encode()
    req = urllib.request.Request(
        API + '/api/v1/auth/login', data=body,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode('utf-8'))['access_token']


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,899')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.add_argument('--force-device-scale-factor=1')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    drv_path = ''
    if chrome_major and os.path.isdir(cache_root):
        cands = []
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
                except ValueError:
                    continue
        same = [exe for ver, exe in cands if ver and ver[0] == chrome_major]
        if same:
            drv_path = max(same)
    service = Service(executable_path=drv_path) if drv_path else Service()
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(120)
    return drv


# ===== 待定态观测器（MutationObserver，SPA 内导航不失效） =====
OBSERVER_JS = r"""
(function () {
  if (window.__pendingObserver) { window.__pendingObserver.disconnect(); }
  window.__pendingLog = [];
  window.__pendingVisible = false;
  window.__pendingLogPage = location.pathname;
  function record(kind, extra) {
    var e = { kind: kind, t: Math.round(performance.now()), href: location.pathname, extra: extra || null };
    window.__pendingLog.push(e);
  }
  function check() {
    var el = document.querySelector('[data-testid="route-pending"]');
    var visible = !!el;
    if (visible === window.__pendingVisible) return;
    window.__pendingVisible = visible;
    var extra = null;
    if (visible) {
      var r = el.getBoundingClientRect();
      var sidebar = document.querySelector('[data-slot="sidebar"]');
      var sr = sidebar ? sidebar.getBoundingClientRect() : null;
      extra = {
        rect: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) },
        text: (el.innerText || '').slice(0, 40),
        sidebarRect: sr ? { x: Math.round(sr.x), w: Math.round(sr.width) } : null,
        headerHeight: (function () {
          var h = document.querySelector('[data-slot="sidebar-inset"] header, header');
          return h ? Math.round(h.getBoundingClientRect().height) : null;
        })(),
        reportTableVisible: (function () {
          var t = document.querySelector('table tbody tr');
          if (!t) return false;
          var r = t.getBoundingClientRect();
          return r.width > 0 && r.height > 0;
        })(),
      };
    }
    record(visible ? 'show' : 'hide', extra);
  }
  var mo = new MutationObserver(check);
  mo.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['data-testid'] });
  window.__pendingObserver = mo;
  check();
  return true;
})();
"""

READ_LOG_JS = 'return window.__pendingLog || [];'


def throttle(drv, latency_ms, throughput_bps):
    drv.execute_cdp_cmd('Network.enable', {})
    drv.execute_cdp_cmd('Network.emulateNetworkConditions', {
        'offline': False,
        'latency': latency_ms,
        'downloadThroughput': throughput_bps,
        'uploadThroughput': throughput_bps,
        'connectionType': 'cellular3g' if throughput_bps > 0 else 'wifi',
    })


def unthrottle(drv):
    drv.execute_cdp_cmd('Network.emulateNetworkConditions', {
        'offline': False,
        'latency': 0,
        'downloadThroughput': -1,
        'uploadThroughput': -1,
        'connectionType': 'wifi',
    })


def drain_perf(drv):
    try:
        drv.get_log('performance')
    except Exception:
        pass


def perf_requests(drv, since_upsert=None):
    """解析 performance log → 请求列表（含耗时）。since_upsert 用 CDP timestamp 过滤。"""
    try:
        entries = drv.get_log('performance')
    except Exception:
        return []
    started = {}
    out = []
    for entry in entries:
        try:
            msg = json.loads(entry['message'])['message']
        except Exception:
            continue
        method = msg.get('method')
        params = msg.get('params') or {}
        if method == 'Network.requestWillBeSent':
            rid = params['requestId']
            started[rid] = {
                'url': params['request']['url'],
                'method': params['request']['method'],
                'type': params.get('type', ''),
                't0': params['timestamp'],
                'startWall': params.get('wallTime'),
            }
        elif method == 'Network.responseReceived':
            rid = params['requestId']
            if rid in started:
                started[rid]['status'] = params['response']['status']
        elif method in ('Network.loadingFinished', 'Network.loadingFailed'):
            rid = params['requestId']
            s = started.pop(rid, None)
            if not s:
                continue
            dur_ms = round((params['timestamp'] - s['t0']) * 1000)
            if since_upsert is not None and s['t0'] < since_upsert:
                continue
            out.append({
                'url': s['url'],
                'method': s['method'],
                'type': s['type'],
                'status': s.get('status'),
                'durationMs': dur_ms,
                'failed': method == 'Network.loadingFailed',
                'errorText': params.get('errorText') if method == 'Network.loadingFailed' else None,
                '_t0': s['t0'],
            })
    return out


def set_viewport(drv, w, h):
    drv.execute_cdp_cmd('Emulation.setDeviceMetricsOverride',
                        {'width': w, 'height': h, 'deviceScaleFactor': 1, 'mobile': False})
    time.sleep(1.0)


def apply_theme(drv, theme):
    drv.execute_script('window.localStorage.setItem(arguments[0], arguments[1]);', THEME_KEY, theme)


def open_report_center(drv):
    drv.get(BASE + '/report-center?status=published')
    WebDriverWait(drv, 90).until(lambda d: d.execute_script('return document.querySelectorAll("table tbody tr").length > 0'))
    time.sleep(1.5)


def click_first_report_row(drv):
    row = drv.find_element(By.CSS_SELECTOR, 'table tbody tr')
    row.find_element(By.CSS_SELECTOR, 'td:nth-child(2)').click()


def wait_pending_show(drv, timeout=20):
    def _has():
        log = drv.execute_script(READ_LOG_JS)
        return any(e['kind'] == 'show' for e in log)
    WebDriverWait(drv, timeout).until(lambda d: _has())
    return drv.execute_script(READ_LOG_JS)


def wait_detail(drv, timeout=180):
    """等路由待定态消失且报告详情页真实挂载（详情壳有「返回」行 + 顶部 h1）。"""
    def _ready():
        return drv.execute_script(r"""
          return !document.querySelector('[data-testid="route-pending"]')
            && location.pathname.indexOf('/report/') === 0
            && !!document.querySelector('h1')
            && (document.body.innerText || '').indexOf('返回') !== -1;
        """)
    WebDriverWait(drv, timeout).until(lambda d: _ready())
    time.sleep(1.2)


def set_cache_disabled(drv, disabled):
    drv.execute_cdp_cmd('Network.setCacheDisabled', {'cacheDisabled': bool(disabled)})


def pending_now(drv):
    return drv.execute_script('return !!document.querySelector(\'[data-testid="route-pending"]\')')


def page_usable_while_pending(drv):
    """待定期间壳层仍可用：侧栏链接可见、待定块在内容区（不覆盖侧栏）。"""
    return drv.execute_script(r"""
      return (function () {
        var el = document.querySelector('[data-testid="route-pending"]');
        if (!el) return {ok:false, reason:'no-pending'};
        var r = el.getBoundingClientRect();
        var links = Array.prototype.slice.call(document.querySelectorAll('a[href="/devices"]'));
        var link = links.length ? links[0] : null;
        var lr = link ? link.getBoundingClientRect() : null;
        var linkVisible = !!lr && lr.width > 0 && lr.height > 0 && lr.right > 0 && lr.left < innerWidth;
        var covered = false;
        if (lr) {
          var topEl = document.elementFromPoint(lr.x + lr.width/2, lr.y + lr.height/2);
          covered = topEl !== link && !(link.contains(topEl) || (topEl && topEl.contains(link)));
        }
        return {
          ok: linkVisible && !covered && r.x > 0,
          pendingRect: {x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width), h:Math.round(r.height)},
          sidebarLinkVisible: linkVisible,
          sidebarLinkCovered: covered,
          viewport: {w: innerWidth, h: innerHeight}
        };
      })();
    """)


def render_waterfall(rows, path_html, title):
    """把 CDP Network 事件渲染成一页瀑布图（用浏览器截图留证）。"""
    max_end = max([r['_startMs'] + r['durationMs'] for r in rows] or [1]) or 1
    body = []
    for r in rows:
        pct = max(0.5, (r['durationMs'] / max_end) * 100)
        left = (r['_startMs'] / max_end) * 100
        short = r['url'].split('?')[0]
        color = '#e11d48' if r['durationMs'] > 1000 else ('#f59e0b' if r['durationMs'] > 300 else '#10b981')
        body.append(
            '<tr><td class="u" title="{u}">{u}</td><td>{st}</td><td class="n">{d} ms</td>'
            '<td class="bar"><div style="margin-left:{l:.2f}%;width:{w:.2f}%;background:{c}"></div></td></tr>'.format(
                u=short, st=r.get('status') or ('失败' if r.get('failed') else '—'),
                d=r['durationMs'], l=left, w=pct, c=color))
    html = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>{title}</title>
<style>
 body{{background:#0b1020;color:#e5e7eb;font:13px/1.5 "Public Sans",system-ui,sans-serif;margin:0;padding:24px}}
 h1{{font-size:16px;margin:0 0 6px}}
 .sub{{color:#94a3b8;font-size:12px;margin-bottom:16px}}
 table{{width:100%;border-collapse:collapse}}
 th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid #1f2a44;vertical-align:middle}}
 th{{color:#94a3b8;font-weight:500;font-size:12px}}
 td.u{{max-width:520px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-family:Consolas,monospace;font-size:12px}}
 td.n{{white-space:nowrap;font-variant-numeric:tabular-nums}}
 td.bar{{width:36%}}
 td.bar div{{height:12px;border-radius:3px;min-width:3px}}
</style></head><body>
<h1>{title}</h1>
<div class="sub">数据源：Chrome DevTools Protocol <code>Network.*</code> 事件（requestWillBeSent → loadingFinished），
节流：延迟 {lat} ms / 带宽 {tp} KB/s。耗时 &gt;1s 标红，&gt;300ms 标黄。</div>
<table><thead><tr><th>请求</th><th>状态</th><th>耗时</th><th>时间轴</th></tr></thead><tbody>{rows}</tbody></table>
</body></html>""".format(title=title, rows=''.join(body), lat=THROTTLE_LATENCY_MS,
                        tp=THROTTLE_THROUGHPUT // 1024)
    with open(path_html, 'w', encoding='utf-8') as f:
        f.write(html)


def screenshot_url(drv, url_or_path, out_png):
    drv.get(url_or_path)
    time.sleep(1.0)
    drv.save_screenshot(out_png)


def main():
    os.makedirs(ART, exist_ok=True)
    token = get_token()
    drv = _driver()
    evidence = {'base': BASE, 'api': API, 'cases': {}, 'checks': RESULT}
    shots = []
    try:
        set_viewport(drv, 1680, 899)
        drv.get(BASE + '/login')
        WebDriverWait(drv, 60).until(lambda d: d.execute_script('return !!document.body'))
        time.sleep(1.5)
        drv.execute_script('window.localStorage.setItem(arguments[0], arguments[1]);', TOKEN_KEY, token)
        apply_theme(drv, 'light')

        # ===== C. 正常网络：不闪、不残留（先跑，此时未做任何 CDP 网络改造） =====
        print('\n===== C. 正常网络（不闪、不残留） =====')
        apply_theme(drv, 'light')
        open_report_center(drv)
        drv.execute_script(OBSERVER_JS)
        click_first_report_row(drv)
        t0 = time.time()
        wait_detail(drv, timeout=90)
        c1_elapsed = round(time.time() - t0, 1)
        log_c1 = drv.execute_script(READ_LOG_JS)
        c1_shows = [e for e in log_c1 if e['kind'] == 'show']
        check('C1: 正常网络点报告行 pending 不闪', len(c1_shows) == 0,
              json.dumps(log_c1, ensure_ascii=False)[:300])
        check('C1: 详情页已落地且无 pending 残留', (not pending_now(drv)) and drv.current_url.find('/report/') > 0,
              drv.current_url)

        # 侧栏切到另一个路由（新 chunk）；关 HTTP 缓存取「正常网络冷加载」基线
        open_report_center(drv)
        drv.execute_script(OBSERVER_JS)
        drain_perf(drv)
        set_cache_disabled(drv, True)
        t1 = time.time()
        link = WebDriverWait(drv, 30).until(
            lambda d: d.find_element(By.CSS_SELECTOR, 'a[href="/devices"]'))
        link.click()
        WebDriverWait(drv, 90).until(
            lambda d: d.execute_script('return document.querySelectorAll(\'[role="tab"]\').length >= 3'))
        c2_elapsed = round(time.time() - t1, 1)
        time.sleep(1.0)
        set_cache_disabled(drv, False)
        log_c2 = drv.execute_script(READ_LOG_JS)
        c2_shows = [e for e in log_c2 if e['kind'] == 'show']
        normal_reqs = perf_requests(drv)
        normal_chunks = [r['durationMs'] for r in normal_reqs if '/static/js/async/' in r['url']]
        check('C2: 侧栏切页（新 chunk）pending 不闪', len(c2_shows) == 0,
              json.dumps(log_c2, ensure_ascii=False)[:300])
        check('C2: 切页后页面已落地且无 pending 残留', not pending_now(drv), drv.current_url)
        shot_c = os.path.join(ART, 'C_after_sidebar_nav_light.png')
        drv.save_screenshot(shot_c)
        shots.append(shot_c)
        evidence['cases']['C_normal_network'] = {
            'detail_nav': {'shows': c1_shows, 'url': drv.current_url, 'elapsed': c1_elapsed},
            'sidebar_nav': {'shows': c2_shows, 'url': drv.current_url, 'elapsed': c2_elapsed,
                            'normal_async_chunk_durations_ms': sorted(normal_chunks)},
        }

        # ===== A. 节流：点报告行 → 必须出现待定态 =====
        print('\n===== A. 节流下点报告行（浅色） =====')
        open_report_center(drv)
        drv.execute_script(OBSERVER_JS)
        drain_perf(drv)
        set_cache_disabled(drv, True)   # 详情 chunk 必须真的走网络，不能被 HTTP 缓存秒回
        throttle(drv, THROTTLE_LATENCY_MS, THROTTLE_THROUGHPUT)
        click_first_report_row(drv)
        log = wait_pending_show(drv, timeout=40)
        show = [e for e in log if e['kind'] == 'show'][0]
        before_shot = time.time()
        shot_light = os.path.join(ART, 'A_pending_light_1680x899.png')
        drv.save_screenshot(shot_light)
        shots.append(shot_light)
        check('A: 节流下点报告行出现路由待定态', True, json.dumps(show, ensure_ascii=False))
        usable = page_usable_while_pending(drv)
        check('A: 待定期间侧栏保持可见且未被遮挡', bool(usable.get('ok')), json.dumps(usable, ensure_ascii=False))
        check('A: 待定文案为「页面加载中」', '页面加载中' in (show.get('extra') or {}).get('text', ''),
              (show.get('extra') or {}).get('text'))

        wait_detail(drv, timeout=180)
        detail_elapsed = round(time.time() - before_shot, 1)
        log = drv.execute_script(READ_LOG_JS)
        hides = [e for e in log if e['kind'] == 'hide']
        check('A: 详情页加载完成后待定态消失', pending_now(drv) is False and len(hides) >= 1,
              json.dumps(log, ensure_ascii=False)[:400])
        shot_detail = os.path.join(ART, 'A_detail_after_pending_light.png')
        drv.save_screenshot(shot_detail)
        shots.append(shot_detail)
        set_cache_disabled(drv, False)
        unthrottle(drv)
        time.sleep(1.0)

        reqs = perf_requests(drv, since_upsert=None)
        async_chunks = [r for r in reqs if '/static/js/async/' in r['url']]
        api_detail = [r for r in reqs if '/api/v1/reports/' in r['url']]
        slow_chunks = [r for r in async_chunks if r['durationMs'] >= 1000]
        check('A: CDP Network 证明详情路由 chunk 请求被拖慢（>=1s）', len(slow_chunks) >= 1,
              json.dumps([{'u': r['url'].split('/')[-1], 'ms': r['durationMs'], 'st': r['status']}
                          for r in async_chunks], ensure_ascii=False))
        base_t = min([r['_t0'] for r in reqs], default=0) if reqs else 0
        for r in reqs:
            r['_startMs'] = max(0, round((r['_t0'] - base_t) * 1000)) if '_t0' in r else 0
        evidence['cases']['A_throttled_light'] = {
            'pendingShow': show, 'pendingHide': hides, 'detailElapsedSec': detail_elapsed,
            'requests': [{k: v for k, v in r.items() if not k.startswith('_')} for r in reqs],
            'slowAsyncChunks': slow_chunks, 'detailApi': api_detail,
            'pageUsableWhilePending': usable, 'shot': shot_light,
        }

        # ===== B. 深色 =====
        print('\n===== B. 节流下点报告行（深色） =====')
        apply_theme(drv, 'dark')
        open_report_center(drv)
        drv.execute_script(OBSERVER_JS)
        drain_perf(drv)
        set_cache_disabled(drv, True)
        throttle(drv, THROTTLE_LATENCY_MS, THROTTLE_THROUGHPUT)
        click_first_report_row(drv)
        log_dark = wait_pending_show(drv, timeout=40)
        show_dark = [e for e in log_dark if e['kind'] == 'show'][0]
        theme_now = drv.execute_script('return document.documentElement.className')
        shot_dark = os.path.join(ART, 'B_pending_dark_1680x899.png')
        drv.save_screenshot(shot_dark)
        shots.append(shot_dark)
        check('B: 深色主题生效（html.dark）', 'dark' in (theme_now or ''), theme_now)
        check('B: 深色下同样出现路由待定态', True, json.dumps(show_dark, ensure_ascii=False))
        wait_detail(drv, timeout=180)
        set_cache_disabled(drv, False)
        unthrottle(drv)
        time.sleep(1.0)
        evidence['cases']['B_throttled_dark'] = {'pendingShow': show_dark, 'theme': theme_now, 'shot': shot_dark}

        # ===== D. console =====
        try:
            logs = drv.get_log('browser')
            severe = [l for l in logs if l.get('level') == 'SEVERE']
            check('D: 浏览器 console 无 SEVERE', len(severe) == 0, json.dumps(severe[:3], ensure_ascii=False))
            evidence['severe'] = severe[:10]
        except Exception as e:
            print('  [warn] console log 读取失败: %s' % e)

        # 瀑布图（浅色 A 的网络证据；切 file:// 会换源，放在所有在线用例之后）
        try:
            waterfall_html = os.path.join(ART, 'A_network_waterfall.html')
            rows = sorted([r for r in reqs if r['type'] in ('Script', 'Fetch', 'XHR', 'Document')],
                          key=lambda r: r['_t0'])[:20]
            render_waterfall(rows, waterfall_html,
                             'INT-2392 A 组：节流(%dms/%dKB/s)下点报告行的 Network 事件'
                             % (THROTTLE_LATENCY_MS, THROTTLE_THROUGHPUT // 1024))
            wf_shot = os.path.join(ART, 'A_network_waterfall.png')
            screenshot_url(drv, 'file:///' + waterfall_html.replace('\\', '/'), wf_shot)
            shots.append(wf_shot)
        except Exception as e:
            print('  [warn] 瀑布图生成失败: %s' % e)

    finally:
        try:
            unthrottle(drv)
        except Exception:
            pass
        drv.quit()

    with open(os.path.join(ART, 'evidence_int2392.json'), 'w', encoding='utf-8') as f:
        json.dump(evidence, f, ensure_ascii=False, indent=2)
    print('\n==== SUMMARY ====')
    passed = sum(1 for r in RESULT if r['ok'])
    print('checks: %d/%d passed' % (passed, len(RESULT)))
    for r in RESULT:
        if not r['ok']:
            print('  [FAIL] %s | %s' % (r['name'], r['detail']))
    print('artifacts: ' + ART)
    return 0 if passed == len(RESULT) else 1


if __name__ == '__main__':
    sys.exit(main())
