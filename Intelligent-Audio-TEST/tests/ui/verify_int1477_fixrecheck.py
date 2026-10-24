# -*- coding: utf-8 -*-
"""INT-1477 复走·React·用例域：INT-1642 / INT-1658 合入后三处修复复验（docker 真实栈）。

覆盖（对应 INT-1477 第五轮交付评论的「待补三处」）：
  A. 页面级「新建分组」入口（INT-1658 e4c493c10）—— 工具栏按钮可达、POST /groups、GET /groups 回读；
  B. 导出弹窗真实接线（INT-1642 492fe09b4/f1ab6585e）—— 已选/筛选两范围真实 POST /testcases/export，
     下载文件落盘非空可解析，条数与选择一致；
  C. 批量评估维度真实轮次（INT-1642）—— 选中用例真实轮次=2（旧 MOCK_ROUND_COUNT=4），
     指定轮次网格与逐轮 Tab 均只出第 1/2 轮。

数据卫生：只用「接线测试_INT1477_FIX_」前缀自建分组/用例，结束前删除（软删→purge）。
"""
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15173')
API = 'http://127.0.0.1:15000/api/v1'
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ART = os.path.join(ROOT, 'tests', 'ui', 'artifacts', 'int1477_fix')
DL = os.path.join(ART, 'downloads')
os.makedirs(ART, exist_ok=True)
shutil.rmtree(DL, ignore_errors=True)
os.makedirs(DL, exist_ok=True)

TS = time.strftime('%m%d%H%M%S')
PREFIX = '接线测试_INT1477_FIX_'
GROUP_NAME = PREFIX + TS
EVID = []
STATE = {'group_id': None, 'case_ids': [], 'bundle': None}


def log(*a):
    print(*a, flush=True)


# ---------- 后端直连（夹具 / 回读 / 清理） ----------
def api(method, path, body=None, timeout=90):
    data = None
    headers = {'Accept': 'application/json'}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode('utf-8')
        headers['Content-Type'] = 'application/json; charset=utf-8'
    req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode('utf-8')
            try:
                return r.status, json.loads(raw)
            except Exception:
                return r.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw


def check_health(tag):
    try:
        with urllib.request.urlopen('http://127.0.0.1:15000/health', timeout=30) as r:
            d = json.loads(r.read().decode('utf-8'))
    except Exception as e:
        d = {'error': str(e)}
    log(f'[health/{tag}] {json.dumps(d, ensure_ascii=False)}')
    return d


# ---------- Selenium 通用 ----------
def driver():
    o = Options()
    o.binary_location = CHROME
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1050')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    prefs = {
        'download.default_directory': DL,
        'download.prompt_for_download': False,
        'download.directory_upgrade': True,
        'safebrowsing.enabled': True,
        # 同一会话多次导出：允许同源自动多文件下载（Chrome 默认只放行第一个）
        'profile.default_content_setting_values.automatic_downloads': 1,
    }
    o.add_experimental_option('prefs', prefs)
    o.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    import winreg
    major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    path = ''
    if major and os.path.isdir(cache):
        cands = []
        for ver in os.listdir(cache):
            exe = os.path.join(cache, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
                except ValueError:
                    continue
        same = [e for v, e in cands if v and v[0] == major]
        if same:
            path = max(same)
    d = webdriver.Chrome(options=o, service=Service(path) if path else Service())
    d.set_page_load_timeout(90)
    return d


def find(d, t, tag='*', exact=True, vis=True):
    cond = f"normalize-space(.)='{t}'" if exact else f"contains(normalize-space(.),'{t}')"
    for e in d.find_elements(By.XPATH, f"//{tag}[{cond}]"):
        if e.is_displayed() or not vis:
            return e
    return None


def jsclick(d, el):
    d.execute_script("arguments[0].scrollIntoView({block:'center'});arguments[0].click();", el)


def click_text(d, t, tag='*', exact=True, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        e = find(d, t, tag, exact)
        if e:
            jsclick(d, e)
            return e
        time.sleep(0.4)
    try:
        log('  BODY@fail:', d.find_element(By.TAG_NAME, 'body').text[:800].replace('\n', ' | '))
    except Exception:
        pass
    raise AssertionError(f'未找到可点击元素: {t}')


def shot(d, name):
    p = os.path.join(ART, name + '.png')
    d.save_screenshot(p)
    log('  shot:', name)
    return p


def clear_log(d):
    try:
        d.get_log('performance')
    except Exception:
        pass


def calls(d):
    out = []
    try:
        logs = d.get_log('performance')
    except Exception:
        return out
    reqs = {}
    for e in logs:
        try:
            m = json.loads(e['message'])['message']
        except Exception:
            continue
        meth = m.get('method')
        p = m.get('params', {})
        if meth == 'Network.requestWillBeSent':
            r = p['request']
            u = r['url']
            if '/api/' not in u:
                continue
            reqs[p['requestId']] = {
                'method': r['method'],
                'url': u.split('/api/v1')[-1].split('?')[0],
                'status': None,
                'post': (r.get('postData') or '')[:600],
            }
        elif meth == 'Network.responseReceived':
            rid = p['requestId']
            if rid in reqs:
                reqs[rid]['status'] = p['response']['status']
    for v in reqs.values():
        out.append(v)
    return out


def summary(cs):
    return ' ; '.join(
        f"{c['method']} {c['url']} -> {c['status'] if c['status'] is not None else 'pending'}"
        for c in cs)


def wait_dialog(d, frag, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        for e in d.find_elements(By.XPATH, "//*[@role='dialog' or @role='alertdialog']"):
            if e.is_displayed() and frag in (e.text or ''):
                return e
        if find(d, frag, '*', exact=False):
            return find(d, frag, '*', exact=False)
        time.sleep(0.4)
    raise AssertionError('弹窗未出现: ' + frag)


def toast_text(d):
    els = d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')
    return ' | '.join((e.text or '').strip() for e in els if e.is_displayed())


def close_dialog(d):
    try:
        d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    except Exception:
        pass
    time.sleep(0.8)
    for _ in range(3):
        btns = [b for b in d.find_elements(By.XPATH, "//button[@aria-label='关闭' or @aria-label='Close']")
                if b.is_displayed()]
        if not btns:
            break
        jsclick(d, btns[-1])
        time.sleep(0.5)


def wait_ready(d, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        try:
            b = d.find_element(By.TAG_NAME, 'body').text
        except Exception:
            b = ''
        if '用例管理' in b and '导出' in b:
            time.sleep(2)
            return
        time.sleep(1)
    raise AssertionError('用例页未就绪')


def record(name, note, cs=None, extra=None):
    item = {'item': name, 'note': note, 'calls': cs or []}
    if extra:
        item.update(extra)
    EVID.append(item)
    log(f'  [{name}] {note} | {summary(cs or [])}')


def wait_download(before, timeout=90):
    """等下载目录出现新文件（忽略 .crdownload）。"""
    end = time.time() + timeout
    while time.time() < end:
        now = set(os.listdir(DL))
        new = [f for f in now - before if not f.endswith('.crdownload')]
        if new:
            time.sleep(0.8)
            return os.path.join(DL, sorted(new)[-1])
        time.sleep(1)
    return None


def type_into(d, el, text):
    """React 受控输入：clear()/send_keys 不触发 onChange（见 selenium-clear-no-react-onchange），
    用原生 value setter + input/change 事件。"""
    d.execute_script("""
      var el = arguments[0], v = arguments[1];
      el.focus();
      var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      setter.call(el, v);
      el.dispatchEvent(new Event('input', {bubbles: true}));
      el.dispatchEvent(new Event('change', {bubbles: true}));
    """, el, text)


def click_enabled(d, text, tag='button', timeout=120):
    """等按钮可用（disabled=false）再点——分组弹窗要等算法列表加载完。"""
    end = time.time() + timeout
    while time.time() < end:
        for e in d.find_elements(By.XPATH, f"//{tag}[normalize-space(.)='{text}']"):
            if e.is_displayed():
                if e.get_attribute('disabled') in (None, 'false', ''):
                    jsclick(d, e)
                    return e
        time.sleep(1)
    raise AssertionError(f'按钮长时间不可用: {text}')


def search_input(d):
    for sel in ["input[aria-label='搜索用例']", "input[placeholder='搜索用例名称或描述']",
                "input[type='search']"]:
        for e in d.find_elements(By.CSS_SELECTOR, sel):
            if e.is_displayed():
                return e
    return None


# ---------- 夹具 ----------
def make_fixtures():
    s, d = api('GET', '/testcases?per_page=1&keyword=' + urllib.parse.quote('HJ050'))
    items = (d.get('data') or {}).get('items') or []
    if not items:
        s, d = api('GET', '/testcases?per_page=1')
        items = (d.get('data') or {}).get('items') or []
    base_id = items[0]['id']
    s, det = api('GET', '/testcases/' + base_id)
    base = det['data']
    rounds = (base.get('config') or {}).get('rounds') or []
    assert len(rounds) >= 2, f'基准用例轮次不足: {len(rounds)}'
    rounds = rounds[:2]
    for i, r in enumerate(rounds):
        r['round_number'] = i + 1
    log(f'[fixture] 基准用例 {base_id} {base.get("name")} 轮次={len(rounds)}')
    return base, rounds


def create_cases(base, rounds, group_id):
    made = []
    for tag in ('R2A', 'R2B'):
        payload = {
            'name': PREFIX + TS + '_' + tag,
            'description': 'INT-1477 三处修复复验夹具',
            'group_id': group_id,
            'algorithm_type': base.get('algorithm_type'),
            'tags': [],
            'config': {
                'rounds': rounds,
                'dimensions': [],
                'background_noise': None,
                'auto_generated': False,
            },
            'algorithm_params': base.get('algorithm_params') or {},
            'reference_params': base.get('reference_params') or {},
        }
        s, r = api('POST', '/testcases', payload)
        log(f'[fixture] POST /testcases -> {s} {json.dumps(r, ensure_ascii=False)[:200]}')
        if s not in (200, 201):
            raise AssertionError('夹具用例创建失败')
        cid = str((r.get('data') or {}).get('id') or r.get('id'))
        made.append(cid)
        s2, det = api('GET', '/testcases/' + cid)
        n = len(((det.get('data') or {}).get('config') or {}).get('rounds') or [])
        log(f'[fixture] 回读 {cid} rounds={n}')
        assert n == 2, '夹具轮次回读不符'
    return made


def cleanup():
    log('===== 清理 =====')
    ids = STATE.get('case_ids') or []
    for cid in ids:
        s, _ = api('DELETE', '/testcases/' + cid)
        log(f'  DELETE /testcases/{cid} -> {s}')
    if ids:
        s, r = api('POST', '/testcases/purge', {'ids': ids})
        log(f'  POST /testcases/purge -> {s} {json.dumps(r, ensure_ascii=False)[:200]}')
    gid = STATE.get('group_id')
    if gid:
        s, _ = api('DELETE', '/groups/' + str(gid))
        log(f'  DELETE /groups/{gid} -> {s}')
    # 回读残留
    s, d = api('GET', '/testcases?per_page=100&keyword=' + urllib.parse.quote(PREFIX))
    left = (d.get('data') or {}).get('items') or []
    s2, d2 = api('GET', '/testcases?per_page=100&only_deleted=1&keyword=' + urllib.parse.quote(PREFIX))
    left2 = (d2.get('data') or {}).get('items') or []
    s3, d3 = api('GET', '/groups?per_page=200')
    gleft = [g for g in ((d3.get('data') or {}).get('items') or []) if g['name'].startswith(PREFIX)]
    log(f'  残留: cases={len(left)} deleted={len(left2)} groups={len(gleft)}')
    return {'cases': len(left), 'deleted': len(left2), 'groups': len(gleft)}


# ---------- 三个复验项 ----------
def phase_a_new_group(d):
    log('===== A 页面级「新建分组」 =====')
    clear_log(d)
    btn = find(d, '新建分组', 'button')
    assert btn is not None, '工具栏无「新建分组」按钮（INT-1658 未生效）'
    shot(d, '30_page_actions_light')
    jsclick(d, btn)
    wait_dialog(d, '新建分组')
    time.sleep(0.8)
    shot(d, '31_group_create_dialog_light')
    inp = None
    for e in d.find_elements(By.CSS_SELECTOR, "input[placeholder='请输入分组名称']"):
        if e.is_displayed():
            inp = e
            break
    assert inp is not None, '新建分组弹窗无名称输入框'
    type_into(d, inp, GROUP_NAME)
    time.sleep(0.5)
    # 弹窗打开时并行加载算法列表（真实库偶发数十秒），保存按钮在加载完成前 disabled
    click_enabled(d, '保存', timeout=150)
    end = time.time() + 60
    while time.time() < end:
        if '添加分组成功' in (toast_text(d) or ''):
            break
        time.sleep(1)
    cs = calls(d)
    t = toast_text(d)
    shot(d, '32_group_created_light')
    record('A:页面级新建分组', f'点击工具栏「新建分组」→ 填 {GROUP_NAME} → 保存；toast={t!r}', cs)
    post = [c for c in cs if c['method'] == 'POST' and c['url'] == '/groups' and c['status'] in (200, 201)]
    assert post, f'未见 POST /groups 2xx: {summary(cs)}'
    s, d2 = api('GET', '/groups?per_page=200')
    hit = [g for g in ((d2.get('data') or {}).get('items') or []) if g['name'] == GROUP_NAME]
    assert hit, 'GET /groups 回读不到新建分组'
    STATE['group_id'] = hit[0]['id']
    log(f'  GET /groups 回读: {hit[0]["id"]} {hit[0]["name"]} count={hit[0].get("test_case_count")}')
    EVID[-1]['readback'] = hit[0]
    close_dialog(d)


def visible_case_boxes(d):
    return [e for e in d.find_elements(By.XPATH, "//*[@role='checkbox']")
            if e.is_displayed() and (e.get_attribute('aria-label') or '').startswith('选择 ')]


def select_two(d):
    """在「按分组」视图里勾选夹具分组的 2 条用例。

    注意：分组视图的卡片列表来自 GET /groups（全部组按用例数降序），页内搜索只过滤组内用例、
    不减少组卡数量（INT-1477 实测），故要先「加载更多」翻到夹具组，再用组头「全选分组」
    （POST /testcases/ids 按组名圈定）选中整组 2 条。
    """
    inp = search_input(d)
    if inp is not None:
        type_into(d, inp, '')
        time.sleep(1.5)
    end = time.time() + 150
    found = False
    while time.time() < end:
        names = [e for e in d.find_elements(By.XPATH, f"//span[normalize-space(.)='{GROUP_NAME}']")
                 if e.is_displayed()]
        if names:
            found = True
            break
        btns = [e for e in d.find_elements(By.XPATH, "//button[contains(normalize-space(.),'加载更多')]")
                if e.is_displayed()]
        if not btns:
            break
        jsclick(d, btns[0])
        time.sleep(4)
    log(f'  夹具组卡可见={found}')
    boxes = visible_case_boxes(d)
    if len(boxes) < 2:
        g = [e for e in d.find_elements(
            By.XPATH, f"//*[@role='checkbox' and @aria-label='全选分组 {GROUP_NAME}']") if e.is_displayed()]
        if g:
            jsclick(d, g[0])
            time.sleep(2.5)
            boxes = visible_case_boxes(d)
    if len(boxes) < 2 and found:
        # 组卡折叠：点组名展开后逐卡勾选
        for e in d.find_elements(By.XPATH, f"//span[normalize-space(.)='{GROUP_NAME}']"):
            if e.is_displayed():
                jsclick(d, e)
                break
        time.sleep(3)
        boxes = visible_case_boxes(d)
        if len(boxes) >= 2:
            jsclick(d, boxes[0])
            time.sleep(0.8)
            jsclick(d, boxes[1])
            time.sleep(1.5)
    body = d.find_element(By.TAG_NAME, 'body').text
    if '已选择' not in body:
        shot(d, 'fail_select_two')
        log('  BODY:', body[:500].replace('\n', ' | '))
    assert '已选择' in body, '未出现批量浮条'
    bar = [ln for ln in body.split('\n') if '已选择' in ln][:1]
    log('  批量浮条:', bar)
    assert any('2' in b for b in bar), f'选中数不是 2: {bar}'


def count_rows(obj):
    if isinstance(obj, list):
        return len(obj)
    if isinstance(obj, dict):
        for k in ('items', 'data', 'test_cases', 'testcases', 'list', 'records'):
            if k in obj:
                return count_rows(obj[k])
    return None


def phase_b_export(d):
    log('===== B 导出弹窗真实接线 =====')
    before = set(os.listdir(DL))
    clear_log(d)
    click_text(d, '导出', 'button')
    wait_dialog(d, '导出用例')
    time.sleep(0.8)
    shot(d, '33_export_dialog_light')
    body = d.find_element(By.TAG_NAME, 'body').text
    assert '按当前筛选条件导出' in body, '导出范围文案缺失'
    # 选「仅导出已选 2 个用例」
    labels = [e for e in d.find_elements(By.XPATH, "//label[contains(normalize-space(.),'仅导出已选')]")
              if e.is_displayed()]
    assert labels, '无「仅导出已选」选项'
    jsclick(d, labels[0])
    time.sleep(0.6)
    shot(d, '34_export_selected_scope_light')
    click_text(d, '开始导出', 'button')
    t = None
    end = time.time() + 90
    path = None
    while time.time() < end:
        t = toast_text(d)
        path = wait_download(before, timeout=5)
        if path:
            break
        if '导出失败' in (t or ''):
            break
        time.sleep(2)
    cs = calls(d)
    shot(d, '35_export_selected_done_light')
    log(f'  toast={t!r} file={path}')
    record('B1:导出-仅已选', f'勾选 2 条 → 仅导出已选 → toast={t!r} file={os.path.basename(path) if path else None}', cs)
    exp = [c for c in cs if c['url'] == '/testcases/export' and c['method'] == 'POST']
    assert exp and exp[0]['status'] == 200, f'POST /testcases/export 非 200: {summary(cs)}'
    assert path and os.path.getsize(path) > 0, '下载文件缺失或为空'
    n = None
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        n = count_rows(data)
    except Exception as e:
        log('  JSON 解析失败:', e)
    EVID[-1].update({'file': os.path.basename(path), 'size': os.path.getsize(path),
                     'request': exp[0]['post'], 'rows': n})
    assert n == 2, f'导出条数 {n} != 2'
    if d.find_elements(By.XPATH, "//*[@role='dialog']"):
        close_dialog(d)
    time.sleep(1)

    # B2：按当前筛选导出（Excel），筛选条件=搜索夹具前缀
    inp = search_input(d)
    if inp is not None:
        type_into(d, inp, PREFIX + TS)
        time.sleep(4)
    before = set(os.listdir(DL))
    clear_log(d)
    click_text(d, '导出', 'button')
    wait_dialog(d, '导出用例')
    time.sleep(0.8)
    # 切 Excel（弹窗内格式 Select）
    trig = [e for e in d.find_elements(By.XPATH, "//*[@role='dialog']//button[@role='combobox']")
            if e.is_displayed()]
    log(f'  弹窗内 combobox {len(trig)} 个')
    if trig:
        jsclick(d, trig[-1])
        time.sleep(1)
        opts = [e for e in d.find_elements(By.XPATH, "//*[normalize-space(.)='Excel']") if e.is_displayed()]
        if opts:
            jsclick(d, opts[-1])
            time.sleep(0.8)
    shot(d, '36_export_filter_scope_light')
    click_text(d, '开始导出', 'button')
    t = None
    path2 = None
    end = time.time() + 120
    while time.time() < end:
        t = toast_text(d)
        path2 = wait_download(before, timeout=5)
        if path2:
            break
        if '导出失败' in (t or ''):
            break
        time.sleep(2)
    cs = calls(d)
    shot(d, '37_export_filter_done_light')
    record('B2:导出-按筛选(Excel)', f'筛选「{PREFIX + TS}」→ 按当前筛选导出 → toast={t!r}', cs)
    log(f'  toast={t!r} file={path2}')
    exp = [c for c in cs if c['url'] in ('/testcases/export', '/testcases/ids') and c['method'] in ('POST',)]
    assert path2 and os.path.getsize(path2) > 0, 'Excel 下载为空'
    EVID[-1].update({'file': os.path.basename(path2), 'size': os.path.getsize(path2),
                     'requests': exp})
    if d.find_elements(By.XPATH, "//*[@role='dialog']"):
        close_dialog(d)
    time.sleep(1)


def phase_c_batch_dimensions(d):
    log('===== C 批量评估维度真实轮次 =====')
    clear_log(d)
    click_text(d, '批量设置评估维度', 'button')
    time.sleep(2.5)
    dlg = wait_dialog(d, '评估维度')
    body = dlg.text
    shot(d, '38_batch_dimensions_light')
    # 指定轮次：勾选网格应只出 第1/第2轮
    spec = [e for e in d.find_elements(By.XPATH, "//label[contains(normalize-space(.),'指定轮次')]")
            if e.is_displayed()]
    if spec:
        jsclick(d, spec[0])
        time.sleep(1.2)
    shot(d, '39_batch_dimensions_specific_light')
    dlg = [e for e in d.find_elements(By.XPATH, "//*[@role='dialog']") if e.is_displayed()][-1]
    t_spec = dlg.text
    has1 = '第 1 轮' in t_spec or '第1轮' in t_spec
    has2 = '第 2 轮' in t_spec or '第2轮' in t_spec
    has3 = '第 3 轮' in t_spec or '第3轮' in t_spec
    has4 = '第 4 轮' in t_spec or '第4轮' in t_spec
    log(f'  指定轮次: 第1轮={has1} 第2轮={has2} 第3轮={has3} 第4轮={has4}')
    # 逐轮模式：Tab 角标
    per = [e for e in d.find_elements(By.XPATH, "//label[contains(normalize-space(.),'逐轮设置')]")
           if e.is_displayed()]
    if per:
        jsclick(d, per[0])
        time.sleep(1.5)
    shot(d, '40_batch_dimensions_per_round_light')
    dlg = [e for e in d.find_elements(By.XPATH, "//*[@role='dialog']") if e.is_displayed()][-1]
    t_per = dlg.text
    tunits = [u for u in ('第1轮', '第 1 轮', '第2轮', '第 2 轮') if u in t_per]
    record('C:批量评估维度-轮次', f'指定轮次含第1/2轮={has1}/{has2}，第3/4轮={has3}/{has4}；逐轮 Tab={tunits}',
           calls(d), {'dialog_text_head': t_per[:400]})
    assert has1 and has2, '指定轮次网格缺少第 1/2 轮'
    assert not has3 and not has4, f'仍出现不存在的第 3/4 轮（mock 残留？）: {t_spec[:300]}'
    close_dialog(d)
    time.sleep(0.6)


def dark_shots(d):
    log('===== 深色三窗截图 =====')
    d.get(BASE + '/')
    time.sleep(2)
    d.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark');")
    d.get(BASE + '/testcases/by-group?rw=%d' % int(time.time()))
    wait_ready(d)
    inp = search_input(d)
    if inp is not None:
        type_into(d, inp, PREFIX + TS)
        inp.send_keys(Keys.ENTER)
        time.sleep(5)
    btn = find(d, '新建分组', 'button')
    if btn is not None:
        jsclick(d, btn)
        wait_dialog(d, '新建分组')
        time.sleep(0.8)
        shot(d, '31_group_create_dialog_dark')
        close_dialog(d)
    select_two(d)
    click_text(d, '导出', 'button')
    wait_dialog(d, '导出用例')
    time.sleep(0.8)
    shot(d, '33_export_dialog_dark')
    close_dialog(d)
    click_text(d, '批量设置评估维度', 'button')
    time.sleep(2.5)
    wait_dialog(d, '评估维度')
    shot(d, '38_batch_dimensions_dark')
    close_dialog(d)
    d.execute_script("localStorage.setItem('iatp:theme:v1:mode','light');")


def main():
    h0 = check_health('开工')
    base, rounds = make_fixtures()
    d = driver()
    try:
        d.get(BASE + '/testcases/by-group?rw=%d' % int(time.time()))
        wait_ready(d)
        STATE['bundle'] = d.execute_script(
            "return [...document.querySelectorAll('script[src]')].map(s=>s.src).filter(s=>/index\\./.test(s)).join(',')")
        log('[bundle]', STATE['bundle'])
        phase_a_new_group(d)
        STATE['case_ids'] = create_cases(base, rounds, STATE['group_id'])
        # 新建后刷新列表拿到夹具用例
        d.get(BASE + '/testcases/by-group?rw=%d' % int(time.time()))
        wait_ready(d)
        select_two(d)
        phase_b_export(d)
        select_two(d)
        phase_c_batch_dimensions(d)
        dark_shots(d)
        check_health('交付前')
    finally:
        try:
            d.quit()
        except Exception:
            pass
        clean = cleanup()

    out = {
        'ts': TS,
        'base': BASE,
        'bundle': STATE['bundle'],
        'health_start': h0,
        'evidence': EVID,
        'cleanup': clean,
    }
    p = os.path.join(ART, 'evidence_fix.json')
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    log('EVIDENCE ->', p)
    log(json.dumps(EVID, ensure_ascii=False, indent=1)[:4000])


if __name__ == '__main__':
    main()