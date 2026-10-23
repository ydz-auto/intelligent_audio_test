# -*- coding: utf-8 -*-
"""INT-1486 复走（修复验收）：INT-1528 / INT-1542 / INT-1544 三卡修复后重走未覆盖项。

覆盖：
  A. 手动勾选 2 条用例 → 开始测试（INT-1542：弹窗必须打开）→ 提交 → POST /tasks case_ids 恰为勾选集
  B. 任务命名弹窗重置（INT-1528）：清空/自定名后取消、Esc 关闭，重开恢复默认名
  C. filter-all 按步骤一筛选圈定（INT-1544）：搜索 1 条 → 提交 case_ids 恰 1 条；空筛选入口拦截
  D. 四窗（task-name / case-detail / api-edit / api-health）浅色 + 深色截图
  E. 提交流程回读：GET /tasks/{id} 与 GET /tasks?keyword=

环境：前端 docker 15173（React），后端 docker 真实库 15000。
"""
import json, os, time, traceback, urllib.parse, urllib.request
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

BASE = 'http://localhost:15173'
API = 'http://127.0.0.1:15000'
ART = 'tests/ui/artifacts/int1486'
TOKEN_FILE = os.path.join(ART, 'token.txt')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
os.makedirs(ART, exist_ok=True)
SUFFIX = str(int(time.time()))[-6:]
TASK_MANUAL = '接线测试_INT1486_F手动_' + SUFFIX
TASK_FILTER = '接线测试_INT1486_F筛选_' + SUFFIX
API_NAME = '接线测试_INT1486_FAPI_' + SUFFIX
DEVICE_NAME = 'pura90gpt'
KEYWORD = 'JG0081'
EMPTY_KEYWORD = 'ZZZ_NO_MATCH_INT1486'

FETCH_PATCH = r"""
window.__fetchLog = [];
const __origFetch = window.fetch;
window.fetch = function(input, init) {
  let url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = (init && init.method) || (input && input.method) || 'GET';
  const entry = { url: String(url), method: method, status: null,
                  reqBody: init && init.body ? String(init.body).slice(0, 200000) : null, resBody: null };
  window.__fetchLog.push(entry);
  return __origFetch.apply(this, arguments).then(async function(res) {
    entry.status = res.status;
    try { entry.resBody = (await res.clone().text()).slice(0, 4000); } catch (e) {}
    return res;
  }).catch(function(e) { entry.status = 'ERR ' + e; throw e; });
};
"""

report = {'env': {}, 'checks': [], 'tasks': [], 'apis': [], 'defects': []}


def chk(name, ok, detail=''):
    report['checks'].append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:800]})
    print(('[PASS] ' if ok else '[FAIL] ') + name + (' | ' + str(detail)[:400] if detail else ''))
    return ok


def api_req(method, path, token, body=None, timeout=180):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    r = urllib.request.Request(API + path, data=data, method=method,
                               headers={'Authorization': 'Bearer ' + token,
                                        'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read().decode('utf-8')
            try:
                return resp.status, json.loads(raw)
            except Exception:
                return resp.status, raw[:500]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')[:500]


def make_driver(token):
    o = Options(); o.binary_location = CHROME_BINARY
    for a in ['--headless=new', '--window-size=1680,1050', '--disable-gpu', '--no-sandbox', '--lang=zh-CN',
              '--disable-dev-shm-usage', '--no-first-run', '--no-default-browser-check']:
        o.add_argument(a)
    import winreg
    major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache = r'D:\00_user_data\.cache\selenium\chromedriver\win64'
    path = ''
    if not os.path.isdir(cache):
        cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    if major and os.path.isdir(cache):
        for v in os.listdir(cache):
            exe = os.path.join(cache, v, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    if int([x for x in v.split('.') if x.isdigit()][0]) == major:
                        path = exe
                except (ValueError, IndexError):
                    continue
    d = webdriver.Chrome(options=o, service=Service(executable_path=path) if path else Service())
    d.set_script_timeout(120)
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
        'source': "try{localStorage.setItem('iatp:auth:token:v1', %s)}catch(e){}" % json.dumps(token)})
    return d


def js_click(d, el):
    d.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)


def text(d):
    return d.execute_script('return document.body.innerText') or ''


def wait_text(d, s, timeout=60):
    WebDriverWait(d, timeout).until(lambda x: s in text(x))
    return True


def shot(d, name):
    p = os.path.join(ART, name)
    d.save_screenshot(p)
    print('SHOT', name, os.path.getsize(p))


def dialogs(d):
    return [x for x in d.find_elements(By.CSS_SELECTOR, '[role="dialog"]') if x.is_displayed()]


def dialog_text(d):
    ds = dialogs(d)
    return '\n'.join(x.text for x in ds) if ds else ''


def close_dialog(d):
    for _ in range(3):
        try:
            d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        except Exception:
            pass
        time.sleep(1)
        if not dialogs(d):
            return True
    return not dialogs(d)


def log_mark(d):
    return len(d.execute_script('return window.__fetchLog || []'))


def log_entries(d, mark, keys=('/tasks', '/apis')):
    out = []
    for it in d.execute_script('return window.__fetchLog || []')[mark:]:
        if any(k in it['url'] for k in keys):
            out.append(it)
    return out


def log_show(d, mark, keys=('/tasks', '/apis'), maxn=40):
    out = log_entries(d, mark, keys)
    for it in out[:maxn]:
        print('REQ', it['method'], it['status'], it['url'])
        if it.get('reqBody') and it['method'] != 'GET':
            print('   BODY', it['reqBody'][:4000])
        if it.get('resBody') and it['method'] != 'GET':
            print('   RES ', it['resBody'][:400])
    return out


def wait_step1(d):
    d.get(BASE + '/start-test')
    wait_text(d, '按分组', 90)
    for _ in range(40):
        if d.find_elements(By.CSS_SELECTOR, '[aria-label^="全选分组 "]'):
            break
        time.sleep(2)
    time.sleep(2)


def search_cases(d, kw):
    inp = None
    for sel in ['input[placeholder="搜索用例名称或描述"]', "[aria-label='搜索用例']"]:
        els = [e for e in d.find_elements(By.CSS_SELECTOR, sel) if e.is_displayed()]
        if els:
            inp = els[0]
            break
    if inp is None:
        return False
    inp.send_keys(Keys.CONTROL, 'a'); inp.send_keys(Keys.DELETE)
    if kw:
        inp.send_keys(kw)
    time.sleep(6)
    return True


def summary_lines(d):
    return [ln for ln in text(d).splitlines() if '未选择用例时' in ln or ln.startswith('已选 ')]


def select_manual_cases(d, n=2):
    spans = d.find_elements(By.XPATH, "//span[normalize-space()='话轮接管']")
    if spans:
        js_click(d, spans[0]); time.sleep(3)
    for _ in range(20):
        if len(d.find_elements(By.CSS_SELECTOR, '[aria-label^="选择 "]')) >= n:
            break
        time.sleep(2)
    boxes = d.find_elements(By.CSS_SELECTOR, '[aria-label^="选择 "]')
    picked = []
    for b in boxes[:n]:
        js_click(d, b); time.sleep(0.6)
        picked.append(b.get_attribute('aria-label'))
    time.sleep(1.5)
    return picked


def next_step(d):
    js_click(d, d.find_elements(By.XPATH, "//button[normalize-space(.)='下一步']")[0])
    wait_text(d, '执行参数', 60)
    time.sleep(2)


def pick_device(d, name=DEVICE_NAME):
    for _ in range(20):
        cb = d.find_elements(By.CSS_SELECTOR, f'[aria-label="选择设备 {name}"]')
        if cb:
            js_click(d, cb[0]); time.sleep(1.2)
            return True
        time.sleep(1.5)
    return False


def click_start(d):
    st = d.find_elements(By.XPATH, "//button[normalize-space(.)='开始测试']")
    if not st:
        return False
    js_click(d, st[-1]); time.sleep(2.5)
    return True


def taskname_input(d):
    els = d.find_elements(By.CSS_SELECTOR, 'input#task-name')
    return els[0] if els else None


def set_input(d, el, value):
    el.send_keys(Keys.CONTROL, 'a'); el.send_keys(Keys.DELETE)
    if value:
        el.send_keys(value)
    time.sleep(0.6)


def stop_and_cleanup_task(d, token, task_id):
    print('STOP', api_req('POST', f'/api/v1/tasks/{task_id}/stop', token, {}))
    time.sleep(2)
    print('DEL', api_req('DELETE', f'/api/v1/tasks/{task_id}', token))
    print('PURGE', api_req('DELETE', f'/api/v1/tasks/{task_id}/purge', token))


def cleanup_apis(token):
    # 只删本 run 自建的 API（按记录 id），不按名称前缀扫库，避免误删同名/被改名的真实记录
    for it in report.get('apis', []):
        if it.get('id'):
            print('CLEAN api', it['id'], api_req('DELETE', f"/api/v1/apis/{it['id']}", token))


def cleanup_tasks(token):
    for name in (TASK_MANUAL, TASK_FILTER):
        st, tl = api_req('GET', '/api/v1/tasks?page=1&per_page=50&keyword=' + urllib.parse.quote(name), token)
        items = (tl.get('data', tl) or {}).get('items', []) if isinstance(tl, dict) else []
        for it in items:
            if it.get('name') == name:
                stop_and_cleanup_task(None, token, it['id'])


def find_task_payload(entries):
    for it in entries:
        if '/tasks' in it['url'] and it['method'] == 'POST' and 'start' not in it['url']:
            try:
                return json.loads(it['reqBody'] or '{}'), it
            except Exception:
                return {}, it
    return None, None


def main():
    token = open(TOKEN_FILE).read().strip()
    # ---------- 环境核对 1 ----------
    st, h = api_req('GET', '/health', token, timeout=20)
    report['env']['health1'] = h
    chk('env /health database=intelligent_audio_test', isinstance(h, dict) and h.get('database') == 'intelligent_audio_test', h)
    st, g = api_req('GET', '/api/v1/groups?page=1&per_page=200', token)
    st2, tc = api_req('GET', '/api/v1/testcases?page=1&per_page=5', token)
    _, tks = api_req('GET', '/api/v1/tasks?page=1&per_page=5', token)
    report['env']['groups_total'] = (g.get('data', g) or {}).get('total')
    report['env']['testcases_total'] = (tc.get('data', tc) or {}).get('total')
    report['env']['tasks_total'] = (tks.get('data', tks) or {}).get('total')
    print('ENV', report['env'])

    d = make_driver(token)
    state = {}
    try:
        # ================= A. 手动勾选 → 开始测试 → 弹窗（INT-1542） =================
        wait_step1(d)
        picked = select_manual_cases(d, 2)
        print('PICKED', picked)
        print('STEP1 summary', summary_lines(d))
        shot(d, 'F_manual_selected_light.png')
        chk('A1 手动勾选 2 条', len(picked) == 2, picked)

        next_step(d)
        dev_ok = pick_device(d)
        chk('A2 选中在线设备 ' + DEVICE_NAME, dev_ok)

        mark = log_mark(d)
        click_start(d)
        ti = taskname_input(d)
        chk('A3 手动勾选后任务命名弹窗打开（INT-1542）', ti is not None,
            'dialogs=%d body=%s' % (len(dialogs(d)), [ln for ln in text(d).splitlines() if '没有可用' in ln][:2]))
        if ti is None:
            shot(d, 'F_defect_manual_no_dialog.png')
            raise RuntimeError('INT-1542 not fixed on this build')
        default_name = ti.get_attribute('value')
        dtxt = dialog_text(d)
        print('A dialog summary:', [ln for ln in dtxt.splitlines() if '条' in ln][:4])
        chk('A4 默认任务名 = 测试任务_日期时间', default_name.startswith('测试任务_'), default_name)
        chk('A5 弹窗摘要用例数 = 2', '2 条' in dtxt, [ln for ln in dtxt.splitlines() if '条' in ln][:2])
        shot(d, 'F_taskname_manual_light.png')

        # ---------- B. 任务命名弹窗重置（INT-1528） ----------
        set_input(d, ti, '接线测试_INT1486_残留名')
        cancel = d.find_elements(By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='取消']")
        if cancel:
            js_click(d, cancel[0]); time.sleep(1.5)
        chk('B1 取消关闭弹窗', not dialogs(d))
        click_start(d)
        ti = taskname_input(d)
        v = ti.get_attribute('value') if ti else None
        chk('B2 自定义名取消后重开恢复默认名（INT-1528）', bool(v) and v.startswith('测试任务_'), repr(v))
        # 清空 → 取消 → 重开
        if ti:
            set_input(d, ti, '')
            cancel = d.find_elements(By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='取消']")
            if cancel:
                js_click(d, cancel[0]); time.sleep(1.5)
            click_start(d)
            ti = taskname_input(d)
            v2 = ti.get_attribute('value') if ti else None
            chk('B3 清空后取消重开恢复默认名', bool(v2) and v2.startswith('测试任务_'), repr(v2))
            sub = d.find_elements(By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='开始测试']")
            chk('B4 重开后主钮可用', bool(sub) and sub[0].get_attribute('disabled') is None,
                'disabled=%s' % (sub[0].get_attribute('disabled') if sub else None))

        # ---------- A6. 真实提交（手动集） ----------
        ti = taskname_input(d)
        set_input(d, ti, TASK_MANUAL)
        shot(d, 'F_taskname_filled_light.png')
        mark = log_mark(d)
        js_click(d, d.find_elements(By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='开始测试']")[0])
        time.sleep(12)
        entries = log_entries(d, mark, keys=('/tasks',))
        log_show(d, mark, keys=('/tasks',))
        payload, post = find_task_payload(entries)
        chk('A6 POST /tasks 成功', post is not None and post.get('status') == 201,
            (post or {}).get('status'))
        ids = (payload or {}).get('case_ids') or (payload or {}).get('test_case_ids') or []
        chk('A7 提交 case_ids 长度 = 手动勾选 2 条', len(ids) == 2, ids[:5])
        chk('A8 提交 name = ' + TASK_MANUAL, (payload or {}).get('name') == TASK_MANUAL, (payload or {}).get('name'))
        state['manual_payload'] = payload

        # ---------- E. 回读 ----------
        time.sleep(3)
        st, tl = api_req('GET', '/api/v1/tasks?page=1&per_page=50&keyword=' + urllib.parse.quote(TASK_MANUAL), token)
        items = (tl.get('data', tl) or {}).get('items', []) if isinstance(tl, dict) else []
        task = next((x for x in items if x.get('name') == TASK_MANUAL), None)
        chk('E1 任务列表回读命中', task is not None, json.dumps(task, ensure_ascii=False)[:300] if task else 'NOT FOUND')
        if task:
            state['task_manual'] = task.get('id')
            st, td = api_req('GET', f"/api/v1/tasks/{task['id']}", token)
            body = td.get('data', td) if isinstance(td, dict) else {}
            chk('E2 GET /tasks/{id} total_cases = 2', body.get('total_cases') == 2,
                {'id': body.get('id'), 'name': body.get('name'), 'total_cases': body.get('total_cases')})
            report['tasks'].append({'id': task['id'], 'name': TASK_MANUAL, 'detail': body})
            # 立即停（真实设备不跑），保留记录供 case-detail 取证，run 末统一删除
            print('STOP manual', api_req('POST', f"/api/v1/tasks/{task['id']}/stop", token, {}))
            time.sleep(2)

        # ---------- D1. case-detail-dialog 浅色（任务详情页共用同一组件） ----------
        if state.get('task_manual'):
            d.get(BASE + f"/tasks/{state['task_manual']}")
            time.sleep(7)
            rows = [e for e in d.find_elements(By.TAG_NAME, 'button')
                    if '测试用例_' in (e.text or '') or 'JG0081' in (e.text or '')]
            print('MANUAL task detail rows', len(rows))
            if rows:
                js_click(d, rows[0]); time.sleep(5)
                ct = dialog_text(d)
                chk('D1 case-detail 弹窗渲染（执行日志/评估中）', ('执行日志' in ct) or ('评估中' in ct), ct[:300])
                shot(d, 'F_case_detail_light.png')
                close_dialog(d)
            d.get(BASE + '/start-test')
            wait_text(d, '按分组', 90)

        # ================= C. filter-all 按筛选圈定（INT-1544） =================
        wait_step1(d)
        ok_search = search_cases(d, KEYWORD)
        lines = summary_lines(d)
        print('C summary', lines)
        chk('C1 搜索 %s 后筛选汇总出现' % KEYWORD, ok_search and bool(lines), lines)
        m = next((ln for ln in lines if '全部' in ln), '')
        chk('C2 界面「全部 1 条用例」', '全部 1 条' in m, m)
        shot(d, 'F_filter_all_light.png')

        next_step(d)
        pick_device(d)
        mark = log_mark(d)
        click_start(d)
        ti = taskname_input(d)
        dtxt = dialog_text(d)
        chk('C3 filter-all 任务命名弹窗打开', ti is not None, dtxt[:200])
        chk('C4 弹窗摘要用例数 = 1（与界面同源）', '1 条' in dtxt, [ln for ln in dtxt.splitlines() if '条' in ln][:2])
        set_input(d, ti, TASK_FILTER)
        mark = log_mark(d)
        js_click(d, d.find_elements(By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='开始测试']")[0])
        time.sleep(12)
        entries = log_entries(d, mark, keys=('/tasks',))
        log_show(d, mark, keys=('/tasks',))
        payload, post = find_task_payload(entries)
        ids = (payload or {}).get('case_ids') or (payload or {}).get('test_case_ids') or []
        chk('C5 POST /tasks 201', post is not None and post.get('status') == 201, (post or {}).get('status'))
        chk('C6 提交 case_ids 长度 = 1（不再回退全库 579）', len(ids) == 1, ids[:5])
        report['env']['filter_case_ids'] = ids
        time.sleep(3)
        st, tl = api_req('GET', '/api/v1/tasks?page=1&per_page=50&keyword=' + urllib.parse.quote(TASK_FILTER), token)
        items = (tl.get('data', tl) or {}).get('items', []) if isinstance(tl, dict) else []
        task = next((x for x in items if x.get('name') == TASK_FILTER), None)
        if task:
            state['task_filter'] = task.get('id')
            st, td = api_req('GET', f"/api/v1/tasks/{task['id']}", token)
            body = td.get('data', td) if isinstance(td, dict) else {}
            chk('C7 回读 total_cases = 1', body.get('total_cases') == 1,
                {'id': body.get('id'), 'total_cases': body.get('total_cases')})
            report['tasks'].append({'id': task['id'], 'name': TASK_FILTER, 'detail': body})
            print('STOP filter-all', api_req('POST', f"/api/v1/tasks/{task['id']}/stop", token, {}))
            time.sleep(2)

        # C8 空筛选拦截
        wait_step1(d)
        search_cases(d, EMPTY_KEYWORD)
        lines = summary_lines(d)
        print('C8 summary', lines)
        pick_device(d)
        mark = log_mark(d)
        click_start(d)
        t = text(d)
        chk('C8 空筛选入口拦截（无请求、提示调整筛选）',
            not any('/tasks' in e['url'] and e['method'] == 'POST' for e in log_entries(d, mark, keys=('/tasks',)))
            and '没有可用的测试用例' in t, [ln for ln in t.splitlines() if '没有可用' in ln][:2])
        shot(d, 'F_filter_empty_blocked_light.png')

        # ================= D2/D3. api-edit / api-health =================
        st, hc = api_req('POST', '/api/v1/apis', token, {
            'name': API_NAME, 'description': 'INT-1486 复走临时', 'algorithm_type': 'voice_llm',
            'default_max_process': 5,
            'endpoints': [{'endpoint': 'https://example.test/int1486-f', 'name': None, 'max_process': 1,
                           'max_timeout': 30, 'max_audio_duration': 60, 'status': 'online', 'priority': 1,
                           'description': None}]})
        api_id = None
        if isinstance(hc, dict):
            api_id = (hc.get('data') or {}).get('id') or hc.get('id')
        chk('D3 临时 API 创建', st < 300 and api_id is not None, {'status': st, 'id': api_id})
        state['api_id'] = api_id
        report['apis'].append({'id': api_id, 'name': API_NAME})

        wait_step1(d)
        if api_id:
            card_btn = d.find_elements(By.CSS_SELECTOR, f'[aria-label="选择 API {API_NAME}"]')
            chk('D4 API 卡片出现', bool(card_btn), len(card_btn))
            if card_btn:
                card = d.execute_script('''
                  let n = arguments[0];
                  while (n && n !== document.body) {
                    if (n.getAttribute && n.getAttribute('data-slot') === 'card') return n;
                    n = n.parentElement;
                  }
                  return arguments[0].parentElement;
                ''', card_btn[0])
                more = card.find_elements(By.CSS_SELECTOR, '[aria-label="更多操作"]')
                if more:
                    mark = log_mark(d)
                    js_click(d, more[0]); time.sleep(1.2)
                    mi = d.find_elements(By.XPATH, "//*[@role='menuitem' and normalize-space(.)='编辑']")
                    js_click(d, mi[0]); time.sleep(2)
                    back = d.find_element(By.ID, 'api-name').get_attribute('value')
                    urls = d.find_elements(By.CSS_SELECTOR, "input[aria-label='端点 URL']")
                    back_url = urls[0].get_attribute('value') if urls else None
                    chk('D5 api-edit 回填名称', back == API_NAME, repr(back))
                    chk('D6 api-edit 回填端点 URL', back_url == 'https://example.test/int1486-f', repr(back_url))
                    shot(d, 'F_api_edit_light.png')
                    close_dialog(d)
            # api-health
            hb = d.find_elements(By.CSS_SELECTOR, f'[aria-label="连接测试 {API_NAME}"]')
            if hb:
                mark = log_mark(d)
                js_click(d, hb[0]); time.sleep(0.6)
                print('HEALTH testing', dialog_text(d)[:200].replace('\n', ' | '))
                try:
                    WebDriverWait(d, 90).until(lambda x: '重新测试' in dialog_text(x) or not dialogs(x))
                except Exception:
                    pass
                ht = dialog_text(d)
                print('HEALTH result', ht[:600].replace('\n', ' | '))
                chk('D7 api-health 结果态渲染（重新测试钮）', '重新测试' in ht, ht[:300])
                shot(d, 'F_api_health_light.png')
                log_show(d, mark, keys=('/apis/', 'health'))
                close_dialog(d)

        # ================= D 深色四窗 =================
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark')")
        wait_step1(d)
        time.sleep(2)
        chk('D8 深色主题生效', d.execute_script("return document.documentElement.classList.contains('dark')") is True,
            d.execute_script("return document.documentElement.className"))
        # task-name 深色
        select_manual_cases(d, 1)
        next_step(d)
        pick_device(d)
        click_start(d)
        ti = taskname_input(d)
        if ti:
            shot(d, 'F_taskname_dark.png')
            close_dialog(d)
        # api-edit 深色
        if api_id:
            cb = d.find_elements(By.CSS_SELECTOR, f'[aria-label="选择 API {API_NAME}"]')
            if cb:
                card = d.execute_script('''
                  let n = arguments[0];
                  while (n && n !== document.body) {
                    if (n.getAttribute && n.getAttribute('data-slot') === 'card') return n;
                    n = n.parentElement;
                  }
                  return arguments[0].parentElement;
                ''', cb[0])
                more = card.find_elements(By.CSS_SELECTOR, '[aria-label="更多操作"]')
                if more:
                    js_click(d, more[0]); time.sleep(1.2)
                    mi = d.find_elements(By.XPATH, "//*[@role='menuitem' and normalize-space(.)='编辑']")
                    js_click(d, mi[0]); time.sleep(2)
                    shot(d, 'F_api_edit_dark.png')
                    close_dialog(d)
            hb = d.find_elements(By.CSS_SELECTOR, f'[aria-label="连接测试 {API_NAME}"]')
            if hb:
                js_click(d, hb[0])
                try:
                    WebDriverWait(d, 90).until(lambda x: '重新测试' in dialog_text(x) or not dialogs(x))
                except Exception:
                    pass
                time.sleep(1)
                shot(d, 'F_api_health_dark.png')
                close_dialog(d)

        # case-detail 深色：任务详情页（与报告域共用同组件）
        if state.get('task_filter'):
            d.get(BASE + f"/tasks/{state['task_filter']}")
            time.sleep(7)
            rows = [e for e in d.find_elements(By.TAG_NAME, 'button')
                    if '测试用例_' in (e.text or '') or 'JG0081' in (e.text or '')]
            print('FILTER task detail rows', len(rows))
            if rows:
                js_click(d, rows[0]); time.sleep(5)
                cdt = dialog_text(d)
                chk('D9 case-detail 深色渲染（执行日志/评估中）',
                    ('执行日志' in cdt) or ('评估中' in cdt), cdt[:300])
                shot(d, 'F_case_detail_dark.png')
                close_dialog(d)
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','light')")

    except Exception:
        traceback.print_exc()
        shot(d, 'F_error.png')
    finally:
        d.quit()
        # ---------- 清理 ----------
        try:
            cleanup_tasks(token)
            cleanup_apis(token)
            st, apis = api_req('GET', '/api/v1/apis?per_page=1000', token)
            residue_a = [x for x in (apis.get('data', apis) or {}).get('items', []) if '接线测试_INT1486' in (x.get('name') or '')]
            st, tl = api_req('GET', '/api/v1/tasks?page=1&per_page=50&keyword=' + urllib.parse.quote('接线测试_INT1486'), token)
            residue_t = [x for x in (tl.get('data', tl) or {}).get('items', []) if '接线测试_INT1486' in (x.get('name') or '')]
            report['residue'] = {'apis': residue_a, 'tasks': residue_t}
            print('RESIDUE apis', residue_a, 'tasks', residue_t)
        except Exception:
            traceback.print_exc()
        # ---------- 环境核对 3 ----------
        st, h3 = api_req('GET', '/health', token, timeout=20)
        report['env']['health3'] = h3
        report['env']['task_manual'] = TASK_MANUAL
        report['env']['task_filter'] = TASK_FILTER
        report['env']['api_name'] = API_NAME
        with open(os.path.join(ART, 'rewalk_f_report.json'), 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print('REPORT', os.path.join(ART, 'rewalk_f_report.json'))
        print('SUMMARY', json.dumps({'checks': len(report['checks']),
                                     'failed': [c['name'] for c in report['checks'] if not c['ok']],
                                     'env': report['env'], 'residue': report.get('residue')},
                                    ensure_ascii=False)[:2000])


if __name__ == '__main__':
    main()
