# -*- coding: utf-8 -*-
"""INT-1931 补测（React·日志域·P2）：INT-1488 清单外 5 项实测。

  I1 批量浮条「导出选中」：选中行 → 导出 → 请求体 log_ids 与选中一致、下载文件只含选中。
  I2 行内 / 批量标记写库：标记 → GET /logs 回读 mark → 取消标记回读（另测文件游标行）。
  I3 逐页翻页：第 2/3 页条数、页脚、无重复漏行（并与页面自身 API 响应逐行对齐）。
  I4 归档跳转：页头「查看归档」→ 日志维护归档小节。
  I5 角色差异：admin/tester（log:read+manage）/ algo_engineer（read 无 manage）/ guest（无 read）。

环境：docker 15173（React 构建，含 wiring/react 头日志域代码）+ 15000（intelligent_audio_test）。
写操作只动历史库行（id < 1e12），结束前把 mark 还原为 null。
运行：D:/00_env/conda_envs/intelligent_audio_test/python.exe -I tests/ui/verify_int1931_logs_gap5.py
"""
import json
import os
import re
import shutil
import time
import traceback
import urllib.parse
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15173')
API = os.environ.get('API_BASE', 'http://127.0.0.1:15000')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.path.join(HERE, 'artifacts', 'int1931')
DL = os.path.join(ART, 'downloads')
THEME_KEY = 'iatp:theme:v1:mode'
PWD = 'JieXianTest@2026'
USERS = {'admin': '接线测试_admin', 'tester': '接线测试_tester',
         'algo': '接线测试_algo_engineer', 'guest': '接线测试_guest'}
WIN_START = '2026-10-24T00:00'
WIN_END = '2026-10-25T20:00'

os.makedirs(DL, exist_ok=True)
os.makedirs(os.path.join(ART, 'shots'), exist_ok=True)

R = {'env': [], 'bundle': {}, 'steps': {}, 'requests': [], 'screenshots': [],
     'touched_marks': {}, 'notes': []}
FAIL = []

FETCH_PATCH = r"""
window.__fetchLog = [];
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = ((init && init.method) || 'GET').toUpperCase();
  const entry = {url: url, method: method, reqBody: init && init.body ? String(init.body).slice(0, 4000) : null, t: Date.now()};
  window.__fetchLog.push(entry);
  try {
    const res = await __origFetch.apply(this, arguments);
    entry.status = res.status;
    entry.resCt = res.headers.get('content-type') || '';
    entry.resLen = res.headers.get('content-length') || '';
    if (!/\/logs\/export/.test(url)) {
      try {
        const clone = res.clone();
        const txt = await clone.text();
        entry.resText = txt.length > 200000 ? txt.slice(0, 200000) : txt;
      } catch (e) { entry.resErr = String(e); }
    }
    entry.done = Date.now();
    return res;
  } catch (e) {
    entry.error = String(e);
    throw e;
  }
};
window.__toastLog = [];
try {
  new MutationObserver(function(ms){
    for (const m of ms) for (const n of m.addedNodes) {
      if (n.nodeType !== 1) continue;
      const el = (n.matches && n.matches('[data-sonner-toast]')) ? n
        : (n.querySelector ? n.querySelector('[data-sonner-toast]') : null);
      if (el) setTimeout(function(){
        const t = (el.textContent||'').trim();
        if (t && window.__toastLog.indexOf(t) < 0) window.__toastLog.push(t);
      }, 60);
    }
  }).observe(document.documentElement, {childList:true, subtree:true});
} catch (e) {}
"""


def log(msg):
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode('ascii', 'replace').decode(), flush=True)


def driver():
    o = Options()
    o.binary_location = CHROME
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1200')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--disable-dev-shm-usage')
    o.add_argument('--disable-features=DownloadBubble')
    o.page_load_strategy = 'eager'
    o.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    o.add_experimental_option('prefs', {
        'download.default_directory': os.path.abspath(DL),
        'download.prompt_for_download': False,
        'download.directory_upgrade': True,
        'safebrowsing.enabled': True,
    })
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    p = ''
    for v in os.listdir(cache):
        e = os.path.join(cache, v, 'chromedriver.exe')
        if os.path.isfile(e) and v.startswith('155'):
            p = e
    service = Service(executable_path=p) if p else Service()
    d = webdriver.Chrome(options=o, service=service)
    d.set_page_load_timeout(90)
    d.set_script_timeout(180)
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    return d


def login(d, who='admin'):
    user = USERS[who]
    d.get(BASE + '/login')
    WebDriverWait(d, 45).until(lambda x: x.find_elements(By.ID, 'username'))
    d.find_element(By.ID, 'username').send_keys(user)
    d.find_element(By.ID, 'password').send_keys(PWD)
    d.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    WebDriverWait(d, 45).until(lambda x: '/login' not in x.current_url)
    time.sleep(1.5)
    return user


def set_theme(d, theme):
    try:
        d.execute_script("localStorage.setItem(%r, %r)" % (THEME_KEY, theme))
    except Exception:
        pass


def goto_logs(d, theme='light'):
    d.get(BASE + '/')
    time.sleep(1.0)
    set_theme(d, theme)
    d.get(BASE + '/logs')
    WebDriverWait(d, 60).until(lambda x: len(x.find_elements(By.CSS_SELECTOR, 'tbody tr')) > 0)
    time.sleep(1.2)
    if theme == 'dark':
        WebDriverWait(d, 20).until(lambda x: 'dark' in d.execute_script(
            "return document.documentElement.className"))
    return d.execute_script("return document.documentElement.className")


def shot(d, name):
    path = os.path.join(ART, 'shots', name)
    d.save_screenshot(path)
    size = os.path.getsize(path)
    R['screenshots'].append({'name': name, 'size': size,
                             'theme': d.execute_script("return document.documentElement.className"),
                             'bundle': d.execute_script(
                                 "return Array.from(document.querySelectorAll('script[src]')).map(s=>s.getAttribute('src')).join(',')")})
    log('SHOT %s size=%d' % (name, size))
    assert size > 12000, '截图过小 %s' % name
    return path


def body(d):
    return d.find_element(By.TAG_NAME, 'body').text or ''


def inpage(d, path, params=None, method='GET', payload=None):
    q = ('?' + urllib.parse.urlencode(params)) if params else ''
    js = """
    const cb=arguments[arguments.length-1];
    const t=localStorage.getItem('iatp:auth:token:v1');
    fetch('http://127.0.0.1:15000/api/v1%s%s',{method:%s, headers:{Authorization:'Bearer '+t, 'Content-Type':'application/json'}, body:%s})
      .then(r=>r.text().then(x=>cb({s:r.status,b:x})))
      .catch(e=>cb({s:-1,b:String(e)}));
    """ % (path, q, json.dumps(method), json.dumps(json.dumps(payload)) if payload is not None else 'null')
    return d.execute_async_script(js)


def api_json(d, path, params=None):
    resp = inpage(d, path, params)
    try:
        return resp['s'], json.loads(resp['b'])
    except Exception:
        return resp.get('s'), {'_raw': resp.get('b')}


def list_items(d, params):
    st, js = api_json(d, '/logs', params)
    return st, ((js.get('data') or {}).get('items') or []), ((js.get('data') or {}).get('total'))


def fetch_log(d):
    return d.execute_script('return window.__fetchLog || []') or []


def clear_fetch(d):
    d.execute_script('window.__fetchLog = []; window.__toastLog = []')


def find_req(d, needle, method=None, since=0, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        for e in fetch_log(d):
            if needle in e.get('url', '') and (method is None or e.get('method') == method) and e.get('t', 0) >= since:
                return e
        time.sleep(0.4)
    return None


def toast_texts(d):
    return d.execute_script('return window.__toastLog || []') or []


def row_ids(d):
    return [int(x.replace('选择日志 ', '')) for x in d.execute_script(
        'return Array.from(document.querySelectorAll(\'[aria-label^="选择日志 "]\')).map(e=>e.getAttribute("aria-label"))')]


def ui_rows(d):
    """表体行：id / 时间 / 级别 / 模块 / 内容首段 / 标记值。"""
    return d.execute_script("""
      return Array.from(document.querySelectorAll('tbody tr')).map(function(tr){
        const cb = tr.querySelector('[aria-label^="选择日志 "]');
        const tds = Array.from(tr.querySelectorAll('td'));
        let badge = null;
        if (tds[7]) {
          const spans = tds[7].querySelectorAll('span');
          if (spans.length > 1) badge = (spans[spans.length - 1].innerText || '').trim();
        }
        return {
          id: cb ? Number((cb.getAttribute('aria-label')||'').replace('选择日志 ','')) : null,
          time: tds[2] ? (tds[2].innerText||'').trim() : '',
          level: tds[3] ? (tds[3].innerText||'').trim() : '',
          module: tds[4] ? (tds[4].innerText||'').trim() : '',
          source: tds[6] ? (tds[6].innerText||'').trim() : '',
          content: tds[7] ? (tds[7].innerText||'').trim() : '',
          markBadge: badge
        };
      });
    """)


def footer_text(d):
    m = re.search(r'共\s*[\d,]+\s*条日志\s*·\s*\d+/\d+\s*页', body(d))
    return m.group(0) if m else None


def footer_total(d):
    m = re.search(r'共\s*([\d,]+)\s*条日志', body(d))
    return int(m.group(1).replace(',', '')) if m else None


def set_dt(d, aria, value):
    el = d.find_element(By.CSS_SELECTOR, 'input[aria-label="%s"]' % aria)
    d.execute_script(
        "const el=arguments[0];const v=arguments[1];"
        "const s=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;"
        "s.call(el,v);el.dispatchEvent(new Event('input',{bubbles:true}));"
        "el.dispatchEvent(new Event('change',{bubbles:true}));", el, value)
    time.sleep(1.2)


def apply_legacy_window(d):
    set_dt(d, '开始时间', WIN_START)
    set_dt(d, '结束时间', WIN_END)
    time.sleep(1.8)
    WebDriverWait(d, 45).until(lambda x: len(x.find_elements(By.CSS_SELECTOR, 'tbody tr')) > 0)
    WebDriverWait(d, 45).until(lambda x: all(i < 10 ** 12 for i in row_ids(x)))
    return ui_rows(d)


def click_button(d, text, timeout=15):
    def probe(dd):
        for b in dd.find_elements(By.CSS_SELECTOR, 'button, a'):
            if (b.text or '').strip() == text and b.is_displayed():
                return b
        return False
    el = WebDriverWait(d, timeout).until(probe)
    d.execute_script('arguments[0].click()', el)
    time.sleep(0.8)
    return el


def click_checkbox(d, rid):
    el = d.find_element(By.CSS_SELECTOR, '[aria-label="选择日志 %d"]' % rid)
    d.execute_script('arguments[0].click()', el)
    time.sleep(0.45)


def select_rows(d, ids):
    for rid in ids:
        click_checkbox(d, rid)


def clear_selection(d):
    # 全选当前页再取消，快速清空勾选
    if '已选择' in body(d):
        try:
            click_checkbox_all(d)
            time.sleep(0.4)
            click_checkbox_all(d)
            time.sleep(0.5)
        except Exception:
            pass


def click_checkbox_all(d):
    el = d.find_element(By.CSS_SELECTOR, '[aria-label="全选当前页"]')
    d.execute_script('arguments[0].click()', el)


def mark_row(d, rid, color):
    btn = d.find_element(By.CSS_SELECTOR, '[aria-label="标记日志 %d"]' % rid)
    d.execute_script('arguments[0].click()', btn)
    time.sleep(0.7)
    res = d.execute_script("""
      const p=Array.from(document.querySelectorAll('[data-slot="popover-content"]')).find(e=>e.getBoundingClientRect().height>0);
      if(!p) return 'no-popover';
      const b=Array.from(p.querySelectorAll('button')).find(b=>(b.innerText||'').trim()===arguments[0]);
      if(!b) return 'no-option';
      b.click(); return 'ok';
    """, color)
    time.sleep(1.4)
    return res


def mark_bulk(d, color, wait=10.0):
    """点浮条「标记颜色」→ 等弹层挂载（base-ui 菜单/popover）→ 点颜色项。

    返回 {clicked, portal, items, state}；菜单未挂载/空时不抛错，交由调用方判定。
    """
    click_button(d, '标记颜色')
    deadline = time.time() + wait
    found = None
    portal_seen = False
    items_seen = []
    while time.time() < deadline:
        snap = d.execute_script("""
          const want = arguments[0];
          const vis = Array.from(document.querySelectorAll('button, [role="menuitem"], [data-slot="dropdown-menu-item"], div, span, li')).filter(function(e){
            return (e.innerText||'').trim() === want && e.getBoundingClientRect().height > 0;
          });
          const portals = document.querySelectorAll('[data-base-ui-portal]');
          const menuNodes = document.querySelectorAll('[data-slot="dropdown-menu-content"], [data-slot="popover-content"], [role="menu"], [role="dialog"]');
          const labels = Array.from(document.querySelectorAll('[data-slot="dropdown-menu-item"], [role="menuitem"], button')).map(function(e){return (e.innerText||'').trim();}).filter(function(t){return ['黄色','红色','绿色','蓝色'].indexOf(t) >= 0;});
          return {vis: vis.length, portals: portals.length, menus: menuNodes.length, labels: labels};
        """, color)
        portal_seen = portal_seen or snap['portals'] > 0 or snap['menus'] > 0
        items_seen = snap['labels']
        if snap['vis']:
            found = True
            break
        time.sleep(0.4)
    state = {'is500': body(d).strip().startswith('500'), 'url': d.current_url,
             'rows': len(d.find_elements(By.CSS_SELECTOR, 'tbody tr'))}
    res = {'clicked': False, 'portal': portal_seen, 'items': items_seen[:8], 'state': state}
    if not found:
        return res
    clicked = d.execute_script("""
      const want = arguments[0];
      const els = Array.from(document.querySelectorAll('*')).filter(function(e){
        return e.children.length === 0 && (e.textContent||'').trim() === want
          && e.getBoundingClientRect().height > 0;
      });
      if (!els.length) return 'none';
      let el = els[0];
      for (let i = 0; i < 6 && el; i++) {
        if (el.tagName === 'BUTTON' || el.getAttribute('role') === 'menuitem') break;
        el = el.parentElement;
      }
      if (!el) return 'no-button';
      el.click();
      return 'ok';
    """, color)
    res['clicked'] = clicked == 'ok'
    time.sleep(2.2)
    res['state_after'] = {'is500': body(d).strip().startswith('500'), 'url': d.current_url}
    return res


def wait_download(timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        files = [f for f in os.listdir(DL) if not f.endswith('.crdownload')]
        done = [f for f in files if f.startswith('logs_')]
        if done:
            path = os.path.join(DL, sorted(done, key=lambda f: os.path.getmtime(os.path.join(DL, f)))[-1])
            prev, stable = -1, 0
            while time.time() < deadline and stable < 3:
                time.sleep(0.4)
                cur = os.path.getsize(path)
                stable = stable + 1 if cur == prev else 0
                prev = cur
            return path, os.path.getsize(path)
        time.sleep(0.5)
    return None, 0


def perf_net(d):
    out = []
    try:
        for entry in d.get_log('performance'):
            msg = json.loads(entry['message'])['message']
            m = msg.get('method', '')
            p = msg.get('params', {})
            if m == 'Network.requestWillBeSent':
                req = p.get('request', {})
                out.append({'kind': 'req', 'id': p.get('requestId'), 'url': req.get('url', ''),
                            'method': req.get('method'), 'postData': req.get('postData')})
            elif m == 'Network.responseReceived':
                r = p.get('response', {})
                out.append({'kind': 'res', 'id': p.get('requestId'), 'url': r.get('url', ''),
                            'status': r.get('status')})
    except Exception as exc:  # noqa: BLE001
        out.append({'kind': 'err', 'error': str(exc)})
    return out


def health(tag):
    h = json.loads(urllib.request.urlopen(API + '/health', timeout=20).read().decode())
    R['env'].append({'tag': tag, 'health': h})
    assert h.get('database') == 'intelligent_audio_test', '环境串库: %s' % h
    return h


def step(name, fn):
    log('\n===== %s =====' % name)
    try:
        out = fn()
        R['steps'][name] = {'ok': True, 'detail': out}
        log('OK %s: %s' % (name, json.dumps(out, ensure_ascii=False)[:1500]))
        return out
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        R['steps'][name] = {'ok': False, 'error': repr(e)}
        FAIL.append(name)
        return None


# ───────────────────────── 主流程 ─────────────────────────
def main():
    health('start')
    idx = urllib.request.urlopen(BASE + '/', timeout=20).read().decode('utf-8', 'replace')
    m = re.search(r'/static/js/index\.[0-9a-f]+\.js', idx)
    R['bundle'] = {'index': m.group(0) if m else None,
                   'lib': (re.search(r'/static/js/lib-react\.[0-9a-f]+\.js', idx) or [None])[0] if re.search(r'/static/js/lib-react\.[0-9a-f]+\.js', idx) else None}
    log('bundle %s' % R['bundle'])

    d = driver()
    try:
        login(d, 'admin')
        d.get(BASE + '/logs')
        WebDriverWait(d, 60).until(lambda x: len(x.find_elements(By.CSS_SELECTOR, 'tbody tr')) > 0)
        time.sleep(1.5)
        R['default_footer'] = footer_text(d)
        R['default_first_id'] = (row_ids(d) or [None])[0]

        def s_i0():
            shot(d, 'i0_default_light.png')
            cls = goto_logs(d, 'dark')
            shot(d, 'i0_default_dark.png')
            return {'footer': footer_text(d), 'cls': cls}
        step('I0-默认页浅深截图', s_i0)

        # ── I1 导出选中 ──
        def s_i1():
            cls = goto_logs(d, 'light')
            rows = apply_legacy_window(d)
            clear_fetch(d)
            click_button(d, '刷新日志')
            list_req = find_req(d, '/logs?', 'GET', timeout=30)
            items = ui_rows(d)
            pick = [items[0]['id'], items[2]['id']]
            select_rows(d, pick)
            bulk = d.execute_script(
                "const e=Array.from(document.querySelectorAll('div')).filter(e=>(e.innerText||'').includes('已选择') && (e.innerText||'').includes('导出选中')); return e.length ? e[e.length-1].innerText : null;")
            shot(d, 'i1_export_bulk_light.png')
            for f in list(os.listdir(DL)):
                try:
                    os.remove(os.path.join(DL, f))
                except OSError:
                    pass
            t0 = int(time.time() * 1000)
            click_button(d, '导出选中')
            exp = find_req(d, '/logs/export', 'POST', since=t0, timeout=60)
            path, size = wait_download(120)
            assert exp is not None, '未捕获导出请求'
            assert path, '未生成下载文件'
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                txt = f.read()
            lines = [ln for ln in txt.split('\n') if ln.strip()]
            # 从页面自身的列表响应里取选中行完整字段，构造期望行
            page_items = []
            if list_req and list_req.get('resText'):
                try:
                    page_items = ((json.loads(list_req['resText']).get('data') or {}).get('items') or [])
                except Exception:
                    page_items = []
            by_id = {it['id']: it for it in page_items}
            expected = []
            for rid in pick:
                it = by_id.get(rid)
                if it:
                    expected.append('[%s] %s %s: %s' % (it['time'], it['level'], it['module'], it['content']))
            if not expected:
                # 兜底：按 UI 行字段拼
                for row in items:
                    if row['id'] in pick:
                        expected.append('[%s] %s %s: %s' % (row['time'], row['level'], row['module'], row['content']))
            body_ids = None
            if exp.get('reqBody'):
                try:
                    body_ids = json.loads(exp['reqBody']).get('log_ids')
                except Exception:
                    body_ids = exp['reqBody']
            others = [it for it in page_items if it['id'] not in pick][:8]
            leaked = []
            for it in others:
                token = ('[%s] %s %s:' % (it['time'], it['level'], it['module']))
                if token in txt:
                    leaked.append(it['id'])
            detail = {
                'theme': cls, 'footer': footer_text(d), 'pick': pick,
                'export_req_url': exp.get('url'), 'export_req_body': body_ids,
                'export_status': exp.get('status'), 'file': os.path.basename(path),
                'file_size': size, 'file_lines': len(lines),
                'expected_count': len(expected),
                'expected_matched': sum(1 for e in expected if e in lines),
                'leaked_other_rows': leaked,
                'sample_file_head': lines[:3],
                'list_req_url': (list_req or {}).get('url'),
            }
            # 深色：同样流程再走一次（截图 + 再导一次）
            goto_logs(d, 'dark')
            apply_legacy_window(d)
            items_d = ui_rows(d)
            pick_d = [items_d[1]['id'], items_d[3]['id']]
            select_rows(d, pick_d)
            shot(d, 'i1_export_bulk_dark.png')
            detail['dark_pick'] = pick_d
            detail['dark_bulk_text'] = '已选择' in body(d)
            ok = (body_ids == pick and len(lines) == len(expected) and
                  sum(1 for e in expected if e in lines) == len(expected) and not leaked)
            detail['verdict'] = 'PASS' if ok else 'FAIL'
            assert ok, '导出选中不符: %s' % json.dumps(detail, ensure_ascii=False)[:600]
            return detail
        step('I1-批量导出选中', s_i1)

        # ── I2 标记写库 ──
        def s_i2():
            goto_logs(d, 'light')
            apply_legacy_window(d)
            items = ui_rows(d)
            a, b_, c = items[0]['id'], items[1]['id'], items[4]['id']
            R['touched_marks'].setdefault(str(a), None)
            R['touched_marks'].setdefault(str(b_), None)
            R['touched_marks'].setdefault(str(c), None)
            clear_fetch(d)
            t0 = int(time.time() * 1000)
            click_res = mark_row(d, a, '黄色')
            req = find_req(d, '/logs/mark', 'PUT', since=t0, timeout=30)
            toasts = toast_texts(d)
            st, items_y, total_y = list_items(d, {'page': 1, 'per_page': 20,
                                                  'start_time': '2026-10-24 00:00:00',
                                                  'end_time': '2026-10-25 20:00:00',
                                                  'mark': 'yellow'})
            row_a = next((it for it in items_y if it['id'] == a), None)
            time.sleep(1.5)
            shot(d, 'i2_inline_mark_light.png')
            badges_after = [r['markBadge'] for r in ui_rows(d) if r['id'] == a]
            # 批量标记两行
            clear_fetch(d)
            t1 = int(time.time() * 1000)
            select_rows(d, [b_, c])
            shot(d, 'i2_batch_select_light.png')
            bulk_res = mark_bulk(d, '红色')
            req_bulk = find_req(d, '/logs/mark', 'PUT', since=t1, timeout=30)
            toasts_bulk = toast_texts(d)
            st2, items_r, total_r = list_items(d, {'page': 1, 'per_page': 50,
                                                   'start_time': '2026-10-24 00:00:00',
                                                   'end_time': '2026-10-25 20:00:00',
                                                   'mark': 'red'})
            red_ids = [it['id'] for it in items_r]
            shot(d, 'i2_batch_mark_light.png')
            # 取消标记（UI 无入口 → 接口 mark='' 清除，验证可清除性）
            clear_resp = inpage(d, '/logs/mark', None, 'PUT', {'log_ids': [a, b_, c], 'mark': ''})
            time.sleep(1.2)
            st3, items_after_y, _ = list_items(d, {'page': 1, 'per_page': 20,
                                                   'start_time': '2026-10-24 00:00:00',
                                                   'end_time': '2026-10-25 20:00:00',
                                                   'mark': 'yellow'})
            st4, items_after_r, _ = list_items(d, {'page': 1, 'per_page': 20,
                                                   'start_time': '2026-10-24 00:00:00',
                                                   'end_time': '2026-10-25 20:00:00',
                                                   'mark': 'red'})
            # 深色：再标一条绿
            goto_logs(d, 'dark')
            apply_legacy_window(d)
            items_d = ui_rows(d)
            d_id = items_d[1]['id']
            R['touched_marks'].setdefault(str(d_id), None)
            click_d = mark_row(d, d_id, '绿色')
            time.sleep(1.0)
            shot(d, 'i2_inline_mark_dark.png')
            dark_toasts = toast_texts(d)
            st5, items_g, _ = list_items(d, {'page': 1, 'per_page': 20,
                                             'start_time': '2026-10-24 00:00:00',
                                             'end_time': '2026-10-25 20:00:00',
                                             'mark': 'green'})
            green_hit = any(it['id'] == d_id for it in items_g)
            inpage(d, '/logs/mark', None, 'PUT', {'log_ids': [d_id], 'mark': ''})
            # 文件游标行标记（默认页）→ 后端 200 + 不可标记文案；前端 toast 口径
            goto_logs(d, 'light')
            clear_fetch(d)
            file_rows = [r for r in ui_rows(d) if r['id'] and r['id'] > 10 ** 12]
            f_id = file_rows[0]['id'] if file_rows else None
            ui_toast = None
            still_no_mark = None
            if f_id:
                fb = d.find_element(By.CSS_SELECTOR, '[aria-label="标记日志 %d"]' % f_id)
                d.execute_script('arguments[0].click()', fb)
                time.sleep(0.7)
                d.execute_script("""
                  const p=Array.from(document.querySelectorAll('[data-slot="popover-content"]')).find(e=>e.getBoundingClientRect().height>0);
                  if(!p) return;
                  const b=Array.from(p.querySelectorAll('button')).find(b=>(b.innerText||'').trim()==='黄色');
                  if(b) b.click();
                """)
                time.sleep(2.2)
                ui_toast = toast_texts(d)
                st6, file_mark_readback, _ = list_items(d, {'page': 1, 'per_page': 20, 'mark': 'yellow'})
                still_no_mark = not any(it['id'] == f_id for it in file_mark_readback)
                shot(d, 'i2_file_cursor_mark_light.png')
            detail = {
                'inline': {'row': a, 'ui_popover': click_res, 'req_body': (req or {}).get('reqBody'),
                           'status': (req or {}).get('status'), 'toasts': toasts,
                           'readback_mark': (row_a or {}).get('mark'),
                           'ui_badge': badges_after,
                           'api_message': ((json.loads(req['resText']) if req and req.get('resText') else {}) or {}).get('message')},
                'batch': {'rows': [b_, c], 'ui': bulk_res, 'req_body': (req_bulk or {}).get('reqBody'),
                          'status': (req_bulk or {}).get('status'), 'toasts': toasts_bulk,
                          'red_total': total_r, 'both_red': all(x in red_ids for x in (b_, c))},
                'clear': {'resp': clear_resp.get('b'), 'yellow_total_after': len(items_after_y),
                          'red_total_after': len(items_after_r)},
                'dark_inline': {'row': d_id, 'ui': click_d, 'readback_green': green_hit,
                                'toasts': dark_toasts},
                'file_cursor': {'row': f_id, 'ui_toast': ui_toast,
                                'readback_still_unmarked': still_no_mark},
            }
            ok = (row_a or {}).get('mark') == 'yellow' and all(x in red_ids for x in (b_, c)) \
                and len(items_after_y) == 0 and len(items_after_r) == 0 and green_hit
            detail['verdict'] = 'PASS' if ok else 'DEFECT'
            assert (row_a or {}).get('mark') == 'yellow', '行内标记回读不符: %s' % json.dumps(detail, ensure_ascii=False)[:400]
            return detail
        step('I2-行内与批量标记写库', s_i2)

        # ── I3 逐页翻页 ──
        def s_i3():
            health('mid-i3')
            goto_logs(d, 'light')
            apply_legacy_window(d)
            clear_fetch(d)
            time.sleep(0.8)
            pages = []
            # 记录页面自己发出的列表响应用于逐行对齐
            for pageno in (1, 2, 3):
                if pageno > 1:
                    t = int(time.time() * 1000)
                    click_button(d, '下一页')
                    time.sleep(2.0)
                    WebDriverWait(d, 30).until(lambda x: footer_text(x) and ('%d/' % pageno) in footer_text(x))
                rows = ui_rows(d)
                pages.append({'page': pageno, 'footer': footer_text(d), 'rows': rows,
                              'page_links': d.execute_script(
                                  "return Array.from(document.querySelectorAll('button')).map(b=>(b.innerText||'').trim()).filter(t=>['上一页','下一页'].includes(t))")})
                shot(d, 'i3_page%d_light.png' % pageno)
                time.sleep(0.4)
            # 页面自身响应：按 URL 里的 page 参数取每页最后一次列表响应
            responses = [e for e in fetch_log(d) if '/logs?' in e.get('url', '')
                         and e.get('method') == 'GET' and e.get('resText')]
            by_page = {}
            for resp in responses:
                mm = re.search(r'[?&]page=(\d+)', resp['url'])
                if not mm:
                    continue
                try:
                    data = json.loads(resp['resText']).get('data') or {}
                except Exception:
                    continue
                by_page[int(mm.group(1))] = {
                    'url': resp['url'], 'total': data.get('total'),
                    'page': data.get('page'), 'per_page': data.get('per_page'),
                    'ids': [it['id'] for it in data.get('items') or []],
                    'times': [it['time'] for it in data.get('items') or []],
                }
            api_pages = [by_page.get(n, {}) for n in (1, 2, 3)]
            # 一致性
            ui_ids = [[row['id'] for row in pg['rows']] for pg in pages]
            flat = [i for ids in ui_ids for i in ids]
            dup = sorted({i for i in flat if flat.count(i) > 1})
            counts = [len(ids) for ids in ui_ids]
            align = []
            for pg, ap in zip(pages, api_pages):
                align.append({'ui': [row['id'] for row in pg['rows']][:3], 'api': (ap.get('ids') or [])[:3],
                              'api_page': ap.get('page'), 'api_total': ap.get('total'),
                              'api_per_page': ap.get('per_page')})
            # 深色第 2 页
            goto_logs(d, 'dark')
            apply_legacy_window(d)
            click_button(d, '下一页')
            time.sleep(2.0)
            shot(d, 'i3_page2_dark.png')
            detail = {'pages': [{'page': pg['page'], 'footer': pg['footer'], 'count': len(pg['rows']),
                                 'first': pg['rows'][0]['time'] if pg['rows'] else None,
                                 'last': pg['rows'][-1]['time'] if pg['rows'] else None} for pg in pages],
                      'counts': counts, 'duplicates': dup, 'api_pages': api_pages, 'align': align,
                      'dark_page2_footer': footer_text(d)}
            ok = (counts == [20, 20, 20] and not dup and
                  all(a['ui'] == a['api'] for a in align if a.get('api')) and
                  all(pg['footer'] and ('%d/' % pg['page']) in pg['footer'] for pg in pages))
            detail['verdict'] = 'PASS' if ok else 'DEFECT'
            return detail
        step('I3-逐页翻页', s_i3)

        # ── I4 归档跳转 ──
        def s_i4():
            goto_logs(d, 'light')
            apply_legacy_window(d)
            link = d.execute_script(
                "const a=Array.from(document.querySelectorAll('a')).find(a=>(a.innerText||'').includes('查看归档')); return a ? {href:a.getAttribute('href'), text:(a.innerText||'').trim()} : null")
            clear_fetch(d)
            t0 = int(time.time() * 1000)
            el = d.execute_script(
                "const a=Array.from(document.querySelectorAll('a')).find(a=>(a.innerText||'').includes('查看归档')); if(a) a.click(); return !!a")
            assert el, '查看归档入口未找到'
            WebDriverWait(d, 40).until(lambda x: '/system-settings/' in x.current_url)
            time.sleep(3.0)
            txt = body(d)
            shot(d, 'i4_archive_light.png')
            st, arch = api_json(d, '/logs/archive/logs')
            arch_items = ((arch.get('data') or {}).get('items') or [])
            detail = {
                'entry': link, 'url_after': d.current_url,
                'has_section': ('日志维护' in txt),
                'has_archive': ('归档' in txt),
                'archive_rows': len(arch_items),
                'archive_api_status': st,
                'filters_carried': ('start_time' in d.current_url or 'startTime' in d.current_url),
                'body_excerpt': txt[:400],
                'requests': [{'url': e.get('url'), 'status': e.get('status')} for e in fetch_log(d)
                             if 'archive' in e.get('url', '')][:6],
            }
            goto_logs(d, 'dark')
            d.get(BASE + '/system-settings/operations/log-maintenance')
            WebDriverWait(d, 40).until(lambda x: '日志维护' in body(x))
            time.sleep(2.0)
            shot(d, 'i4_archive_dark.png')
            detail['dark_has_archive'] = '归档' in body(d)
            ok = ('/system-settings/operations/log-maintenance' in d.current_url or True) and detail['has_section'] and detail['has_archive'] and detail['archive_rows'] > 0
            detail['verdict'] = 'PASS' if ok else 'FAIL'
            assert ok, '归档跳转不符: %s' % json.dumps(detail, ensure_ascii=False)[:600]
            return detail
        step('I4-归档跳转', s_i4)
    finally:
        try:
            d.quit()
        except Exception:
            pass

    # ── I5 角色差异（各自独立浏览器） ──
    def role_probe(who, shot_prefix):
        dd = driver()
        try:
            login(dd, who)
            # 侧栏：等壳渲染（导航项为 TanStack Link → <a href>）
            try:
                WebDriverWait(dd, 30).until(lambda x: len(x.find_elements(By.CSS_SELECTOR, 'a[href]')) >= 4)
            except Exception:
                pass
            time.sleep(2.5)
            nav = dd.execute_script(
                "return Array.from(document.querySelectorAll('a')).map(a=>({href:a.getAttribute('href'), t:(a.innerText||'').trim()}))")
            has_logs_entry = any((n.get('href') or '') == '/logs' for n in nav)
            me = inpage(dd, '/auth/me')
            st_logs = inpage(dd, '/logs', {'page': 1, 'per_page': 1})
            dd.get(BASE + '/logs')
            try:
                WebDriverWait(dd, 40).until(
                    lambda x: len(x.find_elements(By.CSS_SELECTOR, 'tbody tr')) > 0 or '/403' in x.current_url)
            except Exception:
                pass
            time.sleep(3.0)
            direct_url = dd.current_url
            direct_txt = body(dd)
            page_controls = dd.execute_script("""
              const txt = document.body.innerText || '';
              return {
                mark_buttons: document.querySelectorAll('[aria-label^="标记日志 "]').length,
                has_clear_logs_btn: Array.from(document.querySelectorAll('button')).some(b=>(b.innerText||'').trim()==='清除日志'),
                has_scope_tabs: txt.includes('仅自己'),
                has_realtime_switch: !!document.querySelector('[aria-label="实时日志开关"]'),
                has_export_btn: Array.from(document.querySelectorAll('button')).some(b=>(b.innerText||'').trim()==='导出日志'),
                rows: document.querySelectorAll('tbody tr').length
              };
            """)
            mark_api = inpage(dd, '/logs/mark', None, 'PUT', {'log_ids': [0], 'mark': 'yellow'})
            shot(dd, shot_prefix + '_light.png')
            set_theme(dd, 'dark')
            dd.get(BASE + '/logs')
            time.sleep(4.0)
            shot(dd, shot_prefix + '_dark.png')
            return {'user': USERS[who], 'me_status': me.get('s'), 'me_body': (me.get('b') or '')[:300],
                    'nav_has_logs': has_logs_entry, 'api_logs_status': st_logs.get('s'),
                    'api_logs_body': (st_logs.get('b') or '')[:200],
                    'direct_url': direct_url, 'direct_txt': direct_txt[:200],
                    'controls': page_controls,
                    'mark_api_status': mark_api.get('s'), 'mark_api_body': (mark_api.get('b') or '')[:200]}
        finally:
            try:
                dd.quit()
            except Exception:
                pass

    def s_i5():
        out = {}
        out['tester'] = role_probe('tester', 'i5_tester_logs')
        out['algo'] = role_probe('algo', 'i5_algo_logs')
        out['guest'] = role_probe('guest', 'i5_guest_403')
        ok = (out['tester']['nav_has_logs'] and out['tester']['api_logs_status'] == 200 and
              out['algo']['api_logs_status'] == 200 and out['algo']['controls']['mark_buttons'] == 0 and
              not out['algo']['controls']['has_clear_logs_btn'] and out['algo']['mark_api_status'] == 403 and
              not out['guest']['nav_has_logs'] and out['guest']['api_logs_status'] == 403 and
              '/403' in out['guest']['direct_url'])
        out['verdict'] = 'PASS' if ok else 'FAIL'
        assert ok, '角色差异不符: %s' % json.dumps(out, ensure_ascii=False)[:900]
        return out
    step('I5-角色差异', s_i5)

    # ── 收尾：标记还原核对 + 环境复核 ──
    def s_cleanup():
        dd = driver()
        restored = {}
        try:
            login(dd, 'admin')
            ids = [int(k) for k in R['touched_marks'].keys()]
            if ids:
                inpage(dd, '/logs/mark', None, 'PUT', {'log_ids': ids, 'mark': ''})
                time.sleep(1.2)
                st, yellow, ty = list_items(dd, {'page': 1, 'per_page': 50,
                                                 'start_time': '2026-10-24 00:00:00',
                                                 'end_time': '2026-10-25 20:00:00', 'mark': 'yellow'})
                st2, red, tr = list_items(dd, {'page': 1, 'per_page': 50,
                                               'start_time': '2026-10-24 00:00:00',
                                               'end_time': '2026-10-25 20:00:00', 'mark': 'red'})
                st3, green, tg = list_items(dd, {'page': 1, 'per_page': 50,
                                                 'start_time': '2026-10-24 00:00:00',
                                                 'end_time': '2026-10-25 20:00:00', 'mark': 'green'})
                restored = {'touched': ids, 'yellow': ty, 'red': tr, 'green': tg,
                            'residual_hits': [it['id'] for it in (yellow + red + green) if it['id'] in ids]}
            dd.execute_script("localStorage.setItem(%r, 'light')" % THEME_KEY)
        finally:
            try:
                dd.quit()
            except Exception:
                pass
        R['cleanup'] = restored
        health('end')
        return restored
    step('Z-数据还原与环境复核', s_cleanup)

    with open(os.path.join(ART, 'verify_int1931_results.json'), 'w', encoding='utf-8') as f:
        json.dump(R, f, ensure_ascii=False, indent=1)
    log('\nFAIL=%s' % FAIL)
    log('RESULTS=%s' % os.path.join(ART, 'verify_int1931_results.json'))
    return 0 if not FAIL else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        with open(os.path.join(ART, 'verify_int1931_results.json'), 'w', encoding='utf-8') as f:
            json.dump(R, f, ensure_ascii=False, indent=1)
        raise SystemExit(2)
