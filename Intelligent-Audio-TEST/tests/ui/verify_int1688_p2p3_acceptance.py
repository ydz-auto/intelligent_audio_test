# -*- coding: utf-8 -*-
"""INT-1688 P2/P3 返工复测（测试工程师独立实测）。

被测：交付 sha c95701f62（P2/P3 结果音频口径 + 轮次 Tab 复位），构建自该提交的 frontend-react，
旁路容器 http://127.0.0.1:15288（nginx 反代 api_gateway），后端真实库栈 http://127.0.0.1:15000。

期望全部由接口原文独立推导（/detail + /results），不引用交付脚本断言：
- 轮次 Tab = 维度轮次 ∪ audio_file 轮次 ∪ audio_list 轮次；「整体」仅当整体维度有非空值；
- 「结果音频」块（result_audios）不随 Tab 过滤、按设备分组（本卡真实库为空 → 块不渲染，
  另用页内 fetch 注入 result_audios 做同口径运行时验证）；
- 「执行结果音频」块（algorithm_results 的 audio_file）按当前 Tab 过滤，轮次只在 chip 出现一次；
- 换用例复位到第一个有数据的 Tab。
"""
import json
import os
import sys
import time
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15288').rstrip('/')
API = os.environ.get('BACKEND_BASE', 'http://127.0.0.1:15000').rstrip('/')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.environ.get(
    'ART_DIR',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts'),
)
TASK_ID = 402
SINGLE_CASE = '7bac162b-275d-4567-b924-954736dc3ce9'
MULTI_CASE = 'd8bdd5a6-666d-41ab-a366-6b9f3b27e564'
SINGLE_FRAG = 'JG0006_单轮接管-正常接管'
MULTI_FRAG = 'DD139_多次打断'
EMPTY_TASK_ID = int(os.environ.get('EMPTY_TASK_ID', '399'))
DARK_KEY = 'iatp:theme:v1:mode'
STEPS = os.environ.get('STEPS', 'all')  # all | A（单轮 + 注入 + 试听） | B（多轮 + 复位 + 空态）

RESULT = []
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass


def check(name, ok, detail=''):
    RESULT.append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:2000]})
    print(('[PASS] ' if ok else '[FAIL] ') + name + (' | ' + str(detail)[:400] if detail else ''))
    return ok


def api_get(path):
    with urllib.request.urlopen(API + path, timeout=120) as r:
        return json.loads(r.read().decode('utf-8'))


def jsnum(v):
    if v is None:
        return '—'
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v)


# ---------------- 期望推导（纯接口原文） ----------------

def detail_and_results(task_id, case_id):
    d = api_get('/api/v1/tasks/%d/cases/%s/detail' % (task_id, case_id))['data']
    r = api_get('/api/v1/tasks/%d/cases/%s/results' % (task_id, case_id))['data']['results']
    return d, r


def strip_suffix(param_code):
    pc = param_code or ''
    base = pc
    for suf_marker in ('@round:', '@overall'):
        idx = base.lower().rfind(suf_marker)
        if idx >= 0:
            base = base[:idx]
            break
    return base.strip()


def audio_fields(d):
    """algorithm_results 的 audio_file 项 → {label, round, overall, dimension}"""
    out = []
    for r in (d.get('algorithm_results') or []):
        if r.get('param_type') != 'audio_file' or not r.get('value'):
            continue
        pc = r.get('param_code') or ''
        overall = pc.lower().endswith('@overall')
        rnd = None
        if '@round:' in pc.lower():
            try:
                rnd = int(pc.lower().rsplit('@round:', 1)[1])
            except ValueError:
                rnd = None
        elif not overall:
            rnd = r.get('round_number')
        out.append({
            'label': strip_suffix(pc) or r.get('label') or pc,
            'round': rnd,
            'overall': overall,
            'dimension': r.get('dimension_name'),
            'param_code': pc,
        })
    return out


def visible_fields(fields, tab):
    if tab is None or tab['kind'] == 'all':
        return list(fields)
    vis = []
    for f in fields:
        if tab['kind'] == 'overall':
            if f['dimension'] is None or f['overall']:
                vis.append(f)
        else:
            if f['overall']:
                continue
            if f['round'] is None or f['round'] == tab['round']:
                vis.append(f)
    return vis


def expectations(task_id, case_id):
    d, results = detail_and_results(task_id, case_id)
    devices = list(d.get('devices') or [])
    configs = [c.get('name') for c in (d.get('metric_configs') or [])]

    points = {}
    for row in results:
        dev = row.get('device_name')
        if not dev:
            continue
        lst = points.setdefault(dev, [])
        for dim in (row.get('dimensions') or []):
            rn = dim.get('round_number')
            lst.append({
                'dim': dim.get('name'),
                'round': None if rn is None else rn + 1,
                'value': jsnum(dim.get('value')),
            })

    fields = audio_fields(d)
    result_audios = [
        {'name': a.get('filename') or a.get('param_code') or '音频%d' % (i + 1), 'device': dev}
        for dev, lst in (d.get('result_audios') or {}).items()
        for i, a in enumerate(lst or [])
    ]
    refs = [{
        'name': a.get('filename') or ('音频 %s' % a.get('id')),
        'round': a.get('roundNumber') if a.get('roundNumber') is not None else a.get('round_number'),
    } for a in (d.get('audio_list') or [])]

    allp = [p for lst in points.values() for p in lst]
    has_round_tag = any(p['round'] is not None for p in allp)
    rounds = sorted(
        {p['round'] for p in allp if p['round'] is not None}
        | {f['round'] for f in fields if f['round'] is not None}
        | {a['round'] for a in refs if a['round'] is not None}
    )
    overall_points = [p for p in allp if p['round'] is None]
    overall_has_value = any(p['value'] != '—' for p in overall_points)

    tabs = []
    if not has_round_tag:
        tabs.append({'label': '指标', 'round': None, 'kind': 'all'})
    else:
        for r in rounds:
            tabs.append({'label': '第%d轮' % r, 'round': r, 'kind': 'round'})
        if overall_has_value:
            tabs.append({'label': '整体', 'round': None, 'kind': 'overall'})

    def accept(kind, rnd):
        if kind == 'round':
            return lambda p: p['round'] == rnd
        if kind == 'overall':
            return lambda p: p['round'] is None
        return lambda p: True

    present = []
    for dev in devices:
        for p in points.get(dev, []):
            if p['dim'] and p['dim'] not in present:
                present.append(p['dim'])
    order = [n for n in configs if n in present] + [n for n in present if n not in configs]

    for tab in tabs:
        acc = accept(tab['kind'], tab['round'])
        rows = []
        for dim in order:
            if not any(acc(p) for dev in devices for p in points.get(dev, []) if p['dim'] == dim):
                continue
            values = []
            for dev in devices:
                hit = next((p for p in points.get(dev, []) if p['dim'] == dim and acc(p)), None)
                values.append(hit['value'] if hit else '—')
            rows.append({'dim': dim, 'values': values})
        tab['rows'] = rows
        tab['audio_fields'] = [f['label'] for f in visible_fields(fields, tab)]
        if tab['kind'] == 'round':
            tab['refs'] = [a['name'] for a in refs
                           if a['round'] is None or a['round'] == tab['round']]
        else:
            tab['refs'] = [a['name'] for a in refs]

    # 第一个有数据的 Tab（P3 复位口径）
    first_with_data = None
    for t in tabs:
        if any(v != '—' for r in t['rows'] for v in r['values']):
            first_with_data = t['label']
            break
    if first_with_data is None and tabs:
        first_with_data = tabs[0]['label']

    return {
        'devices': devices,
        'tabs': tabs,
        'metric_configs': configs,
        'result_audios': result_audios,
        'audio_fields_all': fields,
        'first_tab_with_data': first_with_data,
        'raw_detail': d,
    }


# ---------------- DOM 采集 ----------------

COLLECT_JS = r"""
const dlg = document.querySelector('[data-slot="case-detail-dialog"]');
if (!dlg) return null;
const tablist = dlg.querySelector('[role="tablist"]');
const tabs = tablist ? [...tablist.querySelectorAll('[role="tab"]')].map(t => ({
  label: (t.textContent||'').trim(),
  selected: t.getAttribute('aria-selected') === 'true',
})) : [];
const table = dlg.querySelector('table');
const heads = table ? [...table.querySelectorAll('thead th')].map(t => (t.textContent||'').trim()) : [];
const rows = table ? [...table.querySelectorAll('tbody tr')].map(tr =>
  [...tr.querySelectorAll('td')].map(td => (td.textContent||'').trim())) : [];
function sec(label){
  const p = [...dlg.querySelectorAll('p')].find(x => (x.textContent||'').trim() === label);
  if (!p) return null;
  const root = p.parentElement;
  const rows = [...root.querySelectorAll('div.rounded-lg.border')].map(d => {
    const spans = [...d.querySelectorAll('span')].map(s => ({
      t: (s.textContent||'').trim(),
      c: typeof s.className === 'string' ? s.className : '',
    }));
    return {
      text: (d.textContent||'').replace(/\s+/g, ' ').trim(),
      label: (spans.find(s => s.c.includes('font-mono')) || {}).t || '',
      chips: spans.filter(s => s.c.includes('text-[10px]')).map(s => s.t),
      hasBtn: !!d.querySelector('button'),
    };
  });
  const groups = [...root.querySelectorAll('p')]
    .filter(x => x !== p).map(x => (x.textContent||'').trim());
  return {rows, groups, text: (root.textContent||'').replace(/\s+/g, ' ')};
}
const header = dlg.querySelector('[data-slot="dialog-header"]') || dlg;
return {
  tabs, heads, rows,
  resultAudios: sec('结果音频'),
  audioFields: sec('执行结果音频'),
  refAudios: sec('参考音频（用例输入）'),
  headerText: (header.textContent||''),
  dialogText: (dlg.textContent||''),
};
"""


# ---------------- Selenium ----------------

def chrome_major():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            return int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        return 0


def build_driver():
    opts = Options()
    opts.binary_location = CHROME_BINARY
    opts.add_argument('--headless=new')
    opts.add_argument('--window-size=1920,1200')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--autoplay-policy=no-user-gesture-required')
    opts.add_argument('--lang=zh-CN')
    opts.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    major = chrome_major()
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
                    pass
        same = [p for v, p in cands if v and v[0] == major]
        if same:
            exe = max(same)
    srv = Service(executable_path=exe) if exe else Service()
    drv = webdriver.Chrome(options=opts, service=srv)
    drv.set_page_load_timeout(300)
    drv.set_script_timeout(300)
    return drv


def goto(drv, path, wait=4.0):
    drv.get(BASE + path)
    WebDriverWait(drv, 240).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(wait)


def shot(drv, name):
    os.makedirs(ART, exist_ok=True)
    p = os.path.join(ART, name + '.png')
    drv.save_screenshot(p)
    print('shot:', p)
    return p


def body_text(drv):
    return drv.execute_script('return document.body.textContent || ""') or ''


def wait_text(drv, text, timeout=240):
    WebDriverWait(drv, timeout).until(lambda d: text in body_text(d))


def js_click(drv, el, wait=0.8):
    drv.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", el)
    time.sleep(wait)


def close_dialog(drv):
    try:
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    except Exception:
        pass
    time.sleep(1.5)


def wait_list(drv):
    wait_text(drv, '关联用例')
    WebDriverWait(drv, 240).until(
        lambda d: len(d.find_elements(By.XPATH, "//button[starts-with(@title,'查看用例详情：')]")) > 0)


def search(drv, frag):
    box = WebDriverWait(drv, 180).until(
        lambda d: d.find_element(By.XPATH, "//input[@placeholder='搜索用例名称或 ID…']"))
    js_click(drv, box, 0.4)
    box.send_keys(Keys.CONTROL, 'a')
    box.send_keys(Keys.BACKSPACE)
    time.sleep(0.6)
    if frag:
        box.send_keys(frag)
    time.sleep(3.5)


def open_first_case(drv):
    btn = WebDriverWait(drv, 180).until(
        lambda d: d.find_elements(By.XPATH, "//button[starts-with(@title,'查看用例详情：')]")[0])
    js_click(drv, btn, 1.2)
    WebDriverWait(drv, 180).until(
        lambda d: d.find_element(By.CSS_SELECTOR, '[data-slot="case-detail-dialog"]'))
    wait_text(drv, '执行结果与指标')
    time.sleep(2.0)


INJECT_JS = r"""
const cid = arguments[0];
const payload = arguments[1];
return (function(){
  if (window.__int1688patched) return 'already';
  window.__int1688patched = true;
  const orig = window.fetch.bind(window);
  window.fetch = async function(input, init){
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    const res = await orig(input, init);
    if (url.indexOf('/cases/' + cid + '/detail') >= 0) {
      try {
        const j = await res.clone().json();
        j.data.result_audios = payload;
        return new Response(JSON.stringify(j), {
          status: res.status,
          headers: {'Content-Type': 'application/json'}
        });
      } catch (e) { return res; }
    }
    return res;
  };
  return 'patched';
})();
"""


def read_perf(drv):
    out = []
    for entry in drv.get_log('performance'):
        try:
            msg = json.loads(entry['message'])['message']
        except Exception:
            continue
        if msg.get('method') == 'Network.responseReceived':
            p = msg['params']
            out.append((p['response']['url'], p['response']['status'],
                        p['response'].get('mimeType', '')))
    return out


def statuses(netlog, needle):
    return sorted({st for url, st, _ in netlog if needle in url})


def click_tab(drv, label):
    tab = WebDriverWait(drv, 90).until(
        lambda d: d.find_element(
            By.XPATH,
            "//*[@data-slot='case-detail-dialog']//*[@role='tab'][normalize-space(.)='%s']" % label))
    js_click(drv, tab, 1.4)


def verify_case(drv, exp, tag, shot_prefix=None):
    data = drv.execute_script(COLLECT_JS)
    if not data:
        check('[%s] 弹窗 DOM 可取' % tag, False, 'collect null')
        return None
    dtext = data['dialogText']

    for dev in exp['devices']:
        check('[%s] 头部设备徽章含 %s' % (tag, dev), dev in data['headerText'], data['headerText'][:120])

    want_tabs = [t['label'] for t in exp['tabs']]
    got_tabs = [t['label'] for t in data['tabs']]
    if len(want_tabs) > 1:
        check('[%s] 轮次 Tab 列表 = 接口推导 %s' % (tag, want_tabs), got_tabs == want_tabs,
              {'want': want_tabs, 'got': got_tabs})
        default = exp['first_tab_with_data']
        sel = [t['label'] for t in data['tabs'] if t['selected']]
        check('[%s] 默认选中第一个有数据的 Tab「%s」' % (tag, default), sel == [default], sel)
    else:
        check('[%s] 单 Tab 不渲染 Tab 栏' % tag, not data['tabs'], got_tabs)

    check('[%s] 表头首列 = 指标' % tag, data['heads'][:1] == ['指标'], data['heads'])
    check('[%s] 表头列数 = 1 + %d 设备' % (tag, len(exp['devices'])),
          len(data['heads']) == 1 + len(exp['devices']), data['heads'])
    check('[%s] 界面不出现内部键 @round / @overall' % tag,
          '@round' not in dtext and '@overall' not in dtext, '')

    # 结果音频块：接口 result_audios 为空 → 整块不渲染
    if not exp['result_audios']:
        check('[%s] 接口 result_audios 为空 → 不渲染「结果音频」块' % tag,
              data['resultAudios'] is None, (data['resultAudios'] or {}).get('text', '')[:120])
    else:
        names = [a['name'] for a in exp['result_audios']]
        got = [r['label'] for r in (data['resultAudios'] or {}).get('rows', [])]
        check('[%s] 结果音频块=接口 result_audios（%d 条）' % (tag, len(names)),
              got == names, {'want': names, 'got': got})

    for i, tab in enumerate(exp['tabs']):
        label = tab['label']
        if i > 0 or exp['first_tab_with_data'] != label:
            click_tab(drv, label)
        data = drv.execute_script(COLLECT_JS)
        sel = [t['label'] for t in data['tabs'] if t['selected']]
        check('[%s]「%s」Tab 选中' % (tag, label), sel == [label], sel)
        dtext = data['dialogText']

        want_dims = [r['dim'] for r in tab['rows']]
        got_dims = [r[0] for r in data['rows'] if r and r[0] != '暂无指标数据']
        if want_dims:
            check('[%s]「%s」指标行 %d 个与接口一致' % (tag, label, len(want_dims)),
                  got_dims == want_dims, {'want': want_dims, 'got': got_dims})
            got_cells = [r[1:] for r in data['rows'] if r and r[0] != '暂无指标数据']
            want_cells = [r['values'] for r in tab['rows']]
            check('[%s]「%s」逐值 = /results 原文' % (tag, label), got_cells == want_cells,
                  {'got': got_cells[:5], 'want': want_cells[:5]})
        else:
            check('[%s]「%s」无指标 → 暂无指标数据' % (tag, label),
                  any('暂无指标数据' in (r[0] if r else '') for r in data['rows']), data['rows'])

        # 执行结果音频：按 Tab 过滤
        want_labels = tab['audio_fields']
        got_labels = [r['label'] for r in (data['audioFields'] or {}).get('rows', [])]
        check('[%s]「%s」执行结果音频 %d 条 = 接口推导' % (tag, label, len(want_labels)),
              got_labels == want_labels, {'want': want_labels, 'got': got_labels})
        for r in (data['audioFields'] or {}).get('rows', []):
            check('[%s]「%s」行 %s label 不带轮次文案（不重复）' % (tag, label, r['label']),
                  '第' not in r['label'] and '（' not in r['label'] and '@' not in r['label'],
                  r['label'])
            check('[%s]「%s」行 %s 轮次 chip 至多一个' % (tag, label, r['label']),
                  len(r['chips']) <= 1, r['chips'])
            check('[%s]「%s」行 %s 带试听按钮' % (tag, label, r['label']), r['hasBtn'], r['text'][:80])

        # 参考音频（现状口径：轮次 Tab 过滤）
        got_refs = [r['label'] for r in (data['refAudios'] or {}).get('rows', [])]
        check('[%s]「%s」参考音频 %d 条（现状口径）' % (tag, label, len(tab['refs'])),
              got_refs == tab['refs'], {'want': tab['refs'], 'got': got_refs})
        if shot_prefix:
            shot(drv, '%s_%s' % (shot_prefix, label))
    if exp['tabs']:
        click_tab(drv, exp['tabs'][0]['label'])
    return data


def verify_injection(drv, exp):
    """P2 运行时：注入 result_audios（跨两轮）→ 任何 Tab 都显示全部、按设备分组。"""
    inj = {
        '9-pura90小艺-1.0.0': [
            {'filename': 'INJECT_R1.wav'},
            {'filename': 'INJECT_R2.wav'},
        ]
    }
    goto(drv, '/tasks/%d' % TASK_ID, wait=5)
    wait_list(drv)
    res = drv.execute_script(INJECT_JS, SINGLE_CASE, inj)
    check('[inject] fetch 注入 result_audios 已挂载', res == 'patched', res)
    search(drv, SINGLE_FRAG)
    open_first_case(drv)
    texts = {}
    for label in [t['label'] for t in exp['tabs']]:
        click_tab(drv, label)
        data = drv.execute_script(COLLECT_JS)
        sec = data.get('resultAudios')
        got = [r['label'] for r in (sec or {}).get('rows', [])]
        check('[inject]「%s」结果音频显示全部 2 条（不随 Tab 过滤）' % label,
              got == ['INJECT_R1.wav', 'INJECT_R2.wav'], got)
        groups = (sec or {}).get('groups') or []
        check('[inject]「%s」按设备分组，组标题还原为 %s' % (label, exp['devices'][0]),
              exp['devices'][0] in groups, groups)
        texts[label] = (sec or {}).get('text', '')
        shot(drv, 'A_inject_%s' % label)
    return texts


def verify_audio_play(drv):
    """执行结果音频试听 → 真实 http 音频地址。"""
    try:
        row = drv.find_element(
            By.XPATH,
            "//*[@data-slot='case-detail-dialog']//div[contains(@class,'rounded-lg') and "
            "contains(.,'user_wav')]//button[normalize-space(.)='试听']")
        js_click(drv, row, 2.0)
        WebDriverWait(drv, 90).until(lambda d: len(d.find_elements(By.TAG_NAME, 'audio')) > 0)
        info = None
        src = ''
        for _ in range(40):
            info = drv.execute_script(
                "const a=document.querySelector('audio');"
                "return a ? {src: a.currentSrc||a.src||'', rs: a.readyState,"
                " dur: a.duration, err: a.error? a.error.code : null} : null")
            if info and info['src']:
                src = info['src']
                if info['rs'] and info['rs'] >= 1:
                    break
            time.sleep(0.5)
        check('[play] 试听得到 http 音频地址', bool(src) and src.startswith('http'), src[:180])
        check('[play] 无「地址获取失败」', '音频播放地址获取失败' not in body_text(drv), '')
        print('   audio:', info)
        shot(drv, 'A_single_light_play')
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(1.2)
        return src
    except Exception as exc:  # noqa: BLE001
        check('[play] 执行结果音频试听', False, repr(exc)[:300])
        return ''


def verify_reset(drv, multi, single):
    """P3：停在多轮第7轮 → 同页换单轮用例 → 复位到第一个有数据 Tab。"""
    goto(drv, '/tasks/%d' % TASK_ID, wait=5)
    wait_list(drv)
    search(drv, MULTI_FRAG)
    open_first_case(drv)
    last = multi['tabs'][-2]['label'] if len(multi['tabs']) > 1 else multi['tabs'][0]['label']
    click_tab(drv, last)
    d0 = drv.execute_script(COLLECT_JS)
    check('[reset] 多轮用例停在「%s」' % last,
          [t['label'] for t in d0['tabs'] if t['selected']] == [last],
          [t['label'] for t in d0['tabs'] if t['selected']])
    close_dialog(drv)
    search(drv, SINGLE_FRAG)
    open_first_case(drv)
    d1 = drv.execute_script(COLLECT_JS)
    sel = [t['label'] for t in d1['tabs'] if t['selected']]
    want = single['first_tab_with_data']
    check('[reset] 同页换用例后复位到「%s」' % want, sel == [want], sel)
    shot(drv, 'A_reset_single')
    close_dialog(drv)


def verify_empty(drv):
    goto(drv, '/tasks/%d' % EMPTY_TASK_ID, wait=5)
    wait_list(drv)
    open_first_case(drv)
    data = drv.execute_script(COLLECT_JS) or {}
    dtext = data.get('dialogText', '')
    check('[empty] 显示「暂无执行结果」', '暂无执行结果' in dtext, dtext[:200])
    check('[empty] 不渲染指标表', not data.get('heads'), data.get('heads'))
    check('[empty] 不渲染轮次 Tab 栏', not data.get('tabs'), data.get('tabs'))
    check('[empty] 无结果音频块', data.get('resultAudios') is None
          and data.get('audioFields') is None, '')
    shot(drv, 'A_empty_task%d' % EMPTY_TASK_ID)


def main():
    os.makedirs(ART, exist_ok=True)
    single = expectations(TASK_ID, SINGLE_CASE)
    multi = expectations(TASK_ID, MULTI_CASE)
    dump = {
        'single': {
            'devices': single['devices'],
            'tabs': [{'label': t['label'], 'kind': t['kind'], 'rows': t['rows'],
                      'audio_fields': t['audio_fields'], 'refs': t['refs']} for t in single['tabs']],
            'first_tab_with_data': single['first_tab_with_data'],
            'result_audios_from_api': single['result_audios'],
        },
        'multi': {
            'devices': multi['devices'],
            'tabs': [{'label': t['label'], 'kind': t['kind'], 'row_count': len(t['rows']),
                      'audio_fields_count': len(t['audio_fields'])} for t in multi['tabs']],
            'first_tab_with_data': multi['first_tab_with_data'],
        },
    }
    with open(os.path.join(ART, 'expected.json'), 'w', encoding='utf-8') as f:
        json.dump(dump, f, ensure_ascii=False, indent=1)
    print('[EXPECT single] tabs=%s' % [t['label'] for t in single['tabs']])
    print('[EXPECT multi] tabs=%s first_data=%s'
          % ([t['label'] for t in multi['tabs']], multi['first_tab_with_data']))

    drv = build_driver()
    ev = {'base': BASE, 'api': API, 'steps': STEPS}
    do_a = STEPS in ('all', 'A')
    do_b1 = STEPS in ('all', 'B', 'B1')
    do_b2 = STEPS in ('all', 'B', 'B2')
    do_b3 = STEPS in ('all', 'B', 'B3')
    try:
        if do_a:
            # ---------- 单轮 · 浅色 ----------
            goto(drv, '/tasks/%d' % TASK_ID, wait=5)
            wait_list(drv)
            search(drv, SINGLE_FRAG)
            open_first_case(drv)
            net = read_perf(drv)
            ev['net'] = {
                'detail': statuses(net, '/cases/%s/detail' % SINGLE_CASE),
                'results': statuses(net, '/cases/%s/results' % SINGLE_CASE),
            }
            check('Network：GET .../detail → 200', ev['net']['detail'] == [200], ev['net']['detail'])
            check('Network：GET .../results → 200', ev['net']['results'] == [200], ev['net']['results'])
            verify_case(drv, single, 'single-light', 'A_single_light')
            ev['play'] = verify_audio_play(drv)
            close_dialog(drv)

            # ---------- 单轮 · 深色 ----------
            drv.execute_script("localStorage.setItem(arguments[0], 'dark')", DARK_KEY)
            goto(drv, '/tasks/%d' % TASK_ID, wait=5)
            wait_list(drv)
            search(drv, SINGLE_FRAG)
            open_first_case(drv)
            cls = drv.execute_script('return document.documentElement.className')
            check('深色主题生效', 'dark' in (cls or ''), cls)
            verify_case(drv, single, 'single-dark', 'A_single_dark')
            close_dialog(drv)
            drv.execute_script("localStorage.setItem(arguments[0], 'light')", DARK_KEY)

            # ---------- P2 运行时注入 ----------
            ev['inject'] = verify_injection(drv, single)
            close_dialog(drv)

        if do_b1:
            # ---------- 7 轮 · 浅色 ----------
            goto(drv, '/tasks/%d' % TASK_ID, wait=5)
            wait_list(drv)
            search(drv, MULTI_FRAG)
            open_first_case(drv)
            net = read_perf(drv)
            ev['net_multi'] = {
                'detail': statuses(net, '/cases/%s/detail' % MULTI_CASE),
                'results': statuses(net, '/cases/%s/results' % MULTI_CASE),
            }
            check('Network：多轮 detail → 200', ev['net_multi']['detail'] == [200], ev['net_multi']['detail'])
            check('Network：多轮 results → 200', ev['net_multi']['results'] == [200], ev['net_multi']['results'])
            verify_case(drv, multi, 'multi-light', 'A_multi_light')
            close_dialog(drv)

        if do_b2:
            # ---------- 7 轮 · 深色 ----------
            goto(drv, '/tasks/%d' % TASK_ID, wait=3)
            drv.execute_script("localStorage.setItem(arguments[0], 'dark')", DARK_KEY)
            goto(drv, '/tasks/%d' % TASK_ID, wait=5)
            wait_list(drv)
            search(drv, MULTI_FRAG)
            open_first_case(drv)
            cls = drv.execute_script('return document.documentElement.className')
            check('[multi-dark] 深色主题生效', 'dark' in (cls or ''), cls)
            verify_case(drv, multi, 'multi-dark', 'A_multi_dark')
            close_dialog(drv)
            drv.execute_script("localStorage.setItem(arguments[0], 'light')", DARK_KEY)

        if do_b3:
            # ---------- P3 复位 ----------
            verify_reset(drv, multi, single)

            # ---------- 空态 ----------
            verify_empty(drv)

        # ---------- 控制台 ----------
        severe = [e for e in drv.get_log('browser')
                  if e.get('level') == 'SEVERE' and 'favicon' not in e.get('message', '')]
        ev['console_severe'] = [s.get('message', '')[:200] for s in severe[-8:]]
        check('浏览器控制台无 SEVERE', not severe, ev['console_severe'])
    finally:
        try:
            drv.quit()
        except Exception:
            pass

    failed = [r for r in RESULT if not r['ok']]
    ev['checks'] = RESULT
    ev['failed'] = len(failed)
    with open(os.path.join(ART, 'evidence_%s.json' % STEPS), 'w', encoding='utf-8') as f:
        json.dump(ev, f, ensure_ascii=False, indent=1, default=str)
    print('\n==== %d checks, %d failed ====' % (len(RESULT), len(failed)))
    for r in failed:
        print('[FAIL]', r['name'], '|', r['detail'][:300])
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
