# -*- coding: utf-8 -*-
"""INT-1688 返工复测（测试工程师独立实测）：case-detail 弹窗的轮次 Tab 口径。

被测前端：旁路容器 http://127.0.0.1:15288（交付 7dd09598c 构建 dist + 15173 同款 nginx，
反代 api_gateway），后端真实库栈 http://127.0.0.1:15000（database=intelligent_audio_test）。

期望值全部从接口原文（/detail + /results）独立推导，不引用交付脚本的断言：
- Tab 列表 = 维度 round_number(+1) ∪ 音频轮次，整体 Tab 仅在整体维度有非空值时出现；
- 表体行 = 该 Tab 有值的维度（顺序照 metric_configs），列 = 设备；
- 音频随 Tab 按轮过滤（轮次 Tab 只留本轮与无轮次信息）。

场景：任务 402 单轮用例（JG0006）+ 7 轮用例（DD139，第1轮无维度只有音频）+ 任务 399 空态；
浅色 / 深色各截图，Network 记 detail / results / 音频取流。
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
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1688_tabs'),
)
TASK_ID = 402
SINGLE_CASE = '7bac162b-275d-4567-b924-954736dc3ce9'
MULTI_CASE = 'd8bdd5a6-666d-41ab-a366-6b9f3b27e564'
SINGLE_FRAG = 'JG0006_单轮接管-正常接管'
MULTI_FRAG = 'DD139_多次打断'
EMPTY_TASK_ID = int(os.environ.get('EMPTY_TASK_ID', '399'))
DARK_KEY = 'iatp:theme:v1:mode'

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
    """模拟 JS String(number)：5.0 -> '5'，4.3 -> '4.3'，1925.0 -> '1925'。"""
    if v is None:
        return '—'
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v)


def detail_and_results(task_id, case_id):
    d = api_get('/api/v1/tasks/%d/cases/%s/detail' % (task_id, case_id))['data']
    r = api_get('/api/v1/tasks/%d/cases/%s/results' % (task_id, case_id))['data']['results']
    return d, r


def expectations(task_id, case_id):
    """按接口原文独立推导弹窗应有的 Tab / 行 / 值 / 音频。"""
    d, results = detail_and_results(task_id, case_id)
    devices = list(d.get('devices') or [])
    configs = [c.get('name') for c in (d.get('metric_configs') or [])]
    # 维度点：设备 → (维度, 轮次1起|None, 值)
    points = {}  # device -> list
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

    # 结果音频：algorithm_results 的 audio_file（round_number 1 起）+ result_audios（无轮次）
    result_audios = []
    for group in (d.get('result_audios') or {}).values():
        for a in (group or []):
            result_audios.append({'name': a.get('filename') or a.get('param_code'), 'round': None})
    for r in (d.get('algorithm_results') or []):
        if r.get('param_type') == 'audio_file' and r.get('value'):
            result_audios.append({
                'name': r.get('label') or r.get('param_code'),
                'round': r.get('round_number'),
            })
    reference_audios = [{
        'name': a.get('filename') or ('音频 %s' % a.get('id')),
        'round': a.get('roundNumber') if a.get('roundNumber') is not None else a.get('round_number'),
    } for a in (d.get('audio_list') or [])]

    allp = [p for lst in points.values() for p in lst]
    has_round_tag = any(p['round'] is not None for p in allp)
    rounds = sorted({p['round'] for p in allp if p['round'] is not None}
                    | {a['round'] for a in result_audios if a['round'] is not None}
                    | {a['round'] for a in reference_audios if a['round'] is not None})
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

    # 每个 Tab 的行与值
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
        if tab['kind'] == 'round':
            tab['audios'] = [a for a in result_audios if a['round'] is None or a['round'] == tab['round']]
            tab['refs'] = [a for a in reference_audios if a['round'] is None or a['round'] == tab['round']]
        else:
            tab['audios'] = list(result_audios)
            tab['refs'] = list(reference_audios)

    return {
        'devices': devices,
        'tabs': tabs,
        'metric_configs': configs,
        'raw_detail': d,
        'exec_status': results[0].get('execution_status') if results else None,
    }


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
const audioRows = [...dlg.querySelectorAll('div')]
  .filter(d => d.className && typeof d.className === 'string'
    && d.className.includes('rounded-lg') && d.className.includes('border')
    && d.querySelector('button'))
  .map(d => (d.textContent||'').trim());
const header = dlg.querySelector('[data-slot="dialog-header"]') || dlg;
return {
  tabs, heads, rows, audioRows,
  headerText: (header.textContent||''),
  dialogText: (dlg.textContent||''),
};
"""


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
    drv.set_page_load_timeout(240)
    drv.set_script_timeout(240)
    return drv


def goto(drv, path, wait=4.0):
    drv.get(BASE + path)
    WebDriverWait(drv, 180).until(
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


def wait_text(drv, text, timeout=180):
    WebDriverWait(drv, timeout).until(lambda d: text in body_text(d))


def js_click(drv, el, wait=0.8):
    drv.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", el)
    time.sleep(wait)


def close_dialog(drv):
    try:
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    except Exception:
        pass
    time.sleep(1.2)


def open_case_dialog(drv, task_id, frag):
    goto(drv, '/tasks/%d' % task_id, wait=5)
    wait_text(drv, '关联用例')
    if frag:
        box = WebDriverWait(drv, 120).until(
            lambda d: d.find_element(By.XPATH, "//input[@placeholder='搜索用例名称或 ID…']"))
        js_click(drv, box, 0.4)
        box.send_keys(frag)
        time.sleep(3.0)
    btn = WebDriverWait(drv, 120).until(
        lambda d: d.find_elements(By.XPATH, "//button[starts-with(@title,'查看用例详情：')]")[0])
    js_click(drv, btn, 1.2)
    WebDriverWait(drv, 120).until(
        lambda d: d.find_element(By.CSS_SELECTOR, '[data-slot="case-detail-dialog"]'))
    wait_text(drv, '执行结果与指标')
    time.sleep(1.8)


def click_tab(drv, label):
    tab = WebDriverWait(drv, 60).until(
        lambda d: d.find_element(
            By.XPATH,
            "//*[@data-slot='case-detail-dialog']//*[@role='tab'][normalize-space(.)='%s']" % label))
    js_click(drv, tab, 1.2)
    return tab


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


def verify_tabs(drv, exp, tag, expect_shot=True):
    data = drv.execute_script(COLLECT_JS)
    if not data:
        check('[%s] 弹窗 DOM 可取' % tag, False, 'collect null')
        return None
    dtext = data['dialogText']

    # 1. 设备徽章
    for dev in exp['devices']:
        check('[%s] 头部设备徽章含 %s' % (tag, dev), dev in data['headerText'], data['headerText'][:120])

    # 2. Tab 列表
    want_tabs = [t['label'] for t in exp['tabs']]
    got_tabs = [t['label'] for t in data['tabs']]
    if len(want_tabs) > 1:
        check('[%s] 轮次 Tab 列表 = 接口推导 %s' % (tag, want_tabs), got_tabs == want_tabs,
              {'want': want_tabs, 'got': got_tabs})
        check('[%s] 默认选中首个 Tab' % tag,
              bool(data['tabs']) and data['tabs'][0]['selected'],
              [t for t in data['tabs'] if t['selected']])
    else:
        check('[%s] 单 Tab 不渲染 Tab 栏' % tag, not data['tabs'], got_tabs)

    # 3. 表头：指标 | 设备名 + 状态徽章，绝不出现 @round/@overall
    check('[%s] 表头首列 = 指标' % tag, data['heads'][:1] == ['指标'], data['heads'])
    check('[%s] 表头列数 = 1 指标 + %d 设备' % (tag, len(exp['devices'])),
          len(data['heads']) == 1 + len(exp['devices']), data['heads'])
    for dev in exp['devices']:
        check('[%s] 表头设备列含设备名 %s' % (tag, dev),
              any(dev in h for h in data['heads'][1:]), data['heads'])
    check('[%s] 界面不出现内部键 @round / @overall' % tag,
          '@round' not in dtext and '@overall' not in dtext,
          dtext[max(0, dtext.find('@round')):][:80])

    # 4. 当前 Tab 的行与逐值比对
    def assert_tab(tab_exp, label):
        got = data['rows']
        want = [r['dim'] for r in tab_exp['rows']]
        got_dims = [r[0] for r in got if r and r[0] != '暂无指标数据']
        if not tab_exp['rows']:
            check('[%s]「%s」无指标 → 显示暂无指标数据' % (tag, label),
                  any('暂无指标数据' in (r[0] if r else '') for r in got), got)
            return
        check('[%s]「%s」行 = 指标（%d 行，顺序照 metric_configs）' % (tag, label, len(want)),
              got_dims == want, {'want': want, 'got': got_dims})
        got_cells = [r[1:] for r in got if r and r[0] != '暂无指标数据']
        want_cells = [r['values'] for r in tab_exp['rows']]
        ok = got_cells == want_cells
        diff = []
        if not ok:
            for i, (g, w) in enumerate(zip(got_cells, want_cells)):
                if g != w:
                    diff.append({'row': want[i] if i < len(want) else None, 'got': g, 'want': w})
            if len(got_cells) != len(want_cells):
                diff.append({'len_got': len(got_cells), 'len_want': len(want_cells)})
        check('[%s]「%s」逐值 = /results 原文' % (tag, label), ok, diff[:6])

    first = exp['tabs'][0]
    assert_tab(first, first['label'])

    # 5. 音频按 Tab 过滤
    for a in first['audios']:
        check('[%s]「%s」结果音频含 %s' % (tag, first['label'], a['name']),
              a['name'] in dtext, dtext.count('结果音频'))
    for a in first['refs']:
        check('[%s]「%s」参考音频含 %s' % (tag, first['label'], a['name']),
              a['name'] in dtext, dtext.count('参考音频'))
    got_row_count = len(data['audioRows'])
    want_row_count = len(first['audios']) + len(first['refs'])
    check('[%s]「%s」音频行数 = %d' % (tag, first['label'], want_row_count),
          got_row_count == want_row_count, {'got': got_row_count, 'rows': data['audioRows']})
    if expect_shot:
        shot(drv, 'T_%s_%s' % (tag, first['label']))
    return data


def verify_tab_switch(drv, exp, tag, label, shot_name=None):
    click_tab(drv, label)
    data = drv.execute_script(COLLECT_JS)
    tab_exp = next((t for t in exp['tabs'] if t['label'] == label), None)
    if not tab_exp:
        check('[%s] Tab「%s」在接口推导中存在' % (tag, label), False, [t['label'] for t in exp['tabs']])
        return data
    selected = [t['label'] for t in data['tabs'] if t['selected']]
    check('[%s] 点「%s」后 aria-selected 切换' % (tag, label), selected == [label], selected)
    dtext = data['dialogText']
    want_dims = [r['dim'] for r in tab_exp['rows']]
    got_dims = [r[0] for r in data['rows'] if r and r[0] != '暂无指标数据']
    if want_dims:
        check('[%s]「%s」行 = 指标（%d 行）' % (tag, label, len(want_dims)),
              got_dims == want_dims, {'want': want_dims, 'got': got_dims})
        got_cells = [r[1:] for r in data['rows'] if r and r[0] != '暂无指标数据']
        want_cells = [r['values'] for r in tab_exp['rows']]
        check('[%s]「%s」逐值 = /results 原文' % (tag, label), got_cells == want_cells,
              {'got': got_cells[:6], 'want': want_cells[:6]})
    else:
        check('[%s]「%s」无指标 → 暂无指标数据' % (tag, label),
              any('暂无指标数据' in (r[0] if r else '') for r in data['rows']), data['rows'])
    for a in tab_exp['audios']:
        check('[%s]「%s」结果音频含 %s' % (tag, label, a['name']), a['name'] in dtext, '')
    for a in tab_exp['refs']:
        check('[%s]「%s」参考音频含 %s' % (tag, label, a['name']), a['name'] in dtext, '')
    check('[%s]「%s」音频行数 = %d' % (tag, label, len(tab_exp['audios']) + len(tab_exp['refs'])),
          len(data['audioRows']) == len(tab_exp['audios']) + len(tab_exp['refs']),
          data['audioRows'])
    # 反向：不属于本轮的音频不应出现（仅轮次 Tab 判定；名字互不为前缀）
    if tab_exp['kind'] == 'round':
        others = [x['name'] for t in exp['tabs'] if t['kind'] == 'round' and t['label'] != label
                  for x in t['audios'] if x['round'] is not None]
        leaked = [n for n in others if n and n in dtext]
        check('[%s]「%s」不串入其他轮次音频' % (tag, label), not leaked, leaked)
    if shot_name:
        shot(drv, shot_name)
    return data


def play_audio(drv, token, mode):
    btn = drv.find_element(
        By.XPATH,
        "//div[contains(@class,'rounded-lg') and contains(.,'%s')]//button[normalize-space(.)='试听']"
        % token)
    js_click(drv, btn, 2.0)
    WebDriverWait(drv, 60).until(lambda d: len(d.find_elements(By.TAG_NAME, 'audio')) > 0)
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
    check('[%s] %s 试听获得 http 音频地址' % (mode, token), bool(src) and src.startswith('http'), src[:180])
    check('[%s] 试听无「地址获取失败」toast' % mode,
          '音频播放地址获取失败' not in body_text(drv), '')
    print('   audio state:', info)
    shot(drv, 'T_%s_audio_play' % mode)
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(1.2)
    return src


def verify_empty(drv):
    goto(drv, '/tasks/%d' % EMPTY_TASK_ID, wait=5)
    wait_text(drv, '关联用例')
    n = len(drv.find_elements(By.XPATH, "//button[starts-with(@title,'查看用例详情：')]"))
    check('[empty] 任务 %d 有用例行' % EMPTY_TASK_ID, n > 0, n)
    btn = drv.find_elements(By.XPATH, "//button[starts-with(@title,'查看用例详情：')]")[0]
    js_click(drv, btn, 1.2)
    WebDriverWait(drv, 120).until(
        lambda d: d.find_element(By.CSS_SELECTOR, '[data-slot="case-detail-dialog"]'))
    wait_text(drv, '执行结果与指标')
    time.sleep(1.5)
    data = drv.execute_script(COLLECT_JS) or {}
    dtext = data.get('dialogText', '')
    check('[empty] 显示「暂无执行结果」空态', '暂无执行结果' in dtext, dtext[:200])
    check('[empty] 不渲染指标表', not data.get('heads'), data.get('heads'))
    check('[empty] 不渲染轮次 Tab 栏', not data.get('tabs'), data.get('tabs'))
    check('[empty] 无结果音频区', '结果音频' not in dtext, '')
    shot(drv, 'T_empty_task%d' % EMPTY_TASK_ID)
    return dtext[:400]


def main():
    os.makedirs(ART, exist_ok=True)
    single = expectations(TASK_ID, SINGLE_CASE)
    multi = expectations(TASK_ID, MULTI_CASE)
    for tag, exp in (('single', single), ('multi', multi)):
        with open(os.path.join(ART, 'expected_%s.json' % tag), 'w', encoding='utf-8') as f:
            json.dump({
                'devices': exp['devices'],
                'tabs': [{'label': t['label'], 'rows': t['rows'],
                          'audios': t['audios'], 'refs': t['refs']} for t in exp['tabs']],
            }, f, ensure_ascii=False, indent=1)
        print('[EXPECT %s] tabs=%s' % (tag, [t['label'] for t in exp['tabs']]))
        print('   first tab rows=%s' % [r['dim'] for r in exp['tabs'][0]['rows']][:8])

    drv = build_driver()
    ev = {'base': BASE, 'api': API}
    try:
        # ---------- 单轮用例 · 浅色 ----------
        open_case_dialog(drv, TASK_ID, SINGLE_FRAG)
        net0 = read_perf(drv)
        ev['net_single'] = {
            'detail': statuses(net0, '/cases/%s/detail' % SINGLE_CASE),
            'results': statuses(net0, '/cases/%s/results' % SINGLE_CASE),
        }
        check('Network：GET .../detail → 200', ev['net_single']['detail'] == [200], ev['net_single']['detail'])
        check('Network：GET .../results → 200', ev['net_single']['results'] == [200], ev['net_single']['results'])
        ev['single_light'] = verify_tabs(drv, single, 'single-light')

        # 整体 Tab（单轮也有整体维度值）
        if any(t['label'] == '整体' for t in single['tabs']):
            ev['single_overall'] = verify_tab_switch(
                drv, single, 'single-light', '整体', 'T_single-light_整体')

        # 试听：结果音频 + 参考音频
        ev['play_result'] = play_audio(drv, 'user_wav', 'single-light')
        net = read_perf(drv)
        ev['net_audio'] = [(u.split('?')[0][-46:], st, mime) for u, st, mime in net if ':9000' in u]
        ev['net_stream'] = statuses(net, '/audios/stream-by-path')
        print('   net_audio:', ev['net_audio'])
        print('   net_stream:', ev['net_stream'])
        check('Network：音频取流（preview/9000）有 2xx/3xx 响应',
              any(200 <= st < 400 for _, st, _ in ev['net_audio'])
              or ev['net_stream'] == [200],
              {'nine_k': ev['net_audio'], 'stream': ev['net_stream']})
        try:
            ev['play_reference'] = play_audio(drv, '_silence.wav', 'single-light')
        except Exception as exc:  # noqa: BLE001
            check('[single-light] 参考音频试听入口', False, repr(exc)[:200])
        close_dialog(drv)

        # ---------- 单轮用例 · 深色 ----------
        drv.execute_script("localStorage.setItem(arguments[0], 'dark')", DARK_KEY)
        open_case_dialog(drv, TASK_ID, SINGLE_FRAG)
        dark_cls = drv.execute_script('return document.documentElement.className')
        check('深色主题已生效', 'dark' in (dark_cls or ''), dark_cls)
        ev['single_dark'] = verify_tabs(drv, single, 'single-dark')
        shot(drv, 'T_single-dark_第1轮')
        close_dialog(drv)
        drv.execute_script("localStorage.setItem(arguments[0], 'light')", DARK_KEY)

        # ---------- 7 轮用例（DD139）· 浅色 ----------
        open_case_dialog(drv, TASK_ID, MULTI_FRAG)
        net1 = read_perf(drv)
        ev['net_multi'] = {
            'detail': statuses(net1, '/cases/%s/detail' % MULTI_CASE),
            'results': statuses(net1, '/cases/%s/results' % MULTI_CASE),
        }
        check('Network：多轮 GET .../detail → 200', ev['net_multi']['detail'] == [200], ev['net_multi']['detail'])
        check('Network：多轮 GET .../results → 200', ev['net_multi']['results'] == [200], ev['net_multi']['results'])
        ev['multi_round1'] = verify_tabs(drv, multi, 'multi-light')
        shot(drv, 'T_multi-light_第1轮')
        # 第7轮 + 整体
        ev['multi_round7'] = verify_tab_switch(drv, multi, 'multi-light', '第7轮', 'T_multi-light_第7轮')
        ev['multi_overall'] = verify_tab_switch(drv, multi, 'multi-light', '整体', 'T_multi-light_整体')
        # 回第2轮，确认真有维度值的那一轮
        ev['multi_round2'] = verify_tab_switch(drv, multi, 'multi-light', '第2轮', 'T_multi-light_第2轮')
        close_dialog(drv)

        # ---------- 7 轮用例 · 深色 ----------
        drv.execute_script("localStorage.setItem(arguments[0], 'dark')", DARK_KEY)
        open_case_dialog(drv, TASK_ID, MULTI_FRAG)
        ev['multi_dark'] = verify_tabs(drv, multi, 'multi-dark')
        verify_tab_switch(drv, multi, 'multi-dark', '第7轮', 'T_multi-dark_第7轮')
        close_dialog(drv)
        drv.execute_script("localStorage.setItem(arguments[0], 'light')", DARK_KEY)

        # ---------- 控制台错误 ----------
        severe = [e for e in drv.get_log('browser')
                  if e.get('level') == 'SEVERE' and 'cherry-picks' not in e.get('message', '')]
        ev['console_severe'] = severe[-10:]
        check('浏览器控制台无本卡相关 SEVERE', not severe,
              [s.get('message', '')[:160] for s in severe[-5:]])

        # ---------- 空态 ----------
        ev['empty'] = verify_empty(drv)
    finally:
        try:
            drv.quit()
        except Exception:
            pass

    failed = [r for r in RESULT if not r['ok']]
    ev['checks'] = RESULT
    ev['failed'] = len(failed)
    with open(os.path.join(ART, 'evidence.json'), 'w', encoding='utf-8') as f:
        json.dump(ev, f, ensure_ascii=False, indent=1, default=str)
    print('\n==== %d checks, %d failed ====' % (len(RESULT), len(failed)))
    for r in failed:
        print('[FAIL]', r['name'], '|', r['detail'][:300])
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
