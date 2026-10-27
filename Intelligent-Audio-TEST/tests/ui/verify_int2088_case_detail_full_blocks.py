# -*- coding: utf-8 -*-
"""INT-2088 验收：任务用例执行详情模态窗 V9.7.10 全块浏览器实测。

环境（docker 真实库栈）：前端旁路容器 :15248（本卡交付 dist，nginx 反代 api_gateway:5000），
后端网关 http://localhost:15000（/health → database=intelligent_audio_test）。
登录：接线测试_admin / JieXianTest@2026（RSA 链路由前端页面 JS 处理，Selenium 只填表单提交）。

验收点（对 15_报告域 §3.5 + 10_测试执行 §5.2 逐块勾核）：
1. 弹窗打开 → 分节①「执行结果与指标」；轮次 Tab 单轴（RoundTabBar）——多轮渲染、单轮不渲染 Tab 栏；
2. 评分指标：层级分组表（行=指标、列=设备），值与 /results 逐字段一致；
3. 多轮对话结果（algorithmResults.rounds 检测；真实库 param_code=rounds 的 json 项 value 数组形态）；
4. 执行结果块：参考数据（referenceParams 有数据才渲染）/ 用例参数（无数据源 → 「暂无数据」空态）/
   评估结果（维度 tab 切换 + 每设备 kv）/ 设备·API 执行结果 / 时间轴对比 / 音频时间轴；
5. Tab 切换各块同步；换用例关闭重开回到第一个有数据 Tab（INT-1861 口径）；
6. 空态（无执行结果用例）：「暂无执行结果」；
7. Network GET /detail、/results 均 200；console 无 SEVERE；浅/深色附图。
"""
import json
import os
import sys
import time
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'tests', 'ui'))
sys.path.insert(0, 'tests/ui')

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://localhost:15248').rstrip('/')
API = os.environ.get('BACKEND_BASE', 'http://localhost:15000').rstrip('/')
ART = os.environ.get('ART_DIR', os.path.join(
    PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int2088_blocks'))
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
DARK_KEY = 'iatp:theme:v1:mode'
USER = '接线测试_admin'
PASS = 'JieXianTest@2026'

TASK_ID = 402
EMPTY_TASK_ID = 399
# 单轮接管（第1轮+整体）；多次打断 7 轮；一次打断-切换话题（2 轮，rounds 数组形态）
SINGLE_CASE_ID = '7bac162b-275d-4567-b924-954736dc3ce9'
SINGLE_FRAG = 'JG0006_单轮接管'
MULTI_CASE_ID = 'd8bdd5a6-666d-41ab-a366-6b9f3b27e564'
MULTI_FRAG = 'DD139'
ROUNDS_CASE_ID = '1b4f51a8-b622-497c-a7b7-f84cca6a17c4'
ROUNDS_FRAG = 'DD061'

RESULT = []


def check(name, ok, detail=''):
    RESULT.append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:1500]})
    print(('[PASS] ' if ok else '[FAIL] ') + name + (' | ' + str(detail)[:400] if detail else ''))
    return ok


def api_get(path, token):
    import urllib.request
    req = urllib.request.Request(API + '/api/v1' + path, headers={'Authorization': 'Bearer ' + token})
    with urllib.request.urlopen(req, timeout=180) as r:
        j = json.loads(r.read().decode('utf-8'))
    return j.get('data', j)


def login_api():
    import base64
    import urllib.parse
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    key = json.loads(urllib.request.urlopen(API + '/api/v1/auth/login/encryption-key', timeout=30).read())
    d = key.get('data', key) if isinstance(key, dict) else key
    if d.get('enabled'):
        pub = serialization.load_pem_public_key(d['public_key'].encode())
        ct = pub.encrypt(PASS.encode(), padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
        body = urllib.parse.urlencode({
            'username': USER, 'password_encrypted': base64.b64encode(ct).decode(), 'encryption_key_id': d['kid']}).encode()
    else:
        body = urllib.parse.urlencode({'username': USER, 'password': PASS}).encode()
    req = urllib.request.Request(API + '/api/v1/auth/login', data=body, method='POST')
    req.add_header('Content-Type', 'application/x-www-form-urlencoded')
    j = json.loads(urllib.request.urlopen(req, timeout=60).read())
    return j['access_token']


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
    opts.add_argument('--window-size=1920,1400')
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


def body_text(drv):
    return drv.execute_script('return document.body.textContent || ""') or ''


def wait_text(drv, text, timeout=90):
    WebDriverWait(drv, timeout).until(lambda d: text in body_text(d))


def js_click(drv, el, wait=0.8):
    drv.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", el)
    time.sleep(wait)


def shot(drv, name):
    os.makedirs(ART, exist_ok=True)
    p = os.path.join(ART, name + '.png')
    drv.save_screenshot(p)
    print('shot:', p)
    return p


def login(drv):
    goto(drv, '/login', wait=3)
    if not drv.find_elements(By.XPATH, "//input[@name='username']"):
        goto(drv, '/tasks/%d' % TASK_ID, wait=3)
    if drv.find_elements(By.XPATH, "//input[@name='username']"):
        drv.find_element(By.XPATH, "//input[@name='username']").send_keys(USER)
        drv.find_element(By.XPATH, "//input[@name='password']").send_keys(PASS)
        btn = drv.find_element(By.XPATH, "//button[@type='submit']")
        drv.execute_script('arguments[0].click()', btn)
        time.sleep(5)
        if '/login' in drv.current_url:
            raise RuntimeError('登录失败，仍在 /login: ' + body_text(drv)[:200])


def open_case_dialog(drv, frag, attempt=1):
    goto(drv, '/tasks/%d' % TASK_ID, wait=4)
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
            By.XPATH, "//button[starts-with(@title,'查看用例详情：')][contains(@title,'%s')]" % frag)
    )
    js_click(drv, btn, 1.0)
    WebDriverWait(drv, 60).until(
        lambda d: d.find_element(By.CSS_SELECTOR, '[data-slot="case-detail-dialog"]'))
    try:
        wait_text(drv, '执行结果与指标', 90)
    except Exception:
        if attempt <= 2:
            print('RETRY 用例详情接口超时')
            drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            return open_case_dialog(drv, frag, attempt + 1)
        raise
    time.sleep(1.2)


def close_dialog(drv):
    try:
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(1.0)
    except Exception:
        pass


def click_round_tab(drv, label):
    btn = WebDriverWait(drv, 30).until(
        lambda d: d.find_element(By.XPATH,
            "//*[@data-slot='case-detail-dialog']//*[@aria-label='轮次切换']//*[@role='tab'][normalize-space(.)='%s']" % label)
    )
    js_click(drv, btn, 1.0)


COLLECT_JS = r"""
const dlg = document.querySelector('[data-slot="case-detail-dialog"]');
if (!dlg) return {error:'no dialog'};
const txt = dlg.textContent || '';
const roundTabList = dlg.querySelector('[aria-label="轮次切换"]');
const roundTabs = roundTabList ? [...roundTabList.querySelectorAll('[role="tab"]')].map(b => ({
  label: (b.textContent||'').trim(), selected: b.getAttribute('aria-selected') === 'true' })) : [];
const pLabel = label => [...dlg.querySelectorAll('p')].find(p => (p.textContent||'').trim() === label);
const sectionByP = label => { const p = pLabel(label); return p ? p.parentElement : null; };
// 评分指标表
const metricSection = sectionByP('评分指标');
let metric = { present: !!metricSection, heads: [], rows: [] };
if (metricSection) {
  const table = metricSection.querySelector('table');
  if (table) {
    metric.heads = [...table.querySelectorAll('thead th')].map(t => (t.textContent||'').trim());
    metric.rows = [...table.querySelectorAll('tbody tr')].map(tr =>
      [...tr.querySelectorAll('td')].map(td => (td.textContent||'').trim()));
  }
}
// 评估结果维度 tab
const evalTabList = dlg.querySelector('[aria-label="评估维度切换"]');
const evalTabs = evalTabList ? [...evalTabList.querySelectorAll('[role="tab"]')].map(b => (b.textContent||'').trim()) : [];
// 多轮对话结果
const mrSection = [...dlg.querySelectorAll('p')].find(p => /^多轮对话结果 \(\d+ 轮\)$/.test((p.textContent||'').trim()));
const multiRoundText = mrSection ? (mrSection.parentElement.textContent||'').trim().slice(0, 1200) : null;
const sections = {};
for (const lbl of ['参考数据','用例参数','评估结果','设备/API 执行结果','时间轴对比','音频时间轴','结果音频','执行结果音频']) {
  const s = sectionByP(lbl);
  sections[lbl] = s ? (s.textContent||'').trim().slice(0, 1000) : null;
}
return {
  dialogText: txt.slice(0, 6000),
  roundTabs,
  metric,
  evalTabs,
  multiRoundText,
  sections,
  hasRoundTabList: !!roundTabList,
};
"""


def collect(drv):
    return drv.execute_script(COLLECT_JS) or {}


def js_str(value):
    if value is None:
        return '—'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def expected_tabs_rows(task_id, case_id, token):
    """按接口原文算期望轮次 Tab 与每 Tab 指标行（verify_int1688 同口径，适配新表头）。"""
    detail = api_get('/tasks/%d/cases/%s/detail' % (task_id, case_id), token)
    results = api_get('/tasks/%d/cases/%s/results' % (task_id, case_id), token)
    devices = detail.get('devices') or []
    configured = [c['name'] for c in (detail.get('metric_configs') or [])]
    points = {}
    for row in results.get('results') or []:
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
    audio_rounds = [a.get('round_number') for a in (detail.get('algorithm_results') or [])
                    if a.get('param_type') == 'audio_file' and a.get('round_number') is not None]
    audio_rounds += [a.get('roundNumber') for a in (detail.get('audio_list') or []) if a.get('roundNumber') is not None]

    def rows_for(accept):
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
        tabs.append({'label': '指标', 'kind': 'all', 'round': None, 'rows': rows_for(lambda r: True)})
    else:
        rounds = sorted({r for _, r in all_points if r is not None} | set(audio_rounds))
        for rnd in rounds:
            tabs.append({'label': '第%d轮' % rnd, 'kind': 'round', 'round': rnd, 'rows': rows_for(lambda r, _r=rnd: r == _r)})
        overall_values = [value for bucket in points.values() for key, value in bucket.items() if key[1] is None]
        if any(v not in (None, '') for v in overall_values):
            tabs.append({'label': '整体', 'kind': 'overall', 'round': None, 'rows': rows_for(lambda r: r is None)})
    return detail, results, tabs


def tab_has_data(tab):
    return any(value not in ('', '—') for row in tab['rows'] for value in row['values'].values())


def has_rounds_array(detail):
    for r in (detail.get('algorithm_results') or []):
        if r.get('param_code') != 'rounds':
            continue
        v = r.get('value')
        if isinstance(v, list):
            return True
        if isinstance(v, dict) and isinstance((v or {}).get('rounds'), list):
            return True
    return False


def verify_blocks(drv, tag, detail, results, tabs, expect_multi_round, expect_timeline_empty, expect_input_audio):
    """核对 INT-2088 全块呈现。"""
    data = collect(drv)
    dtext = data.get('dialogText', '')
    tabs_ui = [t['label'] for t in data.get('roundTabs', [])]
    want_tabs = [t['label'] for t in tabs]
    # 单轮「指标」Tab 不渲染 Tab 栏（roundTabs.length<=1 口径）
    if len(want_tabs) <= 1:
        check('%s：单轮不渲染轮次 Tab 栏' % tag, not data.get('hasRoundTabList'),
              {'want': want_tabs, 'got': tabs_ui})
    else:
        check('%s：轮次 Tab = %s（单轴）' % (tag, want_tabs), tabs_ui == want_tabs,
              {'want': want_tabs, 'got': tabs_ui})

    metric = data.get('metric') or {}
    devices = detail.get('devices') or []
    if devices:
        check('%s：评分指标表存在' % tag, metric.get('present'), '')
        heads = metric.get('heads') or []
        check('%s：表头首列=指标名称，设备列=%s' % (tag, devices),
              len(heads) >= 1 and heads[0] == '指标名称' and all(any(d in h for h in heads[1:]) for d in devices),
              heads)
        first = next((t for t in tabs if tab_has_data(t)), tabs[0])
        sel = [t['label'] for t in data.get('roundTabs', []) if t.get('selected')]
        check('%s：默认选中第一个有数据 Tab「%s」' % (tag, first['label']),
              (not sel and first['label'] == '指标') or any(t == first['label'] for t in sel),
              {'sel': sel, 'want': first['label']})
        _check_metric_rows(tag, data, first, devices)
        if len(tabs) > 1:
            last = tabs[-1]
            click_round_tab(drv, last['label'])
            data2 = collect(drv)
            _check_metric_rows(tag + '·切' + last['label'], data2, last, devices)
            sel2 = [t['label'] for t in data2.get('roundTabs', []) if t.get('selected')]
            check('%s：切 Tab 后轮次轴选中「%s」' % (tag, last['label']), sel2 == [last['label']],
                  data2.get('roundTabs'))
            return data2
    else:
        check('%s：无设备列（API/voice_llm）不渲染评分指标表' % tag,
              not metric.get('present'), metric.get('heads'))

    # 用例参数：后端无 case_params → 「暂无数据」空态
    cp = data.get('sections', {}).get('用例参数')
    check('%s：用例参数块=「暂无数据」空态（后端无 case_params 数据源）' % tag,
          cp is not None and '暂无数据' in cp, cp)

    # 参考数据：referenceParams 空 → 块不渲染
    ref = data.get('sections', {}).get('参考数据')
    has_ref = bool(detail.get('reference_params'))
    check('%s：参考数据块%s（reference_params=%s）' % (tag, '渲染' if has_ref else '不渲染', has_ref),
          (ref is not None) == has_ref, {'has_ref': has_ref, 'block': bool(ref)})

    # 评估结果：维度归属字段存在时渲染
    ev = data.get('sections', {}).get('评估结果')
    has_dim = any(r.get('dimension_name') for r in (detail.get('algorithm_results') or []))
    if has_dim:
        check('%s：评估结果块渲染（有维度归属字段）' % tag, ev is not None and '评估结果' in ev, ev[:200])
    else:
        check('%s：无维度归属字段 → 评估结果不渲染' % tag, ev is None, '')

    # 设备/API 执行结果：有 results 行 → 渲染状态行
    dev = data.get('sections', {}).get('设备/API 执行结果')
    has_results = len((results.get('results') or [])) > 0
    if has_results:
        check('%s：设备/API 执行结果块渲染（/results %d 行）' % (tag, len(results.get('results') or [])),
              dev is not None and '设备/API 执行结果' in dev, (dev or '')[:150])
    else:
        check('%s：无 /results → 设备/API 执行结果块不渲染' % tag, dev is None, '')

    # 时间轴对比：真实库 turn_eval_* 为 dict 嵌套 → hasTimeline 不触发 → 块不渲染
    tl = data.get('sections', {}).get('时间轴对比')
    check('%s：时间轴对比块%s（真实库 json 嵌套无 speaker，判据不触发）' % (tag, '渲染' if not expect_timeline_empty else '空态/不渲染'),
          (tl is not None) == (not expect_timeline_empty), {'block': bool(tl)})

    # 音频时间轴：audio_list 有输入音频 → 渲染
    at = data.get('sections', {}).get('音频时间轴')
    check('%s：音频时间轴块%s（audio_list=%d 条）' % (tag, '渲染' if expect_input_audio else '不渲染', len(detail.get('audio_list') or [])),
          (at is not None) == bool(expect_input_audio), at)

    # 结果音频：result_audios 空 → 块不渲染
    ra = data.get('sections', {}).get('结果音频')
    has_ra = bool(detail.get('result_audios'))
    check('%s：结果音频块%s（result_audios=%s）' % (tag, '渲染' if has_ra else '不渲染', has_ra),
          (ra is not None) == has_ra, {'has_ra': has_ra, 'block': bool(ra)})

    # 多轮对话结果
    mr = data.get('multiRoundText')
    if expect_multi_round:
        check('%s：多轮对话结果渲染' % tag, mr is not None and '多轮对话结果' in mr, (mr or '')[:120])
    else:
        check('%s：多轮对话结果不渲染' % tag, mr is None, '')

    return data


def _check_metric_rows(tag, data, tab_expected, devices):
    rows = data.get('metric', {}).get('rows') or []
    want_rows = tab_expected['rows']
    if not want_rows:
        placeholder = (not rows) or (len(rows) == 1 and rows[0] and rows[0][0] == '暂无指标数据')
        check('%s：本轮无指标 → 「暂无指标数据」' % tag, placeholder, {'rows': rows})
        return
    check('%s：指标行数 = %d（行=指标）' % (tag, len(want_rows)), len(rows) == len(want_rows),
          {'want': len(want_rows), 'got': len(rows), 'ui': rows})
    ui_by_dim = {}
    for row in rows:
        if row and row[0]:
            ui_by_dim[row[0]] = row[1:]
    for exp in want_rows:
        ui_vals = ui_by_dim.get(exp['dimension'])
        want_vals = [exp['values'].get(dev, '—') for dev in devices]
        check('%s：指标「%s」各设备值' % (tag, exp['dimension']),
              ui_vals == want_vals, {'want': want_vals, 'got': ui_vals})


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
    return [(url.split('?')[0][-75:], status) for url, status in netlog if needle in url]


def main():
    token = login_api()
    print('API token ok')
    single_detail, single_results, single_tabs = expected_tabs_rows(TASK_ID, SINGLE_CASE_ID, token)
    multi_detail, multi_results, multi_tabs = expected_tabs_rows(TASK_ID, MULTI_CASE_ID, token)
    rounds_detail, rounds_results, rounds_tabs = expected_tabs_rows(TASK_ID, ROUNDS_CASE_ID, token)
    print('JG0006 tabs:', [t['label'] for t in single_tabs])
    print('DD139 tabs:', [t['label'] for t in multi_tabs])
    print('DD061 tabs:', [t['label'] for t in rounds_tabs])

    evidence = {'base': BASE, 'checks': [], 'shots': {}}
    drv = build_driver()
    try:
        login(drv)
        print('login ok, url=', drv.current_url)
        # ---------- 单轮 JG0006（浅色） ----------
        open_case_dialog(drv, SINGLE_FRAG)
        expect_mr = has_rounds_array(single_detail)
        verify_blocks(drv, '单轮JG0006', single_detail, single_results, single_tabs,
                      expect_multi_round=expect_mr, expect_timeline_empty=True,
                      expect_input_audio=len(single_detail.get('audio_list') or []) > 0)
        evidence['shots']['single_light'] = shot(drv, 'INT2088_JG0006_single_light')
        netlog = network_responses(drv)
        evidence['network'] = {
            'detail': network_status(netlog, '/cases/%s/detail' % SINGLE_CASE_ID),
            'results': network_status(netlog, '/cases/%s/results' % SINGLE_CASE_ID),
        }
        check('Network：单轮 GET /detail → 200', any(c == 200 for _, c in evidence['network']['detail']), evidence['network']['detail'])
        check('Network：单轮 GET /results → 200', any(c == 200 for _, c in evidence['network']['results']), evidence['network']['results'])
        close_dialog(drv)

        # ---------- 多轮 DD139（浅色） ----------
        open_case_dialog(drv, MULTI_FRAG)
        expect_mr139 = has_rounds_array(multi_detail)
        verify_blocks(drv, '多轮DD139', multi_detail, multi_results, multi_tabs,
                      expect_multi_round=expect_mr139, expect_timeline_empty=True,
                      expect_input_audio=len(multi_detail.get('audio_list') or []) > 0)
        click_round_tab(drv, '第1轮')
        evidence['shots']['multi_round1_light'] = shot(drv, 'INT2088_DD139_round1_light')
        click_round_tab(drv, '第7轮')
        evidence['shots']['multi_round7_light'] = shot(drv, 'INT2088_DD139_round7_light')
        netlog_multi = network_responses(drv)
        evidence['network_multi'] = {
            'detail': network_status(netlog_multi, '/cases/%s/detail' % MULTI_CASE_ID),
            'results': network_status(netlog_multi, '/cases/%s/results' % MULTI_CASE_ID),
        }
        check('Network：多轮 GET /detail → 200', any(c == 200 for _, c in evidence['network_multi']['detail']), evidence['network_multi']['detail'])
        check('Network：多轮 GET /results → 200', any(c == 200 for _, c in evidence['network_multi']['results']), evidence['network_multi']['results'])
        close_dialog(drv)

        # ---------- DD061（rounds 数组形态，多轮对话结果） ----------
        open_case_dialog(drv, ROUNDS_FRAG)
        expect_mr061 = has_rounds_array(rounds_detail)
        verify_blocks(drv, 'DD061-rounds', rounds_detail, rounds_results, rounds_tabs,
                      expect_multi_round=expect_mr061, expect_timeline_empty=True,
                      expect_input_audio=len(rounds_detail.get('audio_list') or []) > 0)
        evidence['shots']['dd061_light'] = shot(drv, 'INT2088_DD061_rounds_light')
        close_dialog(drv)

        # ---------- 深色（同源 reload） ----------
        drv.execute_script("localStorage.setItem(arguments[0], 'dark')", DARK_KEY)
        open_case_dialog(drv, SINGLE_FRAG)
        dark_html = drv.execute_script('return document.documentElement.className')
        check('深色主题已生效', 'dark' in (dark_html or ''), dark_html)
        verify_blocks(drv, '单轮JG0006·深色', single_detail, single_results, single_tabs,
                      expect_multi_round=expect_mr, expect_timeline_empty=True,
                      expect_input_audio=len(single_detail.get('audio_list') or []) > 0)
        evidence['shots']['single_dark'] = shot(drv, 'INT2088_JG0006_single_dark')
        open_case_dialog(drv, MULTI_FRAG)
        click_round_tab(drv, '第7轮')
        evidence['shots']['multi_round7_dark'] = shot(drv, 'INT2088_DD139_round7_dark')
        drv.execute_script("localStorage.setItem(arguments[0], 'light')", DARK_KEY)
        time.sleep(0.5)

        # ---------- 空态（任务 399） ----------
        goto(drv, '/tasks/%d' % EMPTY_TASK_ID, wait=4)
        try:
            wait_text(drv, '关联用例', 180)
        except Exception:
            btn = drv.find_elements(By.XPATH, "//button[normalize-space(.)='重试']")
            if btn:
                js_click(drv, btn[0], 1.5)
            wait_text(drv, '关联用例', 180)
        btns = WebDriverWait(drv, 60).until(
            lambda d: d.find_elements(By.XPATH, "//button[starts-with(@title,'查看用例详情：')]"))
        js_click(drv, btns[0], 1.0)
        WebDriverWait(drv, 60).until(
            lambda d: d.find_element(By.CSS_SELECTOR, '[data-slot="case-detail-dialog"]'))
        wait_text(drv, '执行结果与指标', 60)
        time.sleep(1.0)
        data = collect(drv)
        dtext = data.get('dialogText', '')
        check('空态：弹窗打开且含「执行结果与指标」', '执行结果与指标' in dtext, dtext[:120])
        check('空态：显示「暂无执行结果」（不回归）', '暂无执行结果' in dtext, dtext[:200])
        evidence['shots']['empty'] = shot(drv, 'INT2088_empty_task%d' % EMPTY_TASK_ID)

        # console SEVERE
        severe = [e for e in drv.get_log('browser') if (e.get('level') or '').upper() == 'SEVERE']
        evidence['console_severe'] = [s.get('message', '')[:300] for s in severe]
        check('console 无 SEVERE', len(severe) == 0, evidence['console_severe'])
    finally:
        try:
            drv.quit()
        except Exception:
            pass

    failed = [r for r in RESULT if not r['ok']]
    evidence['checks'] = RESULT
    evidence['failed'] = len(failed)
    os.makedirs(ART, exist_ok=True)
    with open(os.path.join(ART, 'evidence_int2088.json'), 'w', encoding='utf-8') as f:
        json.dump(evidence, f, ensure_ascii=False, indent=2)
    print('\n==== %d checks, %d failed ====' % (len(RESULT), len(failed)))
    for r in failed:
        print('[FAIL]', r['name'], '|', r['detail'])
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
