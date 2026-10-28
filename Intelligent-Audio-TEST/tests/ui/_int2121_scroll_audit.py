# -*- coding: utf-8 -*-
"""INT-2121 验收：算法编辑 Sheet「高级配置→评估参数映射」滚动性能 + 功能回归。

用法：
  python _int2121_scroll_audit.py --base http://localhost:15290 --side fix
  python _int2121_scroll_audit.py --base http://localhost:15173 --side base

测量：向 form#algorithm-mutate-form（编辑 Sheet 唯一滚动容器）连续派发 5 屏滚轮，
rAF 采帧 + PerformanceObserver(longtask) 采长任务；1x 与 4x CPU 节流各 N 轮。
功能：分组行数/折叠/分页/搜索/徽章/行内下拉门户；浅/深色截图；Network 取真实接口。
"""
import argparse
import json
import os
import statistics
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
DRIVER = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver',
                      'win64', '155.0.8059.84', 'chromedriver.exe')
HERE = os.path.dirname(os.path.abspath(__file__))
ALGO = '小艺语音大模型'
USER, PWD = 'dev_user', 'dev_password'

START_JS = r"""
window.__rec = window.__rec || {};
window.__rec.frames = [];
window.__rec.lt = [];
try {
  window.__rec.po && window.__rec.po.disconnect();
  window.__rec.po = new PerformanceObserver(l => {
    for (const e of l.getEntries()) window.__rec.lt.push({start: e.startTime, duration: e.duration});
  });
  window.__rec.po.observe({entryTypes: ['longtask']});
} catch (e) { window.__rec.ltErr = String(e); }
window.__rec.on = true;
window.__rec.t0 = performance.now();
window.__rec.last = performance.now();
window.__rec.scrollEnd = 0;
window.__rec.tick = function (t) {
  if (!window.__rec.on) return;
  window.__rec.frames.push(t - window.__rec.last);
  window.__rec.last = t;
  window.__rec.raf = requestAnimationFrame(window.__rec.tick);
};
window.__rec.raf = requestAnimationFrame(window.__rec.tick);
return 'started';
"""

STOP_JS = r"""
window.__rec.on = false;
if (window.__rec.raf) cancelAnimationFrame(window.__rec.raf);
if (window.__rec.po) window.__rec.po.disconnect();
return {frames: window.__rec.frames.slice(2), longtasks: window.__rec.lt.slice(), ltErr: window.__rec.ltErr || null, t0: window.__rec.t0, scrollEnd: window.__rec.scrollEnd};
"""

FIND_EVAL_TABLE_JS = r"""
const trig = [...document.querySelectorAll('button')].find(b => (b.innerText || '').includes('评估参数映射'));
if (!trig) return {ok: false, why: 'trigger not found'};
let el = trig;
while (el && !el.querySelector('table')) el = el.parentElement;
if (!el) return {ok: false, why: 'root not found'};
window.__evalRoot = el;
window.__evalTable = el.querySelector('table');
return {ok: true};
"""

TABLE_STATS_JS = r"""
const t = window.__evalTable;
if (!t) return null;
const trs = [...t.querySelectorAll('tbody tr')];
const heads = [...t.querySelectorAll('tbody button[aria-expanded]')]
  .filter(b => /条\s*$/.test((b.innerText || '').replace(/\s+/g, ' ')));
return {
  rows: trs.length,
  group_heads: heads.length,
  data_rows: trs.filter(tr => tr.querySelectorAll('td').length > 1).length,
  add_rows: [...t.querySelectorAll('tbody button')].filter(b => (b.innerText || '').trim() === '添加映射').length,
  main_badges: heads.filter(b => (b.innerText || '').includes('主')).length,
  sub_badges: heads.filter(b => (b.innerText || '').includes('子')).length,
};
"""

# 展开评估参数映射 + 定位表并把表头滚到容器顶部附近
PREPARE_JS = r"""
const trig = [...document.querySelectorAll('button')].find(b => (b.innerText || '').includes('评估参数映射'));
if (!trig) return {ok: false, why: 'no trigger'};
const expanded = trig.getAttribute('aria-expanded') === 'true';
if (!expanded) { trig.click(); }
return {ok: true, wasExpanded: expanded};
"""

SCROLL_TO_TABLE_JS = r"""
const form = document.querySelector('#algorithm-mutate-form');
const t = window.__evalTable;
if (!form || !t) return null;
const fr = form.getBoundingClientRect();
const tr = t.getBoundingClientRect();
const newTop = form.scrollTop + (tr.top - fr.top) - 60;
form.scrollTop = Math.max(0, newTop);
const r = form.getBoundingClientRect();
return {
  x: Math.round(r.left + r.width / 2),
  y: Math.round(Math.max(120, Math.min(r.height - 120, r.height / 2))),
  scrollHeight: form.scrollHeight,
  clientHeight: form.clientHeight,
  width: Math.round(r.width), height: Math.round(r.height),
  scrollTop: Math.round(form.scrollTop),
};
"""

DETAIL_PREPARE_JS = r"""
// 详情弹窗：点「评估参数」页签；滚动容器 = DialogContent（role=dialog, overflow-y-auto）
const tab = [...document.querySelectorAll('[role=tab]')].find(b => (b.innerText || '').includes('评估参数'));
if (!tab) return {ok: false, why: 'eval tab not found'};
tab.click();
return {ok: true};
"""

DETAIL_SCROLL_JS = r"""
const dlg = document.querySelector('[role=dialog]');
if (!dlg) return null;
const panel = [...dlg.querySelectorAll('[role=tabpanel]')].find(p => (p.innerText || '').includes('映射') || (p.innerText || '').includes('参数'));
const target = panel || dlg;
const r = dlg.getBoundingClientRect();
return {
  x: Math.round(r.left + r.width / 2),
  y: Math.round(r.top + r.height * 0.7),
  scrollHeight: dlg.scrollHeight,
  clientHeight: dlg.clientHeight,
  width: Math.round(r.width), height: Math.round(r.height),
  scrollTop: Math.round(dlg.scrollTop),
};
"""


def pct(vals, p):
    if not vals:
        return None
    s = sorted(vals)
    k = max(0, min(len(s) - 1, int(round(p / 100 * len(s))) - 1))
    return s[k]


def stats(frames, longtasks, t0=None, scroll_end=None):
    if not frames:
        return {'n': 0}
    lts = [x['duration'] for x in longtasks]
    return {
        'n': len(frames),
        'avg': round(statistics.mean(frames), 2),
        'median': round(statistics.median(frames), 2),
        'p95': round(pct(frames, 95), 2),
        'max': round(max(frames), 2),
        'gt16_7_pct': round(100.0 * sum(1 for f in frames if f > 16.7) / len(frames), 2),
        'gt33_pct': round(100.0 * sum(1 for f in frames if f > 33) / len(frames), 2),
        'gt50_pct': round(100.0 * sum(1 for f in frames if f > 50) / len(frames), 2),
        'lt_count': len(lts),
        'lt_gt50': sum(1 for d in lts if d > 50),
        'lt_gt100': sum(1 for d in lts if d > 100),
        'lt_max': round(max(lts), 2) if lts else 0,
        'lt_detail': [{'start': round(x['start'], 1), 'dur': round(x['duration'], 1),
                       'during_scroll': (t0 is not None and x['start'] - t0 <= (scroll_end or 0) - t0)} for x in longtasks][:10],
    }


def make_driver(log_perf=False):
    o = Options()
    o.binary_location = CHROME
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1050')
    o.add_argument('--no-sandbox')
    if os.environ.get('INT2121_DISABLE_GPU', '0') == '1':
        o.add_argument('--disable-gpu')
    o.add_argument('--force-device-scale-factor=1')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--disable-dev-shm-usage')
    if log_perf:
        o.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    d = webdriver.Chrome(service=Service(DRIVER), options=o)
    d.set_page_load_timeout(90)
    return d


def login(d, base):
    d.get(base + '/login')
    WebDriverWait(d, 30).until(lambda x: x.find_elements(By.CSS_SELECTOR, '#username'))
    time.sleep(1.0)
    d.execute_script("""
      const u = document.querySelector('#username'); const p = document.querySelector('#password');
      const set = (el, v) => { const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set; s.call(el, v); el.dispatchEvent(new Event('input',{bubbles:true})); };
      set(u, arguments[0]); set(p, arguments[1]);
      document.querySelector('form').requestSubmit();
    """, USER, PWD)
    try:
        WebDriverWait(d, 40).until(lambda x: '/login' not in x.current_url)
    except Exception:
        if '/login' in d.current_url:
            raise RuntimeError('login failed, url=%s' % d.current_url)


def open_edit_sheet(d, base):
    d.get(base + '/AlgorithmConfig')
    WebDriverWait(d, 45).until(lambda x: x.find_elements(By.XPATH, "//tr[contains(., '%s')]" % ALGO))
    time.sleep(1.5)
    d.execute_script("""
      const row = [...document.querySelectorAll('tr')].find(r => r.innerText.includes(arguments[0]));
      const btn = row.querySelector('button[aria-label*="操作"]');
      if (!btn) return 'no menu btn';
      btn.click(); return 'clicked';
    """, ALGO)
    time.sleep(1.2)
    d.execute_script("""
      const item = [...document.querySelectorAll('[role=menuitem]')].find(m => (m.innerText || '').trim() === '编辑');
      if (!item) return 'no edit item';
      item.click(); return 'clicked';
    """)
    WebDriverWait(d, 30).until(lambda x: x.find_elements(By.XPATH, "//*[self::button or self::div][contains(., '高级配置')]"))
    time.sleep(1.5)
    # 展开高级配置
    d.execute_script("""
      const b = [...document.querySelectorAll('button')].find(x => (x.innerText || '').includes('高级配置'));
      if (!b) return 'no adv';
      b.click(); return 'clicked';
    """)
    time.sleep(2.0)
    r = d.execute_script(PREPARE_JS)
    WebDriverWait(d, 40).until(lambda x: x.execute_script(FIND_EVAL_TABLE_JS).get('ok'))
    time.sleep(2.5)
    return r


def measure_round(d, steps, delta, throttle=1, interval=0.03):
    d.execute_cdp_cmd('Emulation.setCPUThrottlingRate', {'rate': throttle})
    geo = d.execute_script(SCROLL_TO_TABLE_JS)
    time.sleep(0.8)
    d.execute_script(START_JS)
    time.sleep(0.3)
    for _ in range(steps):
        d.execute_cdp_cmd('Input.dispatchMouseEvent', {
            'type': 'mouseWheel', 'x': geo['x'], 'y': geo['y'],
            'deltaX': 0, 'deltaY': delta, 'pointerType': 'mouse',
        })
        time.sleep(interval)
    d.execute_script('window.__rec.scrollEnd = performance.now();')
    time.sleep(0.8)
    data = d.execute_script(STOP_JS)
    d.execute_cdp_cmd('Emulation.setCPUThrottlingRate', {'rate': 1})
    return stats(data['frames'], data['longtasks'], data.get('t0'), data.get('scrollEnd')), geo, data.get('ltErr')


GROUP_HEADS_JS = r"""
const t = window.__evalTable; if (!t) return null;
return [...t.querySelectorAll('tbody button[aria-expanded]')]
  .filter(b => /条\s*$/.test((b.innerText || '').replace(/\s+/g, ' ')));
"""


def functional_checks(d, shots_dir):
    out = {}
    out['group_view'] = d.execute_script(TABLE_STATS_JS)

    # 折叠 / 还原第一组（组头按钮带「N 条」计数）
    out['collapse'] = d.execute_script("""
      const t = window.__evalTable; if (!t) return {ok:false};
      const heads = [...t.querySelectorAll('tbody button[aria-expanded]')]
        .filter(b => /条\\s*$/.test((b.innerText || '').replace(/\\s+/g, ' ')));
      if (!heads.length) return {ok:false, why:'no group head'};
      window.__gh = heads[0];
      window.__before = t.querySelectorAll('tbody tr').length;
      window.__ghName = (heads[0].innerText || '').trim().slice(0, 20);
      heads[0].click();
      return {ok:true};
    """)
    time.sleep(0.8)
    out['collapse']['after'] = d.execute_script("return window.__evalTable.querySelectorAll('tbody tr').length")
    out['collapse']['before'] = d.execute_script("return window.__before")
    out['collapse']['head_name'] = d.execute_script("return window.__ghName")
    d.execute_script("window.__gh.click()")
    time.sleep(0.8)
    out['collapse']['restored'] = d.execute_script("return window.__evalTable.querySelectorAll('tbody tr').length")

    # 搜索（分组视图）
    out['search'] = d.execute_script("""
      const root = window.__evalRoot;
      const inp = root.querySelector('input[aria-label="搜索映射"]');
      if (!inp) return {ok:false};
      const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
      s.call(inp, '时延');
      inp.dispatchEvent(new Event('input', {bubbles:true}));
      return {ok:true};
    """)
    time.sleep(1.2)
    out['search_rows'] = d.execute_script(TABLE_STATS_JS)
    d.execute_script("""
      const root = window.__evalRoot;
      const inp = root.querySelector('input[aria-label="搜索映射"]');
      const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
      s.call(inp, ''); inp.dispatchEvent(new Event('input',{bubbles:true}));
    """)
    time.sleep(1.0)

    # 平铺视图分页
    out['flat'] = d.execute_script("""
      const root = window.__evalRoot;
      const b = [...root.querySelectorAll('button')].find(x => (x.innerText || '').trim() === '平铺视图');
      if (!b) return {ok:false};
      b.click(); return {ok:true};
    """)
    time.sleep(1.2)
    out['flat_page1'] = d.execute_script(TABLE_STATS_JS)
    out['flat_total'] = d.execute_script("return (window.__evalRoot.innerText.match(/共\\s*\\d+\\s*条/) || [''])[0];")
    out['flat_page2'] = d.execute_script("""
      const root = window.__evalRoot;
      const btn = [...root.querySelectorAll('button')].find(b => (b.getAttribute('aria-label')||'').includes('下一页') || (b.innerText||'').trim() === '下一页');
      if (!btn) return {ok:false, why:'no next'};
      btn.click(); return {ok:true};
    """)
    time.sleep(1.0)
    out['flat_page2_rows'] = d.execute_script(TABLE_STATS_JS)

    # 回分组视图
    d.execute_script("""
      const root = window.__evalRoot;
      const b = [...root.querySelectorAll('button')].find(x => (x.innerText || '').trim() === '评估维度视图');
      if (b) b.click();
    """)
    time.sleep(1.2)

    # containment 生效 + 横向滚动仍可用
    out['contain'] = d.execute_script("""
      const t = window.__evalTable; if (!t) return null;
      const cs = getComputedStyle(t);
      const wrap = t.parentElement;
      const before = wrap.scrollLeft;
      wrap.scrollLeft = 120;
      const after = wrap.scrollLeft;
      wrap.scrollLeft = before;
      return {contain: cs.contain, hscroll_ok: after > 0, scrollWidth: wrap.scrollWidth, clientWidth: wrap.clientWidth};
    """)

    # 浅色截图（下拉打开前）
    d.execute_script("const t = window.__evalTable; if (t) t.scrollIntoView({block:'start'});")
    time.sleep(0.6)
    d.save_screenshot(os.path.join(shots_dir, 'sheet-light.png'))

    # 行内下拉（门户不被 contain 裁切）
    out['select'] = d.execute_script("""
      const t = window.__evalTable; if (!t) return {ok:false};
      const trig = t.querySelector('tbody [data-slot="select-trigger"]');
      if (!trig) return {ok:false, why:'no trigger'};
      trig.scrollIntoView({block:'center'});
      trig.click();
      return {ok:true};
    """)
    time.sleep(1.0)
    out['select_popup'] = d.execute_script("""
      const lb = document.querySelector('[role=listbox]');
      if (!lb) return {ok:false};
      const r = lb.getBoundingClientRect();
      const visible = r.width > 0 && r.height > 0 && r.top < innerHeight && r.bottom > 0;
      return {ok:true, w: Math.round(r.width), h: Math.round(r.height),
              options: lb.querySelectorAll('[role=option]').length, visible,
              clippedByContain: getComputedStyle(lb).position !== 'fixed' && !!lb.closest('.alg-table-contain')};
    """)
    d.save_screenshot(os.path.join(shots_dir, 'select-open-light.png'))
    from selenium.webdriver.common.keys import Keys
    body = d.find_element(By.TAG_NAME, 'body')
    body.send_keys(Keys.ESCAPE)
    time.sleep(0.6)
    out['sheet_still_open_after_esc'] = d.execute_script(
        "return !!document.querySelector('#algorithm-mutate-form')")
    d.save_screenshot(os.path.join(shots_dir, 'sheet-light-after-esc.png'))
    return out


def dark_screenshot(d, base, shots_dir):
    d.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark');")
    d.get('about:blank')
    time.sleep(0.4)
    open_edit_sheet(d, base)
    is_dark = d.execute_script("return document.documentElement.className.includes('dark')")
    time.sleep(0.6)
    d.execute_script("const t=window.__evalTable; if(t) t.scrollIntoView({block:'start'});")
    time.sleep(0.6)
    p = os.path.join(shots_dir, 'sheet-dark.png')
    d.save_screenshot(p)
    d.execute_script("localStorage.setItem('iatp:theme:v1:mode','light');")
    return is_dark


def network_entries(d):
    urls = []
    try:
        for e in d.get_log('performance'):
            m = json.loads(e['message'])['message']
            if m.get('method') == 'Network.responseReceived':
                u = m['params']['response']['url']
                if '/api/' in u:
                    urls.append({'url': u.split('?')[0], 'status': m['params']['response']['status']})
    except Exception as ex:
        return {'err': str(ex)}
    uniq = []
    seen = set()
    for u in urls:
        k = (u['url'], u['status'])
        if k not in seen:
            seen.add(k)
            uniq.append(u)
    return uniq


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', required=True)
    ap.add_argument('--side', required=True)
    ap.add_argument('--rounds', type=int, default=3)
    ap.add_argument('--steps', type=int, default=16)
    ap.add_argument('--delta', type=int, default=320)
    ap.add_argument('--mode', choices=['edit', 'detail', 'both'], default='edit')
    ap.add_argument('--skip-perf', action='store_true')
    ap.add_argument('--interval', type=float, default=0.03)
    args = ap.parse_args()

    art = os.path.join(HERE, 'artifacts', 'int2121', args.side)
    shots = os.path.join(art, 'shots')
    os.makedirs(shots, exist_ok=True)
    result = {'base': args.base, 'side': args.side, 'mode': args.mode}

    d = make_driver(log_perf=True)
    try:
        login(d, args.base)
        if args.mode in ('edit', 'both'):
            open_edit_sheet(d, args.base)
            result['geo'] = d.execute_script(SCROLL_TO_TABLE_JS)
            if not args.skip_perf:
                r1 = []
                for i in range(args.rounds):
                    s, geo, lterr = measure_round(d, args.steps, args.delta, 1, args.interval)
                    r1.append(s)
                result['perf_1x'] = r1
                r4 = []
                for i in range(args.rounds):
                    s, geo, lterr = measure_round(d, 8, args.delta, 4, args.interval)
                    r4.append(s)
                result['perf_4x'] = r4
            result['functional'] = functional_checks(d, shots)
            result['dark_ok'] = dark_screenshot(d, args.base, shots)
            result['network'] = network_entries(d)
            dump(result, art)
        if args.mode in ('detail', 'both'):
            d.execute_script("localStorage.setItem('iatp:theme:v1:mode','light');")
            d.get(args.base + '/AlgorithmConfig')
            WebDriverWait(d, 45).until(lambda x: x.find_elements(By.XPATH, "//tr[contains(., '%s')]" % ALGO))
            time.sleep(1.5)
            d.execute_script("""
              const row = [...document.querySelectorAll('tr')].find(r => r.innerText.includes(arguments[0]));
              row.click();
            """, ALGO)
            WebDriverWait(d, 30).until(lambda x: x.find_elements(By.CSS_SELECTOR, '[role=dialog]'))
            time.sleep(2.0)
            prep = d.execute_script(DETAIL_PREPARE_JS)
            time.sleep(2.0)
            result['detail_prep'] = prep
            result['detail_geo'] = d.execute_script(DETAIL_SCROLL_JS)
            if not args.skip_perf:
                rounds = []
                for i in range(args.rounds):
                    s = detail_round(d, args.steps, args.delta, 1, args.interval)
                    rounds.append(s)
                result['detail_perf_1x'] = rounds
                d.save_screenshot(os.path.join(shots, 'detail-light.png'))
    finally:
        d.quit()

    dump(result, art)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def dump(result, art):
    with open(os.path.join(art, 'result.json'), 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


def detail_round(d, steps, delta, throttle=1, interval=0.03):
    d.execute_cdp_cmd('Emulation.setCPUThrottlingRate', {'rate': throttle})
    geo = d.execute_script(DETAIL_SCROLL_JS)
    d.execute_script("""
      const dlg = document.querySelector('[role=dialog]');
      if (dlg) dlg.scrollTop = 0;
    """)
    time.sleep(0.8)
    d.execute_script(START_JS)
    time.sleep(0.3)
    for _ in range(steps):
        d.execute_cdp_cmd('Input.dispatchMouseEvent', {
            'type': 'mouseWheel', 'x': geo['x'], 'y': geo['y'],
            'deltaX': 0, 'deltaY': delta, 'pointerType': 'mouse',
        })
        time.sleep(interval)
    d.execute_script('window.__rec.scrollEnd = performance.now();')
    time.sleep(0.8)
    data = d.execute_script(STOP_JS)
    d.execute_cdp_cmd('Emulation.setCPUThrottlingRate', {'rate': 1})
    return stats(data['frames'], data['longtasks'])


if __name__ == '__main__':
    main()
