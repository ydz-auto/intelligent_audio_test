# -*- coding: utf-8 -*-
"""INT-1688 返工实测：case-detail 弹窗按 V9.7.10 轮次 Tab 呈现（行=指标 / 列=设备）。

口径（INT-1723 回写后的 10_测试执行.md §5.2，INT-1688 06:08 返工裁定）：
- 轮次 Tab：第1轮…第N轮 + 整体（整体有评估值才出现）；无轮次标记 → 单个「指标」Tab；
- 表体：行=指标（metric_configs 顺序），列=设备（表头=设备名 + 执行状态徽章）；
  `@round:{n}` / `@overall` 只是内部键，不得出现在界面上；
- 结果音频（detail `result_audios`）**不随轮次 Tab 过滤**，按设备分组全量（空则整块不渲染）；
- 执行结果音频（`algorithm_results` 的 audio_file 项）按当前 Tab 与轮次过滤，
  label 用原始参数名（去掉 `@round:N` / `@overall`）+ 单个轮次 chip（不重复）；
- 参考音频（`audio_list`）按当前 Tab 过滤（现状保留）；
- 换用例时轮次 Tab 复位到第一个有数据的 Tab。

验收点：
1. 单轮用例（任务 402 / 7bac162b…）：Tab = 第1轮 + 整体，6 个维度行、设备名 pura90小艺；
2. 多轮用例（任务 402 / d8bdd5a6… DD139，7 轮）：Tab = 第1轮…第7轮 + 整体，
   切第7轮后值与音频随轮变化（第1轮音频不再显示）、label 不带「（第N轮）」；
3. 换用例复位：停在多轮「第7轮」后开单轮用例 → 默认落在「第1轮」；
4. 结果音频块：有数据时按设备分组全量（与 Tab 无关），无数据时整块不渲染；
5. 浅 / 深色截图 + Network（detail / results 均 200）；
6. 无结果用例（任务 399）空态不回归。

环境：docker 真实库栈 15000 + 本 worktree dev server（-c rsbuild.realstack.config.ts 代理 15000）。
"""
import json
import os
import re
import sys
import time
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:5391').rstrip('/')
API = os.environ.get('BACKEND_BASE', 'http://127.0.0.1:15000').rstrip('/')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.environ.get(
    'ART_DIR',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1688-rounds'),
)
TASK_ID = 402
# 单轮：JG0006 单轮接管；多轮：DD139 多次打断（7 轮）
SINGLE_CASE_ID = '7bac162b-275d-4567-b924-954736dc3ce9'
SINGLE_FRAG = 'JG0006_单轮接管-正常接管'
MULTI_CASE_ID = 'd8bdd5a6-666d-41ab-a366-6b9f3b27e564'
MULTI_FRAG = 'DD139'
EMPTY_TASK_ID = int(os.environ.get('EMPTY_TASK_ID', '399'))
DARK_KEY = 'iatp:theme:v1:mode'

RESULT = []

try:  # Windows 控制台是 GBK，中文证据直接 print 会 UnicodeEncodeError
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass


def check(name, ok, detail=''):
    RESULT.append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:2000]})
    print(('[PASS] ' if ok else '[FAIL] ') + name + (' | ' + str(detail)[:500] if detail else ''))
    return ok


def api_get(path, attempts=4):
    last = None
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(API + path, timeout=300) as r:
                return json.loads(r.read().decode('utf-8'))['data']
        except Exception as exc:  # 真实栈偶发 gRPC DEADLINE_EXCEEDED
            last = exc
            time.sleep(2)
    raise last


def js_str(value):
    """后端值 → 前端 String(value) 显示口径（1.0 → '1'，0.75 → '0.75'，null → '—'）"""
    if value is None:
        return '—'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def expected_view(case_id):
    """按接口原文算期望：Tab 文案、每 Tab 的指标行（名→值）、按轮音频名。"""
    detail = api_get('/api/v1/tasks/%d/cases/%s/detail' % (TASK_ID, case_id))
    results = api_get('/api/v1/tasks/%d/cases/%s/results' % (TASK_ID, case_id))['results']
    devices = detail.get('devices') or []
    configured = [c['name'] for c in (detail.get('metric_configs') or [])]

    # 设备 → {(dimension, round|None): value}；round 为 1 起（round_number + 1）
    points = {}
    for row in results:
        name = row.get('device_name')
        if not name or name in points:
            continue
        bucket = {}
        for d in row.get('dimensions') or []:
            rn = d.get('round_number')
            bucket[(d['name'], None if rn is None else rn + 1)] = d.get('value')
        points[name] = bucket

    all_points = [k for bucket in points.values() for k in bucket]
    has_round = any(r is not None for _, r in all_points)
    audio_rounds = [
        a.get('round_number')
        for a in (detail.get('algorithm_results') or [])
        if a.get('param_type') == 'audio_file' and a.get('round_number') is not None
    ]
    audio_rounds += [
        a.get('roundNumber')
        for a in (detail.get('audio_list') or [])
        if a.get('roundNumber') is not None
    ]

    def rows_for(accept):
        """行=指标（metric_configs 顺序），列=设备；只对满足 accept(round) 的点出行。"""
        seen = []
        for dim, rnd in all_points:
            if accept(rnd) and dim not in seen:
                seen.append(dim)
        order = [n for n in configured if n in seen] + [n for n in seen if n not in configured]
        out = []
        for dim in order:
            values = {}
            for dev in devices:
                hit = [k for k in points.get(dev, {}) if k[0] == dim and accept(k[1])]
                if hit:
                    values[dev] = js_str(points[dev][hit[0]])
            out.append({'dimension': dim, 'values': values})
        return out

    tabs = []
    if not has_round:
        tabs.append({'label': '指标', 'kind': 'all', 'round': None,
                     'rows': rows_for(lambda r: True)})
    else:
        rounds = sorted({r for _, r in all_points if r is not None} | set(audio_rounds))
        for rnd in rounds:
            tabs.append({'label': '第%d轮' % rnd, 'kind': 'round', 'round': rnd,
                         'rows': rows_for(lambda r, _r=rnd: r == _r)})
        overall_values = [
            value for bucket in points.values() for key, value in bucket.items() if key[1] is None
        ]
        if any(v not in (None, '') for v in overall_values):
            tabs.append({'label': '整体', 'kind': 'overall', 'round': None,
                         'rows': rows_for(lambda r: r is None)})

    # 执行结果音频（algorithm_results 的 audio_file 项）：UI label = 原始参数名（去掉内部后缀），
    # 轮次信息只在 chip 上出现一次（P3 返工）。
    audios = []
    for a in detail.get('algorithm_results') or []:
        if a.get('param_type') != 'audio_file' or not a.get('value'):
            continue
        code = a.get('param_code') or ''
        base = re.sub(r'@round:\d+$', '', code, flags=re.I)
        base = re.sub(r'@overall$', '', base, flags=re.I).strip() or code
        m = re.search(r'@round:(\d+)$', code, flags=re.I)
        overall = bool(re.search(r'@overall$', code, flags=re.I))
        audios.append({
            'label': base,
            'round': int(m.group(1)) if m else (None if overall else a.get('round_number')),
            'overall': overall,
            'dimension': a.get('dimension_name'),
        })
    refs = [
        {'label': a.get('filename'), 'round': a.get('roundNumber')}
        for a in detail.get('audio_list') or []
    ]

    # 结果音频（detail result_audios）：按设备分组，不随 Tab 过滤。
    result_audio_groups = []
    for device, items in (detail.get('result_audios') or {}).items():
        names = [
            (i.get('filename') or i.get('param_code') or '')
            for i in (items or [])
        ]
        result_audio_groups.append({'device': device, 'names': [n for n in names if n]})

    return {
        'devices': devices,
        'tabs': tabs,
        'audios': audios,
        'refs': refs,
        'resultAudioGroups': result_audio_groups,
        'configured': configured,
    }


def tab_has_data(tab):
    """V9.7.10 tabHasMetricData：Tab 内任一维度值非空且非「—」才算有数据。"""
    return any(
        value not in ('', '—')
        for row in tab['rows']
        for value in row['values'].values()
    )


def visible_audio_labels(expected, tab):
    """执行结果音频字段按 Tab 的可见集合（V9.7.10 :834-891 同口径，独立重算）。"""
    kind = tab.get('kind')
    rnd = tab.get('round')
    out = []
    for a in expected['audios']:
        if kind in (None, 'all'):
            ok = True
        elif kind == 'overall':
            ok = True if a['dimension'] is None else a['overall']
        else:
            ok = False if a['overall'] else (a['round'] is None or a['round'] == rnd)
        if ok:
            out.append(a['label'])
    return out


def visible_ref_labels(expected, tab):
    if tab.get('kind') != 'round':
        return [r['label'] for r in expected['refs']]
    return [r['label'] for r in expected['refs'] if r['round'] in (None, tab.get('round'))]


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
    drv.set_page_load_timeout(120)
    drv.set_script_timeout(120)
    return drv


def goto(drv, path, wait=5.0):
    drv.get(BASE + path)
    WebDriverWait(drv, 90).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(wait)


def shot(drv, name):
    os.makedirs(ART, exist_ok=True)
    p = os.path.join(ART, name + '.png')
    drv.save_screenshot(p)
    print('shot:', p)
    return p


def body_text(drv):
    return drv.execute_script('return document.body.textContent || ""') or ''


def wait_text(drv, text, timeout=90):
    WebDriverWait(drv, timeout).until(lambda d: text in body_text(d))


def js_click(drv, el, wait=0.8):
    drv.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", el)
    time.sleep(wait)


COLLECT_JS = r"""
const dlg = document.querySelector('[data-slot="case-detail-dialog"]');
if (!dlg) return null;
const header = dlg.querySelector('[data-slot="dialog-header"]') || dlg;
const badges = [...header.querySelectorAll('span.flex.flex-wrap.gap-1 span')].map(s => (s.textContent||'').trim());
const tabs = [...dlg.querySelectorAll('[role="tab"]')].map(b => ({
  label: (b.textContent||'').trim(),
  selected: b.getAttribute('aria-selected') === 'true',
}));
const table = dlg.querySelector('table');
const heads = table ? [...table.querySelectorAll('thead th')].map(t => (t.textContent||'').trim()) : [];
const rows = table ? [...table.querySelectorAll('tbody tr')].map(tr =>
  [...tr.querySelectorAll('td')].map(td => (td.textContent||'').trim())) : [];
const rowSpans = el => [...el.querySelectorAll('span')].map(s => (s.textContent||'').trim()).filter(Boolean);
const sectionByLabel = label => {
  const p = [...dlg.querySelectorAll('p')].find(x => (x.textContent||'').trim() === label);
  return p ? p.parentElement : null;
};
// 执行结果音频：每行 = [label, chip..., device?]
const fieldBlock = sectionByLabel('执行结果音频');
const fieldRows = fieldBlock
  ? [...fieldBlock.querySelectorAll('div.flex.items-center.gap-2.rounded-lg.border')]
      .map(d => ({ spans: rowSpans(d), preview: (d.textContent||'').trim() }))
  : [];
// 结果音频（按设备分组）：组标题 = 设备名
const resBlock = sectionByLabel('结果音频');
let resGroups = [];
if (resBlock) {
  let current = null;
  for (const child of [...resBlock.children]) {
    if (child.tagName === 'P' && child.classList.contains('font-medium')) { current = { device: (child.textContent||'').trim(), rows: [] }; resGroups.push(current); }
    else if (current && child.querySelectorAll) {
      for (const d of [...child.querySelectorAll('div.flex.items-center.gap-2.rounded-lg.border')]) {
        current.rows.push({ spans: rowSpans(d), preview: (d.textContent||'').trim() });
      }
    }
  }
}
const refBlock = sectionByLabel('参考音频（用例输入）');
const refRows = refBlock
  ? [...refBlock.querySelectorAll('div.flex.items-center.gap-2.rounded-lg.border')]
      .map(d => ({ spans: rowSpans(d), preview: (d.textContent||'').trim() }))
  : [];
return {
  badges,
  tabs,
  heads,
  rows,
  fieldRows,
  resultAudioGroups: resGroups,
  refRows,
  hasResultAudioBlock: !!resBlock,
  dialogText: (dlg.textContent || ''),
  audioSrc: [...dlg.querySelectorAll('audio')].map(a => a.currentSrc || a.src || ''),
};
"""


def click_tab(drv, label):
    btn = WebDriverWait(drv, 30).until(
        lambda d: d.find_element(
            By.XPATH,
            "//*[@data-slot='case-detail-dialog']//*[@role='tab'][normalize-space(.)='%s']" % label,
        )
    )
    js_click(drv, btn, 1.0)


def close_dialog(drv):
    try:
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(1.0)
    except Exception:
        pass


def open_case_dialog(drv, frag, attempt=1):
    goto(drv, '/tasks/%d' % TASK_ID, wait=5)
    try:
        wait_text(drv, '关联用例', 180)
    except Exception:
        if attempt <= 2:
            print('RETRY 任务详情接口超时，attempt=%d' % attempt)
            btn = drv.find_elements(By.XPATH, "//button[normalize-space(.)='重试']")
            if btn:
                js_click(drv, btn[0], 1.0)
            return open_case_dialog(drv, frag, attempt + 1)
        raise
    box = WebDriverWait(drv, 60).until(
        lambda d: d.find_element(By.XPATH, "//input[@placeholder='搜索用例名称或 ID…']")
    )
    js_click(drv, box, 0.4)
    box.send_keys(frag)
    time.sleep(2.5)
    btn = WebDriverWait(drv, 60).until(
        lambda d: d.find_element(
            By.XPATH,
            "//button[starts-with(@title,'查看用例详情：')][contains(@title,'%s')]" % frag,
        )
    )
    js_click(drv, btn, 1.0)
    WebDriverWait(drv, 60).until(
        lambda d: d.find_element(By.CSS_SELECTOR, '[data-slot="case-detail-dialog"]')
    )
    try:
        wait_text(drv, '执行结果与指标', 90)
    except Exception:
        if attempt <= 2:
            print('RETRY 用例详情接口超时，attempt=%d' % attempt)
            close_dialog(drv)
            return open_case_dialog(drv, frag, attempt + 1)
        raise
    time.sleep(1.2)


def open_case_dialog_same_page(drv, frag):
    """同页换用例（不 reload，保留组件状态）——用于验证 P3 换用例复位 Tab。"""
    close_dialog(drv)
    WebDriverWait(drv, 30).until(
        lambda d: not d.find_elements(By.CSS_SELECTOR, '[data-slot="case-detail-dialog"]')
    )
    box = WebDriverWait(drv, 60).until(
        lambda d: d.find_element(By.XPATH, "//input[@placeholder='搜索用例名称或 ID…']")
    )
    box.clear()
    js_click(drv, box, 0.3)
    box.send_keys(frag)
    time.sleep(2.5)
    btn = WebDriverWait(drv, 60).until(
        lambda d: d.find_element(
            By.XPATH,
            "//button[starts-with(@title,'查看用例详情：')][contains(@title,'%s')]" % frag,
        )
    )
    js_click(drv, btn, 1.0)
    WebDriverWait(drv, 60).until(
        lambda d: d.find_element(By.CSS_SELECTOR, '[data-slot="case-detail-dialog"]')
    )
    wait_text(drv, '执行结果与指标', 90)
    time.sleep(1.2)


def collect(drv):
    return drv.execute_script(COLLECT_JS) or {}


def verify_case(drv, expected, tag):
    """核对当前打开的弹窗：Tab 列表 / 每 Tab 行=指标列=设备 / 内部键不外露 / 音频口径。"""
    data = collect(drv)
    dtext = data.get('dialogText', '')
    tabs = [t['label'] for t in data.get('tabs', [])]
    want_tabs = [t['label'] for t in expected['tabs']]

    check('%s：弹窗打开且含「执行结果与指标」' % tag, '执行结果与指标' in dtext, dtext[:120])
    check('%s：轮次 Tab = %s' % (tag, want_tabs), tabs == want_tabs, {'want': want_tabs, 'got': tabs})
    check('%s：内部键 @round/@overall 不外露' % tag,
          '@round' not in dtext and '@overall' not in dtext, dtext[:200])
    for dev in expected['devices']:
        check('%s：设备名 %s 在头部徽章' % (tag, dev), dev in data.get('badges', []), data.get('badges'))
        check('%s：表头设备列 = %s' % (tag, dev),
              bool(data.get('heads'))
              and data['heads'][0] == '指标'
              and any(dev in h for h in data['heads'][1:]),
              data.get('heads'))

    # 结果音频（result_audios）：不随 Tab 过滤，按设备分组；空数据整块不渲染
    want_groups = expected['resultAudioGroups']
    got_groups = data.get('resultAudioGroups') or []
    check('%s：结果音频块%s' % (tag, '存在' if want_groups else '不渲染（result_audios 为空）'),
          bool(got_groups) == bool(want_groups),
          {'want_groups': want_groups, 'got_groups': got_groups})
    if want_groups:
        check('%s：结果音频按设备分组（组标题=设备名）' % tag,
              [g['device'] for g in got_groups] == [g['device'] for g in want_groups],
              {'want': [g['device'] for g in want_groups], 'got': [g['device'] for g in got_groups]})
        want_names = [n for g in want_groups for n in g['names']]
        got_names = [r['spans'][0] for g in got_groups for r in g['rows']]
        check('%s：结果音频行 = filename（全量）' % tag, got_names == want_names,
              {'want': want_names, 'got': got_names})

    # 默认 Tab = 第一个有数据的轮次（V9.7.10 tabHasMetricData + :1317-1328），
    # 多轮用例第1轮没有维度值时默认落在第2轮。
    first = next((t for t in expected['tabs'] if tab_has_data(t)), expected['tabs'][0])
    check('%s：默认选中第一个有数据的 Tab「%s」' % (tag, first['label']),
          any(t['label'] == first['label'] and t['selected'] for t in data.get('tabs', [])),
          data.get('tabs'))
    _check_rows(tag, data, first, expected)
    _check_audios(tag, data, first, expected)

    if len(expected['tabs']) > 1:
        last = expected['tabs'][-1]
        click_tab(drv, last['label'])
        data2 = collect(drv)
        _check_rows(tag, data2, last, expected)
        _check_audios(tag, data2, last, expected)
        # P2：结果音频块与 Tab 无关（切 Tab 后内容不变）
        if want_groups:
            check('%s：结果音频不随轮次 Tab 过滤' % tag,
                  (data2.get('resultAudioGroups') or []) == got_groups,
                  {'before': got_groups, 'after': data2.get('resultAudioGroups')})
        return data2
    return data


def _check_rows(tag, data, tab_expected, expected):
    rows = data.get('rows') or []
    want_rows = tab_expected['rows']
    if not want_rows:
        # 该轮无评估维度（如多轮用例第1轮只有音频）→ 表体只留「暂无指标数据」占位行
        placeholder = (not rows) or (
            len(rows) == 1 and rows[0] and rows[0][0] == '暂无指标数据'
        )
        check('%s·%s：本轮无指标 → 「暂无指标数据」' % (tag, tab_expected['label']),
              placeholder and '暂无指标数据' in data.get('dialogText', ''),
              {'rows': rows})
        return
    check('%s·%s：指标行数 = %d（行=指标）' % (tag, tab_expected['label'], len(want_rows)),
          len(rows) == len(want_rows), {'want': len(want_rows), 'got': len(rows), 'ui': rows})
    ui_by_dim = {}
    for row in rows:
        if row and row[0]:
            ui_by_dim[row[0]] = row[1:]
    for exp in want_rows:
        ui_vals = ui_by_dim.get(exp['dimension'])
        want_vals = [exp['values'].get(dev, '—') for dev in expected['devices']]
        check('%s·%s：指标「%s」各设备值' % (tag, tab_expected['label'], exp['dimension']),
              ui_vals == want_vals, {'want': want_vals, 'got': ui_vals})


def _check_audios(tag, data, tab_expected, expected):
    label = '%s·%s' % (tag, tab_expected['label'])
    # 执行结果音频字段：按 Tab 过滤，label = 原始参数名（不带「（第N轮）」）
    want = visible_audio_labels(expected, tab_expected)
    got_rows = data.get('fieldRows') or []
    got = [r['spans'][0] for r in got_rows if r.get('spans')]
    check('%s：执行结果音频 = %s' % (label, want), got == want, {'want': want, 'got': got})
    dup = [r['preview'] for r in got_rows if '（第' in r['preview'] or '第' in (r['spans'][0] if r.get('spans') else '')]
    check('%s：音频 label 不含轮次（轮次只在 chip，P3）' % label, not dup, dup)
    chips = [s for r in got_rows for s in r.get('spans', [])[1:] if re.fullmatch(r'第\d+轮|整体', s)]
    check('%s：每条音频至多一个轮次 chip' % label,
          all(sum(1 for s in r.get('spans', []) if re.fullmatch(r'第\d+轮|整体', s)) <= 1 for r in got_rows),
          [r.get('spans') for r in got_rows])

    # 参考音频（audio_list）：按当前 Tab 轮次过滤（现状保留）
    want_ref = visible_ref_labels(expected, tab_expected)
    got_ref = [r['spans'][0] for r in (data.get('refRows') or []) if r.get('spans')]
    check('%s：参考音频 = %d 条' % (label, len(want_ref)), got_ref == want_ref,
          {'want': want_ref, 'got': got_ref})


def network_responses(drv):
    out = []
    for entry in drv.get_log('performance'):
        try:
            msg = json.loads(entry['message'])['message']
        except Exception:
            continue
        if msg.get('method') != 'Network.responseReceived':
            continue
        p = msg['params']
        out.append((p['response']['url'], p['response']['status']))
    return out


def network_status(netlog, needle):
    return [(url.split('?')[0][-70:], status) for url, status in netlog if needle in url]


def verify_audio_play(drv):
    """结果音频试听 → 预签名地址（stream-by-path 复用 INT-356 弹窗）。"""
    try:
        btn = drv.find_element(
            By.XPATH,
            "//*[@data-slot='case-detail-dialog']//button[normalize-space(.)='试听']",
        )
        js_click(drv, btn, 0.5)
        # 预签名地址经网关换取，最长等 30s；同时等试听弹窗挂出（2 个 role=dialog）
        deadline = time.time() + 30
        srcs, dialogs = [], 1
        while time.time() < deadline:
            srcs = drv.execute_script(
                "return [...document.querySelectorAll('audio')].map(a => a.currentSrc || a.src || '')"
            )
            dialogs = drv.execute_script(
                "return [...document.querySelectorAll('[role=\"dialog\"]')].length"
            )
            if any(s.startswith('http') for s in srcs) and dialogs >= 2:
                break
            time.sleep(0.5)
        check('试听弹窗拿到真实音频地址（预签名）', any(s.startswith('http') for s in srcs), srcs)
        check('无「音频播放地址获取失败」', '音频播放地址获取失败' not in body_text(drv), '')
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        deadline = time.time() + 10
        while time.time() < deadline:
            still = drv.execute_script(
                "return [...document.querySelectorAll('[role=\"dialog\"]')].length"
            )
            if still == 1:
                break
            time.sleep(0.5)
        check('ESC 关闭试听弹窗后仅剩用例详情弹窗', still == 1, still)
    except Exception as exc:  # noqa: BLE001
        check('试听入口可点击', False, repr(exc)[:300])


def verify_empty_state(drv):
    goto(drv, '/tasks/%d' % EMPTY_TASK_ID, wait=5)
    try:
        wait_text(drv, '关联用例', 180)
    except Exception:
        btn = drv.find_elements(By.XPATH, "//button[normalize-space(.)='重试']")
        if btn:
            js_click(drv, btn[0], 1.5)
        wait_text(drv, '关联用例', 180)
    btn = WebDriverWait(drv, 60).until(
        lambda d: d.find_elements(By.XPATH, "//button[starts-with(@title,'查看用例详情：')]")[0]
    )
    js_click(drv, btn, 1.0)
    WebDriverWait(drv, 60).until(
        lambda d: d.find_element(By.CSS_SELECTOR, '[data-slot="case-detail-dialog"]')
    )
    wait_text(drv, '执行结果与指标', 60)
    time.sleep(1.0)
    data = collect(drv)
    dtext = data.get('dialogText', '')
    check('空态：弹窗可打开且含「执行结果与指标」', '执行结果与指标' in dtext, dtext[:120])
    check('空态：显示「暂无执行结果」（不回归）', '暂无执行结果' in dtext, dtext[:200])
    check('空态：不渲染指标表', not data.get('heads'), data.get('heads'))
    check('空态：无结果音频区', '结果音频' not in dtext, '')
    return shot(drv, 'R_case_detail_task%d_empty' % EMPTY_TASK_ID)


def main():
    single = expected_view(SINGLE_CASE_ID)
    multi = expected_view(MULTI_CASE_ID)
    print('单轮期望：', json.dumps(single, ensure_ascii=False)[:1200])
    print('多轮期望：', json.dumps(multi, ensure_ascii=False)[:1200])
    evidence = {'base': BASE, 'single': single, 'multi': multi, 'shots': {}}
    drv = build_driver()
    try:
        # ---------- 单轮（浅色） ----------
        open_case_dialog(drv, SINGLE_FRAG)
        data = verify_case(drv, single, '单轮')
        click_tab(drv, single['tabs'][0]['label'])
        evidence['shots']['single_light'] = shot(drv, 'R_case_detail_task402_single_light')
        verify_audio_play(drv)
        # 「整体」Tab 图
        if len(single['tabs']) > 1:
            click_tab(drv, single['tabs'][-1]['label'])
            evidence['shots']['single_overall_light'] = shot(
                drv, 'R_case_detail_task402_single_overall_light'
            )
        netlog = network_responses(drv)
        evidence['network'] = {
            'detail': network_status(netlog, '/cases/%s/detail' % SINGLE_CASE_ID),
            'results': network_status(netlog, '/cases/%s/results' % SINGLE_CASE_ID),
        }
        check('Network：GET .../detail → 200',
              any(c == 200 for _, c in evidence['network']['detail']), evidence['network']['detail'])
        check('Network：GET .../results → 200',
              any(c == 200 for _, c in evidence['network']['results']), evidence['network']['results'])

        # ---------- 多轮（浅色） ----------
        open_case_dialog(drv, MULTI_FRAG)
        verify_case(drv, multi, '多轮')
        click_tab(drv, '第1轮')
        evidence['shots']['multi_round1_light'] = shot(drv, 'R_case_detail_task402_multi_round1_light')
        click_tab(drv, '第7轮')
        data7 = collect(drv)
        check('多轮：第7轮 Tab 内值随轮次变化',
              any(r and r[0] == '打断成功数量' for r in (data7.get('rows') or [])),
              data7.get('rows'))
        evidence['shots']['multi_round7_light'] = shot(drv, 'R_case_detail_task402_multi_round7_light')

        netlog_multi = network_responses(drv)
        evidence['network_multi'] = {
            'detail': network_status(netlog_multi, '/cases/%s/detail' % MULTI_CASE_ID),
            'results': network_status(netlog_multi, '/cases/%s/results' % MULTI_CASE_ID),
        }
        check('Network：多轮 GET .../detail → 200',
              any(c == 200 for _, c in evidence['network_multi']['detail']),
              evidence['network_multi']['detail'])
        check('Network：多轮 GET .../results → 200',
              any(c == 200 for _, c in evidence['network_multi']['results']),
              evidence['network_multi']['results'])

        # ---------- P3：同页换用例，轮次 Tab 复位到第一个有数据的 Tab ----------
        stuck = [t['label'] for t in (collect(drv).get('tabs') or []) if t.get('selected')]
        open_case_dialog_same_page(drv, SINGLE_FRAG)
        after = collect(drv)
        sel = [t['label'] for t in (after.get('tabs') or []) if t.get('selected')]
        want_sel = next((t['label'] for t in single['tabs'] if tab_has_data(t)),
                        single['tabs'][0]['label'])
        check('P3：换用例后轮次 Tab 复位（多轮停在「%s」→ 单轮默认「%s」）'
              % ('/'.join(stuck), want_sel),
              sel == [want_sel], {'before': stuck, 'after': sel,
                                  'tabs': after.get('tabs')})
        _check_rows('换用例复位', after,
                    next((t for t in single['tabs'] if tab_has_data(t)), single['tabs'][0]), single)
        evidence['shots']['reset_after_switch_light'] = shot(
            drv, 'R_case_detail_task402_reset_after_switch_light'
        )

        # ---------- 深色（同源 reload） ----------
        drv.execute_script("localStorage.setItem(arguments[0], 'dark')", DARK_KEY)
        open_case_dialog(drv, SINGLE_FRAG)
        dark_html = drv.execute_script('return document.documentElement.className')
        check('深色主题已生效', 'dark' in (dark_html or ''), dark_html)
        verify_case(drv, single, '单轮·深色')
        evidence['shots']['single_dark'] = shot(drv, 'R_case_detail_task402_single_dark')
        open_case_dialog(drv, MULTI_FRAG)
        click_tab(drv, '第7轮')
        check('深色：多轮第7轮可切', '第7轮' in body_text(drv), '')
        evidence['shots']['multi_round7_dark'] = shot(
            drv, 'R_case_detail_task402_multi_round7_dark'
        )
        drv.execute_script("localStorage.setItem(arguments[0], 'light')", DARK_KEY)
        time.sleep(0.5)

        # ---------- 空态 ----------
        evidence['shots']['empty'] = verify_empty_state(drv)
    finally:
        try:
            drv.quit()
        except Exception:
            pass

    failed = [r for r in RESULT if not r['ok']]
    evidence['checks'] = RESULT
    evidence['failed'] = len(failed)
    os.makedirs(ART, exist_ok=True)
    with open(os.path.join(ART, 'evidence.json'), 'w', encoding='utf-8') as f:
        json.dump(evidence, f, ensure_ascii=False, indent=2)
    print('\n==== %d checks, %d failed ====' % (len(RESULT), len(failed)))
    for r in failed:
        print('[FAIL]', r['name'], '|', r['detail'])
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
