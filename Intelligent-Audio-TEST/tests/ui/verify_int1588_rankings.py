# -*- coding: utf-8 -*-
"""INT-1588 排行榜列表态补测（docker 真实库栈 15000 / React 15173）。

背景：/rankings 真实库排行 ReadModel 因源报告全软删恒空（INT-1218 可见性过滤），
INT-1494 走查时筛选行 / 榜单组卡 / 指标图 / 视图切换 未覆盖。规划师裁定用本 run
自建夹具（benchmark_rankings id 990001~990005，source_report_id → 未软删的真实报告
564）补测列表态，run 结束前按 id SQL 删除。

覆盖（对应卡面 1~3 项）：
  1. 筛选行选项条数 vs 接口：测试集 / 指标（/metric-mappings）/ 数据来源 / 主体联想
     （/ranking/subjects）——逐个与接口返回条数对照；并实测指标筛选真实下发 metricCode。
  2. 榜单组卡：标题「{metric_name} · {scenario_key}」、方向徽章、组内主体数、主值与
     score100、名次、来源/主体类型徽章、指标条形图（VChart canvas）；无 mock 残留。
  3. 列表 ↔ 表格视图切换（含表格列）、主体搜索防抖 300ms（URL 写入时机 + 子串过滤）、
     重置。
  4. 「立即计算」只验取消路径：ConfirmDialog 打开 → 取消 → Network 无 POST compute。

证据：浅色/深色整页截图 + 关键交互截图 + Network 请求清单，落
tests/ui/artifacts/int1588_rankings/。

用法：
  $env:REACT_BASE='http://localhost:15173'
  python tests/ui/verify_int1588_rankings.py
"""
import base64
import json
import os
import sys
import time
from urllib.parse import unquote

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

sys.stdout.reconfigure(encoding='utf-8')
os.environ.setdefault('SE_OFFLINE', 'true')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1588_rankings')

BASE = os.environ.get('REACT_BASE', 'http://localhost:15173')
API = os.environ.get('REACT_API', BASE + '/api/v1')
HEALTH = os.environ.get('BACKEND_HEALTH', 'http://127.0.0.1:15000/health')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

FIXTURE_IDS = list(range(990001, 990006))
FIXTURE_SUBJECTS = ['接线测试_主体A', '接线测试_主体B', '接线测试_主体C']

RESULTS = []


def check(cid, ok, detail=''):
    RESULTS.append({'id': cid, 'ok': bool(ok), 'detail': detail})
    print(('  [PASS] ' if ok else '  [FAIL] ') + cid + ((' — ' + detail) if detail else ''))
    return ok


def health(tag):
    r = requests.get(HEALTH, timeout=20)
    body = r.json()
    ok = body.get('database') == 'intelligent_audio_test' and body.get('status') == 'ok'
    print(f'[health:{tag}] {json.dumps(body, ensure_ascii=False)}')
    return ok, body


def api_ranking(params=None):
    r = requests.get(API + '/benchmarks/ranking', params=params or {}, timeout=60)
    r.raise_for_status()
    return r.json()['data']


def api_subjects():
    r = requests.get(API + '/benchmarks/ranking/subjects', timeout=60)
    r.raise_for_status()
    return r.json()['data']['items']


def api_mappings():
    r = requests.get(API + '/benchmarks/metric-mappings', params={'activeOnly': 'true'}, timeout=60)
    r.raise_for_status()
    return r.json()['data']['items']


# ---------------------------------------------------------------------------
# driver / 页面工具
# ---------------------------------------------------------------------------

def make_driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1200')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
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
    print(f'[driver] chrome_major={chrome_major} chromedriver={drv_path or "(Selenium Manager)"}')
    service = Service(executable_path=drv_path) if drv_path else Service()
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(90)
    drv.set_script_timeout(60)
    return drv


def body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 40).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.2)


def wait_text(drv, text, timeout=30):
    WebDriverWait(drv, timeout).until(lambda d: text in body_text(drv))


def wait_text_gone(drv, text, timeout=20):
    WebDriverWait(drv, timeout).until(lambda d: text not in body_text(drv))


def js_click(drv, el):
    drv.execute_script('arguments[0].click();', el)


def escape(drv):
    ActionChains(drv).send_keys(Keys.ESCAPE).perform()
    time.sleep(0.3)


def open_select(drv, aria):
    """打开 base-ui Select（JS click 规避动画拦截），返回**当前可见**选项文本列表。

    注意：base-ui 关闭后的弹窗仍残留在 DOM（data-closed），必须按 is_displayed 过滤，
    否则会把上一个 Select 的选项算进来。
    """
    escape(drv)
    trig = drv.find_element(By.XPATH, f"//button[@aria-label='{aria}']")
    js_click(drv, trig)

    def visible_items(d):
        return [i for i in d.find_elements(By.CSS_SELECTOR, "[data-slot='select-item']")
                if i.is_displayed()]

    WebDriverWait(drv, 15).until(lambda d: len(visible_items(d)) > 0)
    time.sleep(0.35)
    return [i.text.strip() for i in visible_items(drv)]


def pick_option(drv, text):
    el = drv.find_element(
        By.XPATH, f"//*[@data-slot='select-item'][contains(normalize-space(.), '{text}')]")
    js_click(drv, el)
    time.sleep(0.8)


def query_values(url):
    """URL query → {key: value}（值已 unquote）；用于判定筛选是否清空。"""
    from urllib.parse import parse_qs, urlparse
    return {k: (v[0] if v else '') for k, v in parse_qs(urlparse(url).query, keep_blank_values=True).items()}


def shot_full(drv, name):
    drv.execute_script('window.scrollTo(0,0)')
    time.sleep(0.5)
    data = drv.execute_cdp_cmd(
        'Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': True})['data']
    path = os.path.join(ARTIFACTS, name + '.png')
    with open(path, 'wb') as f:
        f.write(base64.b64decode(data))
    print(f'[shot] {path}')
    return path


def shot_view(drv, name):
    path = os.path.join(ARTIFACTS, name + '.png')
    drv.save_screenshot(path)
    print(f'[shot] {path}')
    return path


def set_theme(drv, mode):
    if not drv.current_url.startswith(BASE):
        drv.get(BASE + '/')
        time.sleep(0.6)
    drv.execute_script(
        "localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", mode)


_PERF = []


def drain_perf(drv):
    """把 performance log 追加进 _PERF（get_log 会清空 Chrome 缓冲，必须边跑边攒）。

    返回本段起点索引，便于只看某一段交互的请求。
    """
    mark = len(_PERF)
    try:
        for entry in drv.get_log('performance'):
            try:
                _PERF.append(json.loads(entry.get('message', '{}')))
            except Exception:
                continue
    except Exception:
        pass
    return mark


def collect_network(events=None):
    """perf 事件 → [{method,url,status}]（Network.requestWillBeSent + responseReceived）"""
    reqs, statuses = {}, {}
    for ev in (events if events is not None else _PERF):
        msg = ev.get('message', {})
        method = msg.get('method')
        params = msg.get('params', {})
        if method == 'Network.requestWillBeSent':
            rid = params.get('requestId')
            reqs[rid] = (params['request'].get('method'), params['request'].get('url'), params.get('type'))
        elif method == 'Network.responseReceived':
            rid = params.get('requestId')
            statuses[rid] = params['response'].get('status')
    out = []
    for rid, (m, u, t) in reqs.items():
        if '/api/' in u:
            out.append({'method': m, 'url': u, 'status': statuses.get(rid), 'type': t})
    return out


# ---------------------------------------------------------------------------
# 检查分组
# ---------------------------------------------------------------------------

def step_render(drv, rows):
    """① 数据态渲染：组卡标题 / 方向徽章 / 组内主体数 / 主值 / 名次 / 徽章 / 指标图 / 无 mock。"""
    text = body_text(drv)
    groups = {}
    for row in rows:
        groups.setdefault((row['metric_code'], row['scenario_key']), []).append(row)

    check('1.1 组卡数量 = 接口分组数(%d)' % len(groups),
          len(drv.find_elements(By.XPATH, "//h2[contains(normalize-space(.), '接线测试_')]")) == len(groups),
          'DOM=%d 接口=%d' % (
              len(drv.find_elements(By.XPATH, "//h2[contains(normalize-space(.), '接线测试_')]")), len(groups)))

    for (code, scenario), grows in groups.items():
        title = f"{grows[0]['metric_name']} · {scenario}"
        check(f'1.2 组卡标题「{title}」', title in text)
        direction = '越低越好' if grows[0]['direction'] == 'lower_is_better' else '越高越好'
        check(f'1.3 方向徽章「{direction}」({code})', direction in text)
        check(f'1.4 组卡主体数 {grows[0]["total"]}',
              f"共 {grows[0]['total']} 个主体参与" in text,
              f"期望「共 {grows[0]['total']} 个主体参与」")
        # 名次 + 主体 + 主值
        for row in grows:
            subject = row['subject_name']
            check(f'1.5 榜单行 {subject} @ {code}', subject in text)
        check(f'1.6 名次标记 1.~{len(grows)}.', all(f'{i}.' in text for i in range(1, len(grows) + 1)))

    # 主值（formatCompactNumber + unit）
    check('1.7 主值 850ms（越低越好组头名）', '850ms' in text)
    check('1.8 主值 1.02Kms（紧凑格式 ≥1000）', '1.02Kms' in text)
    check('1.9 主值 0.85score/0.62score/0.41score',
          all(v in text for v in ('0.85score', '0.62score', '0.41score')))
    # score100 副值（deltaExternal 为空时回退显示）
    check('1.10 score100 副值 100 分/72 分/48 分/60 分',
          all(v in text for v in ('100 分', '72 分', '48 分', '60 分')))
    # 徽章组
    check('1.11 来源徽章「平台实测」', text.count('平台实测') >= 5, f"出现 {text.count('平台实测')} 次")
    check('1.12 主体类型徽章 App/闭源', 'App' in text and '闭源' in text)
    check('1.13 设备类型徽章 实体设备/HTTP API', '实体设备' in text and 'HTTP API' in text)
    check('1.14 版本徽章 v1', 'v1' in text)
    check('1.15 计算于角标 10-23 15:30', '10-23 15:30' in text)
    # 行尾「查看报告」链接（canReadReport，AUTH_MODE=off 全放行）
    report_links = drv.find_elements(By.XPATH, "//a[contains(normalize-space(.), '查看报告')]")
    check('1.16 行尾「查看报告」链接数 = 行数(%d)' % len(rows), len(report_links) == len(rows),
          f'DOM={len(report_links)}')
    # 指标条形图（VChart canvas）
    try:
        WebDriverWait(drv, 20).until(lambda d: len(d.find_elements(By.TAG_NAME, 'canvas')) >= len(groups))
        canvases = len(drv.find_elements(By.TAG_NAME, 'canvas'))
    except Exception:
        canvases = len(drv.find_elements(By.TAG_NAME, 'canvas'))
    check('1.17 指标条形图 canvas 数 ≥ 组卡数', canvases >= len(groups),
          f'canvas={canvases} 组卡={len(groups)} 暂无图表数据={"暂无图表数据" in text}')
    # mock 残留
    check('1.18 无 mock 残留（通用识别引擎 / 字错率 · 通用）',
          '通用识别引擎' not in text and '字错率 · 通用' not in text)
    # 页面上只出现夹具主体（真实库无其他可见主体）
    strays = [s for s in ('Default App', 'INT95R7-voice-llm-adapter')
              if s in text]
    check('1.19 可见主体仅夹具 3 个（无历史软删源报告行泄漏）', not strays, f'额外主体={strays}')


def step_filters(drv, rows):
    """② 筛选行选项条数与接口逐一对照 + 指标筛选真实下发。"""
    suites = sorted({r['benchmark_suite'] for r in rows})
    mappings = api_mappings()
    subjects = api_subjects()

    suite_opts = open_select(drv, '测试集')
    escape(drv)
    check('2.1 测试集选项 = 数据去重 suite(%d) + 全部测试集' % len(suites),
          len(suite_opts) == len(suites) + 1, f'DOM={suite_opts}')
    check('2.2 测试集选项内容', '全部测试集' in suite_opts and all(s in suite_opts for s in suites), str(suite_opts))

    metric_opts = open_select(drv, '指标')
    escape(drv)
    check('2.3 指标选项 = /metric-mappings 条数(%d) + 全部指标' % len(mappings),
          len(metric_opts) == len(mappings) + 1, f'DOM={len(metric_opts)} 接口={len(mappings)}')
    missing = [m['metric_name'] for m in mappings if m['metric_name'] not in metric_opts]
    check('2.4 指标选项与映射名称全量对照', not missing, f'缺失={missing[:5]}')

    source_opts = open_select(drv, '数据来源')
    escape(drv)
    check('2.5 数据来源选项 3 态', source_opts == ['全部来源', '平台实测', '外部基线'] or
          sorted(source_opts) == sorted(['全部来源', '平台实测', '外部基线']), str(source_opts))

    # 主体联想：输入「接线测试」→ 选项数 = /ranking/subjects 中匹配条数
    inp = drv.find_element(By.XPATH, "//input[@aria-label='搜索主体']")
    js_click(drv, inp)
    inp.send_keys('接线测试')
    time.sleep(1.2)
    expected = [s for s in subjects if '接线测试' in s][:8]
    opts = [li.text.strip() for li in drv.find_elements(By.XPATH, "//ul[@role='listbox']//li[@role='option']")]
    check('2.6 主体联想选项 = /ranking/subjects 匹配条数(%d)' % len(expected),
          sorted(opts) == sorted(expected), f'DOM={opts} 接口={expected}')
    shot_view(drv, '03_subject_suggestions')
    escape(drv)

    # 指标筛选真实下发（metricCode → 后端精确筛选 → 只剩该指标组卡）
    open_select(drv, '指标')
    pick_option(drv, '环境理解评分')
    time.sleep(1.5)
    url = unquote(drv.current_url)
    check('2.7 选指标后 URL 写入 metricCode', 'metricCode=ENV_UNDERSTAND_SCORE' in url, url)
    wait_text(drv, '接线测试_环境理解评分 · 接线测试_通用')
    text = body_text(drv)
    check('2.8 指标筛选后只剩环境理解评分组（平均回复时延消失）',
          '接线测试_环境理解评分' in text and '接线测试_平均回复时延' not in text)

    # 重置
    reset_btn = drv.find_element(By.XPATH, "//button[@aria-label='重置']")
    js_click(drv, reset_btn)
    time.sleep(1.5)
    url = unquote(drv.current_url)
    q = query_values(url)
    check('2.9 重置清空全部筛选值（category/suite/metricCode/source/subjectName 均为空）',
          all(q.get(k, '') == '' for k in ('category', 'suite', 'metricCode', 'source', 'subjectName')),
          str(q))
    text = body_text(drv)
    check('2.10 重置后两组建卡恢复',
          '接线测试_理解评分' in text or ('接线测试_环境理解评分' in text and '接线测试_平均回复时延' in text))
    check('2.11 重置后「重置」按钮消失',
          len(drv.find_elements(By.XPATH, "//button[@aria-label='重置']")) == 0)


def step_debounce(drv):
    """③ 主体搜索防抖 300ms：输入后 URL 不立即变，~300ms 后写入；子串过滤生效。"""
    inp = drv.find_element(By.XPATH, "//input[@aria-label='搜索主体']")
    js_click(drv, inp)
    # Ctrl+A + Delete（Selenium clear() 不触发 React onChange）
    ActionChains(drv).key_down(Keys.CONTROL).send_keys('a').key_up(Keys.CONTROL).send_keys(Keys.DELETE).perform()
    time.sleep(0.3)
    t0 = time.time()
    target = 'subjectName=接线测试_主体C'
    inp.send_keys('接线测试_主体C')
    immediate = unquote(drv.current_url)
    check('3.1 键入后立即不写选中值（防抖生效）', target not in immediate, immediate)
    deadline = t0 + 8
    while time.time() < deadline:
        if target in unquote(drv.current_url):
            break
        time.sleep(0.02)
    elapsed = time.time() - t0
    url = unquote(drv.current_url)
    check('3.2 防抖 ~300ms 后写入 subjectName', target in url,
          f'elapsed={elapsed:.2f}s url={url}')
    check('3.3 防抖时长 ≥ 0.25s', elapsed >= 0.25, f'elapsed={elapsed:.2f}s')
    time.sleep(1.5)
    text = body_text(drv)
    check('3.4 主体子串过滤生效（只剩主体C，主体A/B 消失）',
          '接线测试_主体C' in text and '接线测试_主体A' not in text and '接线测试_主体B' not in text)
    check('3.5 过滤后只剩环境理解评分组卡（平均回复时延无主体C）',
          '接线测试_环境理解评分' in text and '接线测试_平均回复时延' not in text)
    # 重置回全量
    js_click(drv, drv.find_element(By.XPATH, "//button[@aria-label='重置']"))
    time.sleep(1.5)
    text = body_text(drv)
    check('3.6 重置后恢复 3 主体 / 2 组卡',
          all(s in text for s in FIXTURE_SUBJECTS) and '接线测试_平均回复时延' in text)


def step_view_switch(drv, rows):
    """④ 列表 ↔ 表格视图切换（表格列全字段）+ 视图持久化前保持列表。"""
    wait_text(drv, '接线测试_主体A')
    heads = drv.find_elements(By.XPATH, "//button[normalize-space(.)='表格']")
    check('4.1 每张组卡都有 列表/表格 切换', len(heads) >= 2, f'表格按钮 {len(heads)} 个')
    js_click(drv, heads[0])
    time.sleep(1.5)
    text = body_text(drv)
    for col in ('名次', '主体', '主体类型', '来源', '版本', 'score100', '百分位', '与最佳差', '与中位差', '基线差', '计算于', '报告'):
        check(f'4.2 表格列「{col}」', col in text)
    regions = drv.find_elements(By.CSS_SELECTOR, "[role='region'][aria-label^='排行明细表']")
    check('4.3 表格 region aria-label', len(regions) == 2, f'region={len(regions)}')
    if regions:
        print('  [region] ' + regions[0].get_attribute('aria-label'))
    # 表格行数 = 夹具行数（每卡各表）
    trs = drv.find_elements(By.CSS_SELECTOR, "[role='region'][aria-label^='排行明细表'] tbody tr")
    check('4.4 表格行数 = 夹具行数(%d)' % len(rows), len(trs) == len(rows), f'DOM={len(trs)}')
    shot_full(drv, '05_table_view')
    # 切回列表
    lists = drv.find_elements(By.XPATH, "//button[normalize-space(.)='列表']")
    js_click(drv, lists[0])
    time.sleep(1.2)
    check('4.5 切回列表后表格列消失', '与中位差' not in body_text(drv))


def step_compute_cancel(drv, rows):
    """⑤ 立即计算：ConfirmDialog 打开 → 取消 → Network 无 POST compute。"""
    buttons = drv.find_elements(By.XPATH, "//button[contains(normalize-space(.), '立即计算')]")
    check('5.1 筛选行「立即计算」按钮存在', len(buttons) >= 1, f'按钮 {len(buttons)} 个')
    mark = drain_perf(drv)  # 只观察本次交互产生的请求
    js_click(drv, buttons[0])
    WebDriverWait(drv, 15).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, "[role='alertdialog']")) > 0)
    time.sleep(0.8)
    dialog = [d for d in drv.find_elements(By.CSS_SELECTOR, "[role='alertdialog']") if d.is_displayed()]
    dtext = dialog[0].text if dialog else ''
    check('5.2 弹窗标题「重新计算排行？」', '重新计算排行？' in dtext, dtext[:80])
    check('5.3 弹窗描述含全量重算说明', '将合并平台实测与外部基线全量重算' in dtext)
    check('5.4 弹窗按钮 取消 / 开始计算', '取消' in dtext and '开始计算' in dtext)
    shot_view(drv, '06_compute_dialog')
    cancel = dialog[0].find_element(By.XPATH, ".//button[normalize-space(.)='取消']")
    js_click(drv, cancel)
    WebDriverWait(drv, 15).until(
        lambda d: len([x for x in d.find_elements(By.CSS_SELECTOR, "[role='alertdialog']") if x.is_displayed()]) == 0)
    time.sleep(1.2)
    check('5.5 取消后弹窗关闭', '重新计算排行？' not in body_text(drv))
    drain_perf(drv)
    net = collect_network(_PERF[mark:])
    posts = [n for n in net if n['method'] == 'POST' and 'benchmarks/ranking/compute' in n['url']]
    check('5.6 取消路径无 POST /benchmarks/ranking/compute（本段 %d 条 /api 请求）' % len(net),
          not posts, str(posts))
    text = body_text(drv)
    check('5.7 取消后榜单数据不变（5 行仍在）',
          all(s in text for s in FIXTURE_SUBJECTS) and '接线测试_环境理解评分' in text)


def main():
    os.makedirs(ARTIFACTS, exist_ok=True)
    print('=== INT-1588 排行榜列表态补测 ===')
    print(f'BASE={BASE}  API={API}  HEALTH={HEALTH}')

    ok1, body1 = health('run-start-resume')
    if not ok1:
        print('!! 后端未连真实库，终止')
        return 2

    rows = api_ranking()['items']
    subjects = api_subjects()
    mappings = api_mappings()
    print(f'[api] ranking rows={len(rows)} subjects={len(subjects)} mappings={len(mappings)}')
    ids = sorted(r['id'] for r in rows)
    if ids != FIXTURE_IDS:
        print(f'!! 排行接口返回行 id {ids} 与夹具 {FIXTURE_IDS} 不一致，终止')
        return 2

    drv = make_driver()
    try:
        # 主题/本地态归零，确保从列表视图 + 浅色开始
        goto(drv, '/rankings')
        drv.execute_script(
            "localStorage.removeItem('iatp:rankings:v1:view');"
            "localStorage.setItem('iatp:theme:v1:mode','light');")
        time.sleep(2.0)  # 等首访请求落地，避免被二次导航打断
        goto(drv, '/rankings')
        wait_text(drv, '接线测试_主体A')

        print('\n--- ① 数据态渲染 ---')
        step_render(drv, rows)

        # health ②：每批截图前
        ok2, body2 = health('before-screenshots')

        print('\n--- ② 筛选行选项与接口对照 ---')
        step_filters(drv, rows)

        print('\n--- ③ 主体搜索防抖 / 过滤 / 重置 ---')
        step_debounce(drv)

        print('\n--- ④ 列表 ↔ 表格视图切换 ---')
        step_view_switch(drv, rows)

        print('\n--- ⑤ 立即计算取消路径 ---')
        step_compute_cancel(drv, rows)

        # 截图：浅色整页（重置后全量态）
        wait_text(drv, '接线测试_主体A')
        time.sleep(1.0)
        shot_full(drv, '01_light_list')

        # 指标下拉选项截图（19 项）
        open_select(drv, '指标')
        shot_view(drv, '02_metric_options')
        escape(drv)

        # 深色整页
        set_theme(drv, 'dark')
        goto(drv, '/rankings')
        wait_text(drv, '接线测试_主体A')
        time.sleep(1.5)
        cls = drv.find_element(By.TAG_NAME, 'html').get_attribute('class') or ''
        print(f'[dark] html class = {cls}')
        check('6.1 深色主题生效', 'dark' in cls, cls)
        text = body_text(drv)
        check('6.2 深色下榜单与指标图渲染',
              all(s in text for s in FIXTURE_SUBJECTS) and '接线测试_平均回复时延' in text)
        shot_full(drv, '07_dark_list')
        set_theme(drv, 'light')

        # Network 证据（整段会话：页面加载 + 筛选 + 重置 + 弹窗交互）
        drain_perf(drv)
        api_calls = [n for n in collect_network() if '/api/v1/benchmarks' in n['url'] or '/api/v1/algorithm' in n['url']]
        with open(os.path.join(ARTIFACTS, 'network.json'), 'w', encoding='utf-8') as f:
            json.dump(api_calls, f, ensure_ascii=False, indent=2)
        with open(os.path.join(ARTIFACTS, 'network.log'), 'w', encoding='utf-8') as f:
            for n in api_calls:
                f.write(f"{n['method']:5s} {n['status']} {n['url']}\n")
        print(f'[network] {len(api_calls)} 条 /api/v1 请求')
        for n in api_calls:
            print(f"  {n['method']:5s} {n['status']} {n['url']}")

        ranking_calls = [n for n in api_calls
                         if n['method'] == 'GET' and '/benchmarks/ranking' in n['url']
                         and '/ranking/subjects' not in n['url']]
        check('7.1 Network 有 GET /benchmarks/ranking（真实接口 200）',
              any(n['status'] == 200 for n in ranking_calls),
              f'{len(ranking_calls)} 次，状态 {[n["status"] for n in ranking_calls]}')
        check('7.2 Network 有 GET /benchmarks/metric-mappings',
              any('benchmarks/metric-mappings' in n['url'] for n in api_calls))
        check('7.3 Network 有 GET /benchmarks/ranking/subjects（主体联想真实请求）',
              any('benchmarks/ranking/subjects' in n['url'] for n in api_calls),
              '\n'.join(n['url'] for n in api_calls))
        check('7.4 Network 有带 metricCode 的排行查询（筛选真实下发后端）',
              any('metricCode=ENV_UNDERSTAND_SCORE' in n['url'] for n in api_calls))
        # status=None = 记录被首访后的二次导航打断、未观测到响应（脚本行为），只对 4xx/5xx 判失败
        bad = [n for n in api_calls if n['status'] is not None and n['status'] >= 400]
        check('7.5 无 4xx/5xx、无 mock 兜底（status=None 仅首访被打断的请求）',
              not bad, str([(n['url'][-70:], n['status']) for n in bad]))
    finally:
        try:
            drv.quit()
        except Exception:
            pass

    ok3, body3 = health('before-delivery')

    summary = {
        'total': len(RESULTS),
        'passed': sum(1 for r in RESULTS if r['ok']),
        'failed': [r for r in RESULTS if not r['ok']],
        'health': {'run_start': body1, 'before_screenshots': body2, 'before_delivery': body3},
        'api': {'rows': len(rows), 'subjects': subjects, 'mappings': len(mappings)},
    }
    with open(os.path.join(ARTIFACTS, 'summary.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print('\n=== 汇总：%d/%d 通过 ===' % (summary['passed'], summary['total']))
    for r in summary['failed']:
        print('  FAIL ' + r['id'] + ' — ' + r['detail'])
    return 0 if not summary['failed'] else 1


if __name__ == '__main__':
    sys.exit(main())
