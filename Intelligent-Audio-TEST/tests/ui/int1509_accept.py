# -*- coding: utf-8 -*-
"""INT-1509 阶段 1 真实库验收走查（pickable-tasks 接线，docker 栈 15000 / dev 5309）。

分段执行（每段独立浏览器会话，结果合并到 accept.json），避免单点崩溃丢全部证据：
  python tests/ui/int1509_accept.py states|stage1|stage2|small|dark|all

覆盖验收标准：
2. 阶段 1 任务数 = 接口 total（117）、大任务 419/418 可见、阶段 1 只发一次 pickable-tasks 不调 candidates
3. pickable_count 与阶段 2 候选行数（excluded=0）核对（≥3 个任务）
4. 「全选当前筛选」选中数 = total（跨页），界面提示 + Network 请求次数
5. 阶段 1 已选 / 阶段 2 摘要 / 返回上一步 / 切排序 / 切筛选 状态同步；向导关闭重开重置
6. 加载态 / 空态 / 错误态截图（响应延迟注入、URL 拦截、响应体注入；均不入库）
8. 浅色 + 深色全页截图 + 排序下拉 / 搜索 / 全选提示
"""
import base64
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('INT1509_BASE', 'http://127.0.0.1:5309')
API = os.environ.get('INT1509_API', 'http://127.0.0.1:15000/api/v1')
ART = os.path.join('tests', 'ui', 'artifacts', 'int1509')
DRIVER = os.environ.get(
    'INT1509_DRIVER',
    r'D:\00_user_data\.cache\selenium\chromedriver\win64\155.0.8059.84\chromedriver.exe',
)
os.makedirs(ART, exist_ok=True)
STORE = os.path.join(ART, 'accept.json')


def load_store():
    try:
        with open(STORE, encoding='utf-8') as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {'started_at': time.strftime('%Y-%m-%dT%H:%M:%S'), 'base': BASE, 'api': API,
                'shots': []}


def save_store(r=None):
    data = r if r is not None else STORE_
    with open(STORE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


STORE_ = load_store()


def log(msg):
    print('[%s] %s' % (time.strftime('%H:%M:%S'), msg), file=sys.stderr, flush=True)


def http_json(path, timeout=120, retries=4):
    """GET JSON；共享栈偶发 400/DEADLINE_EXCEEDED → 退避重试，仍失败再抛。"""
    url = API + path
    last = None
    for i in range(retries):
        t0 = time.time()
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                data = json.load(resp)
            return data, round((time.time() - t0) * 1000)
        except Exception as e:  # noqa: BLE001
            body = ''
            try:
                body = e.read().decode('utf-8', 'replace')[:300]  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                pass
            last = f'{type(e).__name__}: {e} {body}'
            time.sleep(3 * (i + 1))
    raise RuntimeError(f'GET {path} failed after {retries}: {last}')


def health():
    try:
        with urllib.request.urlopen('http://127.0.0.1:15000/health', timeout=20) as resp:
            return json.load(resp)
    except Exception as e:  # noqa: BLE001
        return {'error': str(e)}


def driver():
    os.environ.setdefault('SE_OFFLINE', 'true')
    opts = webdriver.ChromeOptions()
    opts.add_argument('--headless=new')
    opts.add_argument('--window-size=1680,1050')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--disable-extensions')
    opts.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    d = webdriver.Chrome(service=Service(DRIVER), options=opts)
    d.set_page_load_timeout(180)
    d.set_script_timeout(60)
    return d


def shot(d, name, full=True):
    time.sleep(0.5)
    p = os.path.join(ART, name + '.png')
    if full:
        try:
            m = d.execute_cdp_cmd('Page.getLayoutMetrics', {})
            size = m.get('cssContentSize') or m.get('contentSize')
            w = min(int(size['width']), 1680)
            h = min(int(size['height']), 4200)
            data = d.execute_cdp_cmd(
                'Page.captureScreenshot',
                {'format': 'png', 'captureBeyondViewport': True,
                 'clip': {'x': 0, 'y': 0, 'width': w, 'height': h, 'scale': 1}},
            )
            with open(p, 'wb') as f:
                f.write(base64.b64decode(data['data']))
            return p
        except Exception as e:  # noqa: BLE001
            log('full screenshot fallback: %s' % e)
    d.save_screenshot(p)
    return p


def js_click(d, el):
    d.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)


def click_text(d, text, tag='button', exact=True):
    for b in d.find_elements(By.TAG_NAME, tag):
        try:
            t = (b.text or '').strip()
            if b.is_displayed() and ((t == text) if exact else (text in t)):
                js_click(d, b)
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def drain(d):
    out = []
    for e in d.get_log('performance'):
        try:
            m = json.loads(e['message']).get('message', {})
        except Exception:  # noqa: BLE001
            continue
        meth = m.get('method')
        pr = m.get('params', {})
        if meth == 'Network.requestWillBeSent':
            u = pr.get('request', {}).get('url', '')
            if '/api/' in u:
                out.append({'kind': 'req', 'url': u,
                            'method': pr.get('request', {}).get('method')})
        elif meth == 'Network.responseReceived':
            r = pr.get('response', {})
            u = r.get('url', '')
            if '/api/' in u:
                out.append({'kind': 'resp', 'url': u, 'status': r.get('status')})
    return out


def q(url):
    return urllib.parse.parse_qs(urllib.parse.urlparse(url).query)


def set_theme(d, mode):
    d.get(BASE + '/')
    d.execute_script("window.localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", mode)
    d.refresh()
    time.sleep(1.5)


def body_text(d):
    try:
        return d.find_element(By.TAG_NAME, 'body').text
    except Exception:  # noqa: BLE001
        return ''


def open_stage1(d, timeout=120):
    d.get(BASE + '/tasks?tab=cherry-picks')
    WebDriverWait(d, timeout).until(
        lambda x: any(b.is_displayed() and '开始挑选' in (b.text or '')
                      for b in x.find_elements(By.TAG_NAME, 'button'))
    )
    for b in d.find_elements(By.TAG_NAME, 'button'):
        if b.is_displayed() and (b.text or '').strip() == '开始挑选':
            js_click(d, b)
            break
    WebDriverWait(d, timeout).until(lambda x: '挑选 · 阶段 1：选择任务' in (x.page_source or ''))


def stage1_state(d):
    rows = [r for r in d.find_elements(By.CSS_SELECTOR, "[data-testid^='pick-task-']")]
    ids = []
    texts = []
    for r in rows:
        tid = (r.get_attribute('data-testid') or '').replace('pick-task-', '')
        if tid.isdigit():
            ids.append(int(tid))
        texts.append((r.text or '').replace('\n', ' '))
    txt = body_text(d)
    skeletons = d.find_elements(By.CSS_SELECTOR, "[data-slot='skeleton'], .animate-pulse")
    m_total = re.search(r'共\s*(\d+)\s*个可挑选任务', txt)
    m_sel = re.search(r'已选\s*(\d+)\s*个任务', txt)
    m_load = re.search(r'已加载\s*(\d+)/(\d+)', txt)
    m_prompt = re.search(r'全选当前筛选将选中命中全部\s*(\d+)\s*个任务([^\n]*)', txt)
    return {
        'rows': len(rows),
        'ids': ids,
        'row_texts': texts[:5],
        'total': int(m_total.group(1)) if m_total else None,
        'selected': int(m_sel.group(1)) if m_sel else None,
        'loaded_hint': m_load.group(0) if m_load else None,
        'select_all_prompt': m_prompt.group(0) if m_prompt else None,
        'error': '可挑选任务加载失败' in txt,
        'empty': '暂无可挑选的终态任务' in txt,
        'skeletons': len(skeletons),
        'loading_hint': len(skeletons) > 0,
    }


def row_counts(d):
    out = {}
    for r in d.find_elements(By.CSS_SELECTOR, "[data-testid^='pick-task-']"):
        tid = (r.get_attribute('data-testid') or '').replace('pick-task-', '')
        m = re.search(r'(\d+)\s*条', r.text or '')
        if tid.isdigit() and m:
            out[int(tid)] = int(m.group(1))
    return out


def wait_rows(d, timeout=180, retries=2):
    deadline = time.time() + timeout
    st = stage1_state(d)
    while time.time() < deadline and not (st['rows'] > 0 or st['error'] or st['empty']):
        time.sleep(1.5)
        st = stage1_state(d)
    tries = 0
    while st['error'] and tries < retries:  # 共享栈偶发超时 → 点重试
        click_text(d, '重试')
        tries += 1
        deadline = time.time() + timeout
        while time.time() < deadline and not (stage1_state(d)['rows'] > 0):
            time.sleep(1.5)
        st = stage1_state(d)
    time.sleep(1)
    return stage1_state(d)


def switch_sort(d, label):
    trig = None
    for b in d.find_elements(By.CSS_SELECTOR, "button[aria-label='排序方式']"):
        if b.is_displayed():
            trig = b
            break
    if trig is None:
        return False
    js_click(d, trig)
    time.sleep(0.8)
    for m in d.find_elements(By.CSS_SELECTOR, "[role='option'], [role='menuitem'], [data-slot='select-item']"):
        try:
            if m.is_displayed() and (m.text or '').strip() == label:
                js_click(d, m)
                time.sleep(1.0)
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def toggle_dir(d):
    for b in d.find_elements(By.CSS_SELECTOR, "button[aria-label*='切换为']"):
        if b.is_displayed():
            before = b.get_attribute('aria-label')
            js_click(d, b)
            time.sleep(1.0)
            return before
    return None


def set_search(d, text):
    inp = None
    for i in d.find_elements(By.CSS_SELECTOR, "input[aria-label='搜索任务名称']"):
        if i.is_displayed():
            inp = i
            break
    if inp is None:
        return False
    js_click(d, inp)
    inp.send_keys(Keys.CONTROL, 'a')
    inp.send_keys(Keys.DELETE)
    time.sleep(0.4)
    if text:
        inp.send_keys(text)
    time.sleep(0.8)
    return True


def pick_rows(d, ids):
    done = []
    for tid in ids:
        el = d.find_element(
            By.CSS_SELECTOR,
            f"[data-testid='pick-task-{tid}'] [data-slot='checkbox'], "
            f"[data-testid='pick-task-{tid}'] [role='checkbox']")
        js_click(d, el)
        done.append(tid)
        time.sleep(0.25)
    return done


def stage2_state(d):
    txt = body_text(d)
    leaf = d.find_elements(By.CSS_SELECTOR, "[data-testid^='pick-leaf-']")
    branch = d.find_elements(By.CSS_SELECTOR, "[data-testid^='pick-branch-']")
    m_task = re.search(r'已选任务：\s*([^\n]*)', txt)
    m_stat = re.search(r'已选\s*(\d+)\s*条结果\s*·\s*来自\s*(\d+)\s*个任务\s*·\s*覆盖\s*(\d+)\s*台设备', txt)
    return {
        'phase2': '挑选 · 阶段 2：选择结果' in txt,
        'task_summary': (m_task.group(1).strip() if m_task else None),
        'leaf_rows': len(leaf),
        'branch_rows': len(branch),
        'summary': m_stat.group(0) if m_stat else None,
        'error': '候选加载失败' in txt,
        'empty': '无符合条件的执行结果' in txt,
    }


def wait_stage2(d, timeout=300, retries=2):
    WebDriverWait(d, timeout).until(lambda x: '挑选 · 阶段 2：选择结果' in (x.page_source or ''))
    deadline = time.time() + timeout
    st = stage2_state(d)
    while time.time() < deadline and not (st['leaf_rows'] or st['branch_rows'] or st['error'] or st['empty']):
        time.sleep(2)
        st = stage2_state(d)
    tries = 0
    while st['error'] and tries < retries:
        click_text(d, '重试')
        tries += 1
        deadline = time.time() + timeout
        while time.time() < deadline and not stage2_state(d)['error']:
            time.sleep(2)
        st = stage2_state(d)
    time.sleep(1)
    return stage2_state(d)


def api_snapshot():
    page, ms = http_json(
        '/tasks/cherry-picks/pickable-tasks?page=1&per_page=200&sort_by=status&sort_order=asc')
    items = page['data']['items']
    totals = {i['id']: i['pickable_count'] for i in items}
    return {'total': page['data']['total'], 'items': items,
            'counts': {str(k): v for k, v in totals.items()}, 'ms': ms}


# ---------------- 分段 ----------------

def seg_states(d, r):
    r['health_start'] = health()
    set_theme(d, 'light')
    delay_patch = """
    (function(){
      var of = window.fetch;
      window.fetch = function(input, init){
        var url = (typeof input === 'string') ? input : ((input && input.url) || '');
        if (url.indexOf('pickable-tasks') >= 0) {
          return new Promise(function(res){
            setTimeout(function(){ res(of.apply(window, [input, init])); }, 4000);
          });
        }
        return of.apply(this, arguments);
      };
    })();
    """
    log('loading')
    sid = d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': delay_patch})
    open_stage1(d)
    time.sleep(1.2)
    r['loading_state'] = stage1_state(d)
    r['shots'].append(shot(d, 'p6_loading'))
    try:
        d.execute_cdp_cmd('Page.removeScriptToEvaluateOnNewDocument',
                          {'identifier': sid.get('identifier')})
    except Exception as e:  # noqa: BLE001
        r['loading_cleanup_error'] = str(e)
    log('loading done %s' % r['loading_state'])
    save_store(r)

    log('error')
    d.execute_cdp_cmd('Network.enable', {})
    d.execute_cdp_cmd('Network.setBlockedURLs', {'urls': ['*pickable-tasks*']})
    open_stage1(d)
    deadline = time.time() + 120
    est = stage1_state(d)
    while time.time() < deadline and not est['error']:
        time.sleep(1)
        est = stage1_state(d)
    r['error_state'] = est
    r['shots'].append(shot(d, 'p7_error'))
    log('error done %s' % est)
    save_store(r)
    d.execute_cdp_cmd('Network.setBlockedURLs', {'urls': []})

    log('empty')
    patch = """
    (function(){
      var of = window.fetch;
      window.fetch = function(input, init){
        var url = (typeof input === 'string') ? input : ((input && input.url) || '');
        if (url.indexOf('pickable-tasks') >= 0) {
          var body = JSON.stringify({success:true, code:0, message:'Success',
            data:{items:[], total:0, page:1, per_page:200}});
          return Promise.resolve(new Response(body, {status:200,
            headers:{'Content-Type':'application/json'}}));
        }
        return of.apply(this, arguments);
      };
    })();
    """
    sid = d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': patch})
    open_stage1(d)
    deadline = time.time() + 90
    strict = stage1_state(d)
    while time.time() < deadline and not strict['empty']:
        time.sleep(1)
        strict = stage1_state(d)
    r['empty_state'] = strict
    r['shots'].append(shot(d, 'p8_empty'))
    log('empty done %s' % strict)
    save_store(r)
    try:
        d.execute_cdp_cmd('Page.removeScriptToEvaluateOnNewDocument',
                          {'identifier': sid.get('identifier')})
    except Exception as e:  # noqa: BLE001
        r['empty_cleanup_error'] = str(e)


def seg_stage1(d, r):
    api = r.get('api_snapshot') or api_snapshot()
    r['api_snapshot'] = api
    log('api total=%s' % api['total'])
    save_store(r)

    set_theme(d, 'light')
    drain(d)
    open_stage1(d)
    st = wait_rows(d)
    time.sleep(3)  # 等 responseReceived 落 performance log
    nw = drain(d)
    r['stage1_light'] = st
    reqs = [n for n in nw if n['kind'] == 'req' and
            ('pickable-tasks' in n['url'] or '/candidates' in n['url'])]
    pick = [n['url'] for n in reqs if 'pickable-tasks' in n['url']]
    cand = [n['url'] for n in reqs if '/candidates' in n['url']]
    r['network_stage1_raw'] = nw
    r['network_stage1'] = {
        'pickable_count': len(pick),
        'pickable_params': [q(u) for u in pick],
        'candidates_count': len(cand),
        'candidates_urls': cand,
    }
    r['row_counts_sample'] = {str(k): v for k, v in row_counts(d).items() if k in (419, 418, 187)}
    r['stage1_vs_api'] = {
        'rows': st['rows'], 'api_total': api['total'], 'total_text': st['total'],
        'match': st['rows'] == api['total'] == st['total'],
        'has_419': 419 in st['ids'], 'has_418': 418 in st['ids'],
    }
    r['shots'].append(shot(d, 'p1_stage1_light'))
    log('stage1 %s net=%s' % (r['stage1_vs_api'], r['network_stage1']))
    save_store(r)

    # 排序下拉展开截图
    log('sort dropdown')
    for b in d.find_elements(By.CSS_SELECTOR, "button[aria-label='排序方式']"):
        if b.is_displayed():
            js_click(d, b)
            break
    time.sleep(0.8)
    r['shots'].append(shot(d, 'p2_sort_dropdown'))
    d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(0.5)

    # 三种排序 × 方向
    sorts = []
    sort_nw = []
    for label in ('任务名', '创建时间', '状态'):
        drain(d)
        ok = switch_sort(d, label)
        time.sleep(1.5)
        ns = drain(d)
        sort_nw.extend(ns)
        purs = [n['url'] for n in ns if n['kind'] == 'req' and 'pickable-tasks' in n['url']]
        sst = stage1_state(d)
        sorts.append({'label': label, 'clicked': ok,
                      'params': [q(u) for u in purs],
                      'first_text': (sst['row_texts'][0] if sst['row_texts'] else None),
                      'rows': sst['rows']})
        log('sort %s -> %s' % (label, sorts[-1]['params']))
    dir_before = toggle_dir(d)
    time.sleep(1.5)
    ns = drain(d)
    dir_nw = ns
    dir_params = [q(n['url']) for n in ns if n['kind'] == 'req' and 'pickable-tasks' in n['url']]
    sds = stage1_state(d)
    r['sorts'] = sorts
    r['network_stage1_raw'] = (r.get('network_stage1_raw') or []) + nw + sort_nw + dir_nw
    r['direction_toggle'] = {'from': dir_before, 'params': dir_params,
                             'first_text': (sds['row_texts'][0] if sds['row_texts'] else None),
                             'rows': sds['rows']}
    r['shots'].append(shot(d, 'p3_sorted'))
    save_store(r)
    switch_sort(d, '状态')

    # 搜索 + 全选
    log('search + select all')
    set_search(d, 'E2E')
    time.sleep(0.8)
    sst = stage1_state(d)
    r['search_filter'] = {'rows': sst['rows'], 'prompt': sst['select_all_prompt'],
                          'selected': sst['selected']}
    r['shots'].append(shot(d, 'p9_search_filtered'))
    set_search(d, '')
    time.sleep(0.8)
    drain(d)
    click_text(d, '全选当前筛选')
    time.sleep(1.2)
    sel = stage1_state(d)
    ns = drain(d)
    pick_after = [n['url'] for n in ns if n['kind'] == 'req' and 'pickable-tasks' in n['url']]
    r['select_all'] = {
        'selected': sel['selected'], 'total': sel['total'], 'rows': sel['rows'],
        'prompt': sel['select_all_prompt'],
        'extra_pickable_requests': len(pick_after),
        'skeleton_visible': sel['loading_hint'],
    }
    r['shots'].append(shot(d, 'p4_select_all'))
    log('select_all %s' % r['select_all'])
    save_store(r)


def seg_stage2(d, r):
    api = r.get('api_snapshot') or api_snapshot()
    r['api_snapshot'] = api
    set_theme(d, 'light')
    open_stage1(d)
    st = wait_rows(d)
    click_text(d, '全选当前筛选')
    time.sleep(1.2)
    sel = stage1_state(d)
    log('selected %s' % sel['selected'])
    drain(d)
    click_text(d, '下一步：选择结果（%d）' % (sel['selected'] or 0))
    st2 = wait_stage2(d)
    nw2 = drain(d)
    c2 = [n['url'] for n in nw2 if n['kind'] == 'req' and '/candidates' in n['url']]
    r['stage2_117'] = {
        'state': st2,
        'candidates_requests': len(c2),
        'candidates_url_head': (c2[0][:300] if c2 else None),
        'candidates_task_ids': (len(q(c2[0]).get('task_ids', [''])[0].split(',')) if c2 else None),
        'expected_tasks': sel['selected'],
    }
    r['shots'].append(shot(d, 'p5_stage2'))
    log('stage2_117 %s' % {k: v for k, v in r['stage2_117'].items() if k != 'candidates_url_head'})
    save_store(r)

    # 返回阶段 1：勾选保持；切排序后仍保持
    click_text(d, '更换任务')
    time.sleep(1.5)
    back = wait_rows(d)
    r['back_to_stage1'] = {'selected': back['selected'], 'rows': back['rows'],
                           'same_as_select_all': back['selected'] == sel['selected']}
    switch_sort(d, '任务名')
    time.sleep(1.5)
    after = wait_rows(d)
    r['select_kept_after_sort'] = {'selected': after['selected'], 'rows': after['rows']}
    log('sync back=%s after_sort=%s' % (r['back_to_stage1'], r['select_kept_after_sort']))
    save_store(r)


def seg_small(d, r):
    api = r.get('api_snapshot') or api_snapshot()
    r['api_snapshot'] = api
    cmp = []
    for tid in (419, 418, 187):
        try:
            cdata, cms = http_json(
                f'/tasks/cherry-picks/candidates?page=1&per_page=1&task_ids={tid}', retries=5)
            cmp.append({'task_id': tid, 'pickable_count': api['counts'].get(str(tid)),
                        'candidates_total': cdata['data'].get('total'), 'ms': cms})
        except Exception as e:  # noqa: BLE001
            cmp.append({'task_id': tid, 'pickable_count': api['counts'].get(str(tid)),
                        'error': str(e)[:300]})
    r['pickable_vs_candidates'] = cmp
    log('pickable_vs_candidates %s' % cmp)
    save_store(r)

    set_theme(d, 'light')
    open_stage1(d)
    wait_rows(d)
    click_text(d, '清空')
    time.sleep(0.8)
    cleared = stage1_state(d)
    pick_rows(d, [187, 191, 192])
    time.sleep(0.8)
    small_sel = stage1_state(d)
    r['small_selection'] = {'selected': small_sel['selected'], 'cleared_before': cleared['selected']}
    log('small_selection %s' % r['small_selection'])
    drain(d)
    click_text(d, '下一步：选择结果（%d）' % (small_sel['selected'] or 0))
    st2 = wait_stage2(d)
    nw2 = drain(d)
    click_text(d, '全部展开')
    time.sleep(1.5)
    st2e = stage2_state(d)
    c2 = [n['url'] for n in nw2 if n['kind'] == 'req' and '/candidates' in n['url']]
    exp = sum(int(api['counts'].get(str(t), 0)) for t in (187, 191, 192))
    r['stage2_small'] = {
        'state': st2,
        'state_expanded': st2e,
        'candidates_requests': len(c2),
        'candidates_url': (c2[0][:300] if c2 else None),
        'expected_leaf_rows': exp,
        'leaf_match': st2e['leaf_rows'] == exp,
    }
    r['shots'].append(shot(d, 'p10_stage2_small'))
    log('stage2_small %s' % {k: v for k, v in r['stage2_small'].items() if k != 'candidates_url'})
    save_store(r)

    # 阶段 2 切执行状态筛选
    changed = False
    for b in d.find_elements(By.CSS_SELECTOR, "button[aria-label='执行状态']"):
        if b.is_displayed():
            js_click(d, b)
            time.sleep(0.8)
            for m in d.find_elements(By.CSS_SELECTOR,
                                     "[role='option'], [role='menuitem'], [data-slot='select-item']"):
                try:
                    if m.is_displayed() and '已完成' in (m.text or ''):
                        js_click(d, m)
                        changed = True
                        break
                except Exception:  # noqa: BLE001
                    continue
            break
    time.sleep(2.5)
    nw_f = drain(d)
    cf = [n['url'] for n in nw_f if n['kind'] == 'req' and '/candidates' in n['url']]
    st2f = stage2_state(d)
    r['stage2_filter_change'] = {
        'changed': changed,
        'candidates_requests': len(cf),
        'candidates_params': [q(u) for u in cf],
        'task_summary': st2f['task_summary'],
        'summary_unchanged': st2f['task_summary'] == r['stage2_small']['state']['task_summary'],
    }
    log('filter change %s' % r['stage2_filter_change'])
    save_store(r)

    # 向导关闭重开重置
    click_text(d, '返回列表')
    time.sleep(1.5)
    open_stage1(d)
    reset = wait_rows(d)
    r['wizard_reopen'] = {'selected': reset['selected'], 'rows': reset['rows']}
    r['shots'].append(shot(d, 'p11_reopen_reset'))
    log('reopen %s' % r['wizard_reopen'])
    save_store(r)


def seg_sortmenu(d, r):
    set_theme(d, 'light')
    open_stage1(d)
    wait_rows(d)
    for b in d.find_elements(By.CSS_SELECTOR, "button[aria-label='排序方式']"):
        if b.is_displayed():
            js_click(d, b)
            break
    time.sleep(1.0)
    r['sortmenu_visible'] = len([m for m in d.find_elements(
        By.CSS_SELECTOR, "[role='option'], [role='menuitem'], [data-slot='select-item']") if m.is_displayed()])
    r['shots'].append(shot(d, 'p2_sort_menu', full=False))
    log('sortmenu options=%s' % r['sortmenu_visible'])
    save_store(r)


def seg_dark(d, r):
    set_theme(d, 'dark')
    open_stage1(d)
    dark = wait_rows(d)
    r['stage1_dark'] = dark
    r['shots'].append(shot(d, 'p12_stage1_dark'))
    pick_rows(d, [419])
    time.sleep(0.6)
    r['shots'].append(shot(d, 'p13_stage1_dark_selected'))
    click_text(d, '下一步：选择结果（%d）' % (stage1_state(d)['selected'] or 0))
    st2 = wait_stage2(d)
    r['stage2_dark'] = st2
    r['shots'].append(shot(d, 'p14_stage2_dark'))
    log('dark done %s' % st2)
    save_store(r)


SEGS = {
    'states': seg_states,
    'stage1': seg_stage1,
    'stage2': seg_stage2,
    'small': seg_small,
    'dark': seg_dark,
    'sortmenu': seg_sortmenu,
}


def run_seg(name):
    global STORE_
    STORE_ = load_store()
    log('=== segment %s ===' % name)
    d = driver()
    try:
        SEGS[name](d, STORE_)
        STORE_['segments'] = sorted(set(STORE_.get('segments', []) + [name]))
        STORE_.pop('error_' + name, None)
    except Exception:  # noqa: BLE001
        import traceback
        STORE_['error_' + name] = traceback.format_exc()[-2000:]
        log('segment %s FAILED' % name)
        print(traceback.format_exc()[-2000:], file=sys.stderr)
    finally:
        try:
            d.quit()
        except Exception:  # noqa: BLE001
            pass
        STORE_['health_before_delivery'] = health()
        save_store()


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else 'all'
    names = list(SEGS) if name == 'all' else [name]
    for n in names:
        run_seg(n)
    r = load_store()
    print(json.dumps({k: v for k, v in r.items() if k != 'api_snapshot'}, ensure_ascii=False, indent=2)[:5000])


if __name__ == '__main__':
    main()
