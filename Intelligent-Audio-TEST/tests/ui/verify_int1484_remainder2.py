# -*- coding: utf-8 -*-
"""INT-1484 评估域深走查·补走（第二段）：上一段在「离线健康测试」定位新维度时中断。

本段覆盖：输入参数「显示标签」保存回读核对、离线/无端点健康测试、空态/错误态、
取消重开、深色截图 12~17、维度删除闭环、数据清理。

口径同第一段：需求规划师 2026-10-24 裁定·第 2 轮精简载荷（≤1 输入 + 1 输出 + 1 端点）。
"""
import json, os, time, traceback
import urllib.request, urllib.error
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://localhost:15173')
API = os.environ.get('API_BASE', 'http://127.0.0.1:15000')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1484')
os.makedirs(ART, exist_ok=True)

STAMP = str(int(time.time()))[-6:]
P = '接线测试_INT1484_B_' + STAMP
DIM = P + '_维度'
OFFLINE_DIM = P + '_离线维度'
SEARCH_NONE = 'zzz_无匹配_1484'
NO_EP_DIM = os.environ.get('NO_EP_DIM', '拒识成功数量')
ONLINE_URL = 'http://host.docker.internal:15000/health'

RESULT, ENV, NET = [], [], []
BASELINE_TOTAL = None
SHEET = "//*[@data-slot='sheet-content']"

FETCH_PATCH = r"""
window.__fetchLog = [];
(function(){
  const orig = window.fetch;
  window.fetch = async function(input, init) {
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    const method = ((init && init.method) || (input && input.method) || 'GET').toUpperCase();
    let reqBody = (init && init.body && typeof init.body === 'string') ? init.body : null;
    let res;
    try {
      res = await orig.apply(this, arguments);
    } catch (e) {
      window.__fetchLog.push({url: url, method: method, status: 'ERR', error: String(e), reqBody: reqBody});
      throw e;
    }
    try {
      const entry = {url: url, method: method, status: res.status, reqBody: reqBody};
      const ct = res.headers.get('content-type') || '';
      if (ct.indexOf('json') !== -1 && url.indexOf('/evaluation') !== -1) {
        try { entry.resBody = await res.clone().text(); } catch (e) {}
      }
      window.__fetchLog.push(entry);
    } catch (e) {}
    return res;
  };
})();
"""


def log(step, ok, detail=''):
    RESULT.append({'step': step, 'ok': bool(ok), 'detail': detail})
    print(('PASS ' if ok else 'FAIL ') + step + ' :: ' +
          json.dumps(detail, ensure_ascii=False, default=str)[:1200], flush=True)


def env(step, detail=''):
    ENV.append({'step': step, 'detail': detail})
    print('ENV  ' + step + ' :: ' + json.dumps(detail, ensure_ascii=False, default=str)[:1200], flush=True)


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
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
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    if tuple(int(x) for x in ver.split('.') if x.isdigit())[0] == chrome_major:
                        drv_path = exe
                except ValueError:
                    continue
    service = Service(executable_path=drv_path) if drv_path else Service()
    drv = webdriver.Chrome(options=options, service=service)
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    return drv


def js_click(drv, el):
    drv.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", el)


def one(drv, expr, root=None, timeout=15):
    root = root or drv

    def _f(d):
        els = root.find_elements(By.XPATH, expr)
        return els[0] if els else False
    return WebDriverWait(drv, timeout).until(_f)


def shot(drv, name):
    path = os.path.join(ART, 'INT1484_' + name + '.png')
    drv.save_screenshot(path)
    return path


def fetch_log(drv):
    try:
        return drv.execute_script('return window.__fetchLog || []') or []
    except Exception:
        return []


def wait_net(drv, substr, method=None, timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        items = fetch_log(drv)
        hits = [n for n in items if substr in n.get('url', '')
                and (method is None or n.get('method') == method)]
        if hits:
            NET.extend(items)
            try:
                drv.execute_script('window.__fetchLog = [];')
            except Exception:
                pass
            return hits
        time.sleep(0.3)
    NET.extend(fetch_log(drv))
    return []


def wait_toast(drv, text, timeout=25):
    try:
        WebDriverWait(drv, timeout).until(
            lambda d: any(text in (e.text or '')
                          for e in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')))
        return True
    except Exception:
        return False


def clear_and_type(drv, el, text):
    js_click(drv, el)
    el.send_keys(Keys.CONTROL, 'a')
    el.send_keys(Keys.DELETE)
    if text:
        el.send_keys(text)


def tab_click(drv, label, scope=SHEET):
    js_click(drv, one(drv, "%s//button[@role='tab'][normalize-space(.)='%s']" % (scope, label), timeout=15))
    time.sleep(0.6)


def sheet(drv):
    return one(drv, SHEET, timeout=15)


def row_button(drv, aria_label):
    el = one(drv, "//button[@aria-label='%s']" % aria_label, timeout=25)
    js_click(drv, el)
    time.sleep(0.6)


def dialog(drv, title_contains):
    return one(drv, "//*[@data-slot='dialog-content'][.//*[@data-slot='dialog-title'][contains(.,'%s')]]"
               % title_contains, timeout=15)


def alert_dialog(drv, title_contains):
    return one(drv, "//*[@data-slot='alert-dialog-content'][.//*[@data-slot='alert-dialog-title'][contains(.,'%s')]]"
               % title_contains, timeout=15)


def tok():
    with open(os.path.join(ART, 'token.txt'), encoding='utf-8') as f:
        return f.read().strip()


def api_call(method, path, body=None, timeout=150):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + '/api/v1' + path, data=data, method=method,
                                 headers={'Authorization': 'Bearer ' + tok(),
                                          'Content-Type': 'application/json'})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode('utf-8')), round(time.time() - t, 2)
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
        try:
            return e.code, json.loads(raw), round(time.time() - t, 2)
        except Exception:
            return e.code, raw, round(time.time() - t, 2)


def api_dims():
    st, body, _ = api_call('GET', '/evaluation/dimensions?per_page=1000')
    return (body or {}).get('data', {}).get('items', []) if isinstance(body, dict) else []


def login(drv):
    drv.get(BASE + '/login')
    WebDriverWait(drv, 30).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)
    uname = WebDriverWait(drv, 15).until(
        lambda d: d.find_element(By.ID, 'username') if d.find_elements(By.ID, 'username') else False)
    uname.send_keys('接线测试_admin')
    drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    drv.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]").click()
    WebDriverWait(drv, 30).until(lambda d: '/login' not in d.current_url)
    time.sleep(2.5)
    token = drv.execute_script("return localStorage.getItem('iatp:auth:token:v1')")
    with open(os.path.join(ART, 'token.txt'), 'w', encoding='utf-8') as f:
        f.write(token or '')


def goto_eval(drv):
    drv.get(BASE + '/Evaluation')
    WebDriverWait(drv, 40).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    WebDriverWait(drv, 30).until(lambda d: d.execute_script(
        "return !!document.querySelector('table tbody tr') || document.body.innerText.indexOf('暂无评估维度')>=0"))
    time.sleep(1.2)


def page_metrics(drv):
    total = drv.execute_script(r"""
      const els=[...document.querySelectorAll('span')];
      const e=els.find(x=>/\u5171\s*\d+\s*\u6761/.test(x.textContent||''));
      return e?e.textContent.trim():'';
    """)
    return {'footer_total': total,
            'rows_page1': len(drv.find_elements(By.CSS_SELECTOR, 'table tbody tr'))}


def search_dim(drv, keyword):
    inp = one(drv, "//input[@aria-label='搜索评估维度']", timeout=15)
    clear_and_type(drv, inp, keyword)
    time.sleep(1.3)


def detail(dim_id):
    st, body, dt = api_call('GET', '/evaluation/dimensions/%s' % dim_id)
    return (body or {}).get('data', {}) if isinstance(body, dict) else {}


SLOW_STREAK = 0


def make_dim(name, endpoint_url, endpoint_name='端点'):
    """精简载荷建维度。裁定：单次 ≥60s 重试一次；连续 2 次 ≥60s 停跑。"""
    global SLOW_STREAK
    body = {
        'name': name, 'description': 'INT-1484 补走', 'type': 'auto', 'dimension_type': 'main',
        'category_id': None, 'status': True, 'weight': 5, 'result_type': 1,
        'result_min': 0, 'result_max': 100, 'decimal_places': 2, 'estimated_exec_time': 5,
        'rule': {'rules': [{'condition': '>=', 'value': 95, 'score': 10},
                           {'condition': '>=', 'value': 90, 'score': 9},
                           {'condition': '>=', 'value': 80, 'score': 8},
                           {'condition': '>=', 'value': 70, 'score': 7},
                           {'condition': '<', 'value': 70, 'score': 0}]},
        'required_inputs': [{'key': 'q_text', 'param_name': '输入原名A', 'label': '输入原标签B',
                             'field_type': 'text', 'required': True, 'default_value': '',
                             'description': '输入描述', 'ui_order': 1}],
        'output_fields': [{'param_code': 'score', 'param_name': '输出原名A', 'label': '输出原标签B',
                           'field_path': 'score', 'field_type': 'number', 'output_role': 'main',
                           'agg_role': 'value', 'default_value': '', 'pass_threshold': None,
                           'visible_in_report': True, 'help_text': '', 'ui_order': 1}],
        'api_endpoints': [{'url': endpoint_url, 'name': endpoint_name, 'priority': 1,
                           'max_process': 5, 'max_timeout': 30, 'max_audio_duration': 60}],
        'api_settings': {'method': 'POST', 'timeout': 30000, 'headers': {}, 'bodyTemplate': {}},
    }
    st, resp, dt = api_call('POST', '/evaluation/dimensions', body)
    did = ((resp or {}).get('data') or {}).get('id') if isinstance(resp, dict) else None
    log('建立夹具维度 %s（精简载荷 POST）' % name, st in (200, 201) and did is not None,
        {'status': st, 'elapsed_s': dt, 'id': did,
         'resp': json.dumps(resp, ensure_ascii=False)[:300] if not did else ''})
    if dt >= 60:
        SLOW_STREAK += 1
    else:
        SLOW_STREAK = 0
    if did is None:
        # 网关 60s 超时后服务端可能仍落库：先按名字回查，避免重复创建
        time.sleep(6)
        same = [d for d in api_dims() if d.get('name') == name]
        if same:
            did = same[0]['id']
            log('建立夹具维度-回查：60s 超时但服务端已落库（id=%s）' % did, True,
                {'id': did, 'elapsed_s': dt})
        elif SLOW_STREAK < 2:
            log('建立夹具维度-重试一次（首次 %ss）' % dt, True, {'first_elapsed_s': dt})
            st, resp, dt2 = api_call('POST', '/evaluation/dimensions', body)
            did = ((resp or {}).get('data') or {}).get('id') if isinstance(resp, dict) else None
            SLOW_STREAK = SLOW_STREAK + 1 if dt2 >= 60 else 0
            log('建立夹具维度-重试结果', st in (200, 201) and did is not None,
                {'status': st, 'elapsed_s': dt2, 'id': did})
        else:
            raise RuntimeError('连续 2 次写 ≥60s：按裁定停跑')
    return did


def phase_label_roundtrip(drv, dim_id):
    """输入「显示标签」/输出「显示名」保存回读核对（必填验收项）。"""
    d = detail(dim_id)
    ri = (d.get('required_inputs') or [{}])[0]
    of = (d.get('output_fields') or [{}])[0]
    log('参数回读-建立后 后端落库口径（param_name 取 param_name 还是 label）',
        True, {'input_param_name': ri.get('param_name'), 'input_label': ri.get('label'),
               'input_key': ri.get('key') or ri.get('param_code'),
               'output_param_name': of.get('param_name'), 'output_label': of.get('label')})

    search_dim(drv, DIM)
    row_button(drv, '编辑维度 %s' % DIM)
    sh = sheet(drv)
    WebDriverWait(drv, 30).until(lambda x: x.find_element(By.ID, 'dim-name').get_attribute('value') == DIM)
    time.sleep(1.4)
    tab_click(drv, 'API配置')
    before_in = sh.find_element(By.XPATH, ".//input[@aria-label='输入显示标签 1']").get_attribute('value')
    before_out = sh.find_element(By.XPATH, ".//input[@aria-label='输出显示名 1']").get_attribute('value')
    shot(drv, '20_label_prefill_light')
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='输入显示标签 1']"), '输入新标签C')
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='输出显示名 1']"), '输出新标签C')
    t0 = time.time()
    js_click(drv, one(drv, SHEET + "//button[@type='submit' and @form='dimension-mutate-form']", timeout=15))
    hits = wait_net(drv, '/evaluation/dimensions', 'PUT', timeout=150)
    elapsed = round(time.time() - t0, 2)
    wait_toast(drv, '成功', timeout=30)
    time.sleep(1.5)
    hit = hits[-1] if hits else {}
    try:
        req = json.loads(hit.get('reqBody') or '{}')
    except Exception:
        req = {}
    req_in = (req.get('required_inputs') or [{}])[0]
    req_out = (req.get('output_fields') or [{}])[0]
    d2 = detail(dim_id)
    ri2 = (d2.get('required_inputs') or [{}])[0]
    of2 = (d2.get('output_fields') or [{}])[0]
    log('参数回读-编辑「显示标签/显示名」后 PUT + GET',
        True,
        {'put_status': hit.get('status'), 'elapsed_s': elapsed,
         'ui_before': {'input': before_in, 'output': before_out},
         'req_input': {k: req_in.get(k) for k in ('key', 'label', 'param_name')},
         'req_output': {k: req_out.get(k) for k in ('param_code', 'label', 'param_name')},
         'readback_input': {k: ri2.get(k) for k in ('key', 'param_code', 'param_name', 'label')},
         'readback_output': {k: of2.get(k) for k in ('param_code', 'param_name', 'label')}})
    persisted_in = (ri2.get('param_name') == '输入新标签C')
    persisted_out = (of2.get('param_name') == '输出新标签C')
    log('参数回读-「显示标签」编辑是否落库（输入）', persisted_in,
        {'saved_param_name': ri2.get('param_name'), 'expect': '输入新标签C'})
    log('参数回读-「输出显示名」编辑是否落库（输出）', persisted_out,
        {'saved_param_name': of2.get('param_name'), 'expect': '输出新标签C'})

    # 重开抽屉看用户可见值（不导航，同页重开）
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(1.0)
    search_dim(drv, DIM)
    row_button(drv, '编辑维度 %s' % DIM)
    sh2 = sheet(drv)
    WebDriverWait(drv, 30).until(lambda x: x.find_element(By.ID, 'dim-name').get_attribute('value') == DIM)
    time.sleep(1.4)
    tab_click(drv, 'API配置')
    after_in = sh2.find_element(By.XPATH, ".//input[@aria-label='输入显示标签 1']").get_attribute('value')
    after_out = sh2.find_element(By.XPATH, ".//input[@aria-label='输出显示名 1']").get_attribute('value')
    shot(drv, '21_label_reopen_light')
    log('参数回读-重开抽屉的用户可见值（保存后）',
        after_in == '输入新标签C' and after_out == '输出新标签C',
        {'reopen_input_label': after_in, 'reopen_output_name': after_out,
         'expected': ['输入新标签C', '输出新标签C']})
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(0.8)
    return {'input_persisted': persisted_in, 'output_persisted': persisted_out,
            'reopen_input': after_in, 'reopen_output': after_out}


def open_health(drv, name):
    search_dim(drv, name)
    row_button(drv, '测试维度 %s 的 API' % name)
    dlg = dialog(drv, 'API健康测试结果')
    hits = wait_net(drv, '/health', 'GET', timeout=60)
    end = time.time() + 30
    txt = ''
    while time.time() < end:
        txt = dlg.text
        if '总状态' in txt or '暂无健康探测数据' in txt or '失败' in txt:
            break
        time.sleep(0.5)
    return dlg, hits, txt


def phase_health_online(drv, name, tag='light'):
    dlg, hits, txt = open_health(drv, name)
    rows = dlg.find_elements(By.CSS_SELECTOR, 'tbody tr')
    log('健康测试-1[%s] 在线端点 → 总状态在线' % tag,
        bool(hits) and '总状态' in txt and '在线' in txt,
        {'status': hits[-1]['status'] if hits else None,
         'resp': (hits[-1].get('resBody') or '')[:400] if hits else None,
         'rows': len(rows), 'dialog_text': txt[:400]})
    shot(drv, '07_health_online_' + tag)
    js_click(drv, dlg.find_element(By.XPATH, ".//button[normalize-space(.)='关闭']"))
    time.sleep(0.8)
    search_dim(drv, '')


def phase_health_offline(drv):
    goto_eval(drv)
    dlg, hits, txt = open_health(drv, OFFLINE_DIM)
    rows = dlg.find_elements(By.CSS_SELECTOR, 'tbody tr')
    log('健康测试-2 离线端点（不可达 127.0.0.1:59999）→ 总状态离线',
        bool(hits) and '总状态' in txt and '离线' in txt,
        {'status': hits[-1]['status'] if hits else None,
         'resp': (hits[-1].get('resBody') or '')[:500] if hits else None,
         'rows': len(rows), 'dialog_text': txt[:400]})
    shot(drv, '08_health_offline_light')
    js_click(drv, dlg.find_element(By.XPATH, ".//button[normalize-space(.)='关闭']"))
    time.sleep(0.8)
    search_dim(drv, '')


def phase_health_no_endpoint(drv):
    try:
        dlg, hits, txt = open_health(drv, NO_EP_DIM)
    except Exception as e:
        env('健康测试-3 无端点维度「%s」入口不可达' % NO_EP_DIM, {'error': str(e)[:300]})
        search_dim(drv, '')
        return
    rows = dlg.find_elements(By.CSS_SELECTOR, 'tbody tr')
    shot(drv, '09_health_no_endpoint_light')
    log('健康测试-3 无端点维度「%s」给出确定态' % NO_EP_DIM,
        ('总状态' in txt) or ('暂无健康探测数据' in txt),
        {'status': hits[-1]['status'] if hits else None,
         'resp': (hits[-1].get('resBody') or '')[:400] if hits else None,
         'rows': len(rows), 'dialog_text': txt[:400]})
    js_click(drv, dlg.find_element(By.XPATH, ".//button[normalize-space(.)='关闭']"))
    time.sleep(0.8)
    search_dim(drv, '')


def phase_empty_state(drv):
    search_dim(drv, SEARCH_NONE)
    time.sleep(1.2)
    body = drv.find_element(By.TAG_NAME, 'body').text
    log('空态：搜索无匹配 → 暂无评估维度', '暂无评估维度' in body, {'has_empty': '暂无评估维度' in body})
    shot(drv, '10_empty_state_light')
    search_dim(drv, '')


def phase_error_state(drv):
    drv.execute_cdp_cmd('Network.enable', {})
    drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': ['*/evaluation/dimensions*']})
    try:
        drv.refresh()
        WebDriverWait(drv, 40).until(lambda d: '加载失败' in d.find_element(By.TAG_NAME, 'body').text)
        body = drv.find_element(By.TAG_NAME, 'body').text
        has_retry = bool(drv.find_elements(By.XPATH, "//button[normalize-space(.)='请重试']"))
        log('错误态：阻断 /evaluation/dimensions → 加载失败 + 请重试',
            '加载失败' in body and has_retry, {'has_error': '加载失败' in body, 'has_retry': has_retry})
        shot(drv, '11_error_state_light')
    finally:
        drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': []})
    js_click(drv, one(drv, "//button[normalize-space(.)='请重试']", timeout=15))
    WebDriverWait(drv, 40).until(lambda d: d.find_elements(By.CSS_SELECTOR, 'table tbody tr'))
    log('错误态-2 请重试恢复列表', len(drv.find_elements(By.CSS_SELECTOR, 'table tbody tr')) > 0, {})
    time.sleep(1.2)


def phase_cancel_reopen(drv):
    js_click(drv, one(drv, "//button[normalize-space(.)='新增维度']", timeout=15))
    sh = sheet(drv)
    clear_and_type(drv, sh.find_element(By.ID, 'dim-name'), '临时输入_应清空')
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(1.2)
    closed = not bool(drv.find_elements(By.XPATH, SHEET))
    js_click(drv, one(drv, "//button[normalize-space(.)='新增维度']", timeout=15))
    sh2 = sheet(drv)
    value_after = sh2.find_element(By.ID, 'dim-name').get_attribute('value')
    log('取消重开-1 Esc 关闭后重开不残留上次输入', closed and value_after == '',
        {'closed_by_esc': closed, 'value_after_reopen': value_after})
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(1.0)
    js_click(drv, one(drv, "//button[normalize-space(.)='新增维度']", timeout=15))
    sh3 = sheet(drv)
    sh3.find_element(By.ID, 'dim-name').send_keys('遮罩测试')
    overlays = drv.find_elements(By.XPATH, "//*[@data-slot='sheet-overlay']")
    closed_overlay = False
    if overlays:
        from selenium.webdriver.common.action_chains import ActionChains
        ActionChains(drv).move_to_element_with_offset(overlays[0], -500, 0).click().perform()
        time.sleep(1.2)
        closed_overlay = not bool(drv.find_elements(By.XPATH, SHEET))
    log('取消重开-2 点遮罩关闭', closed_overlay,
        {'closed_by_overlay': closed_overlay, 'overlay_present': bool(overlays)})
    if not closed_overlay:
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(1.0)


def phase_rule_calc_dark(drv):
    search_dim(drv, DIM)
    row_button(drv, '规则试算维度 %s' % DIM)
    dlg = dialog(drv, '规则试算')
    clear_and_type(drv, dlg.find_element(By.ID, 'calc-value'), '92')
    js_click(drv, dlg.find_element(By.XPATH, ".//button[normalize-space(.)='试算']"))
    hits = wait_net(drv, '/calculate', 'POST', timeout=30)
    time.sleep(1.2)
    log('规则试算[dark] 92 → 评分 9 分',
        bool(hits) and '评分 9 分' in dlg.text,
        {'status': hits[-1]['status'] if hits else None, 'dialog_text': dlg.text[:300]})
    shot(drv, '16_rule_calc_dark')
    js_click(drv, dlg.find_element(By.XPATH, ".//button[normalize-space(.)='关闭']"))
    time.sleep(0.8)


def phase_dark(drv):
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark');")
    drv.get('about:blank')
    goto_eval(drv)
    time.sleep(1.2)
    shot(drv, '12_page_list_dark')
    tab_click(drv, '分组视图', scope="//*")
    time.sleep(1.4)
    shot(drv, '13_page_group_dark')
    tab_click(drv, '列表视图', scope="//*")
    time.sleep(0.8)
    js_click(drv, one(drv, "//button[normalize-space(.)='新增维度']", timeout=15))
    sh = sheet(drv)
    clear_and_type(drv, sh.find_element(By.ID, 'dim-name'), P + '_darkobj')
    shot(drv, '14_dimension_drawer_dark')
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(1.2)
    js_click(drv, one(drv, "//button[normalize-space(.)='新增分类']", timeout=15))
    time.sleep(1.0)
    shot(drv, '15_category_dialog_dark')
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(1.0)
    phase_rule_calc_dark(drv)
    phase_health_online(drv, DIM, tag='dark')
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode','light');")
    drv.get('about:blank')
    goto_eval(drv)


def phase_delete_dimension(drv, name):
    search_dim(drv, name)
    row_button(drv, '删除维度 %s' % name)
    dlg = alert_dialog(drv, '删除维度')
    dlg_text = dlg.text
    shot(drv, '19_delete_dimension_confirm_light')
    t0 = time.time()
    js_click(drv, dlg.find_element(By.XPATH, ".//button[normalize-space(.)='删除']"))
    hits = wait_net(drv, '/evaluation/dimensions', 'DELETE', timeout=120)
    elapsed = round(time.time() - t0, 2)
    time.sleep(1.5)
    still = [d for d in api_dims() if d.get('name') == name]
    log('维度删除闭环：确认弹窗 + DELETE + GET 回读（列表消失）',
        '确定要删除维度' in dlg_text and bool(hits) and not still,
        {'confirm_text': dlg_text[:160], 'status': hits[-1].get('status') if hits else None,
         'elapsed_s': elapsed, 'still_in_list': bool(still)})
    return not still


def phase_cleanup(drv):
    created = [d for d in api_dims() if d.get('name', '').startswith(P)]
    deleted = []
    for d in created:
        st, body, dt = api_call('DELETE', '/evaluation/dimensions/%s' % d['id'])
        deleted.append({'id': d['id'], 'name': d['name'], 'status': st, 'elapsed_s': dt})
    time.sleep(1.0)
    remain = [d.get('name') for d in api_dims() if d.get('name', '').startswith(P)]
    goto_eval(drv)
    m = page_metrics(drv)
    log('清理：删除本 run 自建维度并复核 0 残留 + 页脚回到基线',
        not remain and ' '.join(m['footer_total'].split()) == '共 %d 条' % BASELINE_TOTAL,
        {'deleted': deleted, 'remain': remain, 'footer': m['footer_total'],
         'baseline': BASELINE_TOTAL})


def main():
    global BASELINE_TOTAL
    t0 = time.time()
    drv = _driver()
    try:
        login(drv)
        goto_eval(drv)
        BASELINE_TOTAL = len(api_dims())
        log('开工基线：维度 %d 条' % BASELINE_TOTAL, BASELINE_TOTAL > 0, {'baseline': BASELINE_TOTAL})
        dim_id = make_dim(DIM, ONLINE_URL, '在线端点')
        off_id = make_dim(OFFLINE_DIM, 'http://127.0.0.1:59999/health', '不可达端点')
        goto_eval(drv)
        phase_label_roundtrip(drv, dim_id)
        phase_empty_state(drv)
        phase_error_state(drv)
        phase_cancel_reopen(drv)
        phase_health_offline(drv)
        phase_health_no_endpoint(drv)
        phase_dark(drv)
        phase_delete_dimension(drv, DIM)
        if off_id:
            st, body, dt = api_call('DELETE', '/evaluation/dimensions/%s' % off_id)
            log('删除离线夹具维度', st in (200, 204), {'status': st, 'elapsed_s': dt, 'id': off_id})
    except Exception:
        log('EXCEPTION', False, traceback.format_exc()[-2500:])
    finally:
        try:
            phase_cleanup(drv)
        except Exception:
            log('CLEANUP-EXCEPTION', False, traceback.format_exc()[-900:])
        with open(os.path.join(ART, 'result_remainder2.json'), 'w', encoding='utf-8') as f:
            json.dump({'stamp': STAMP, 'elapsed_s': round(time.time() - t0, 1),
                       'baseline_total': BASELINE_TOTAL, 'result': RESULT, 'env': ENV, 'net': NET},
                      f, ensure_ascii=False, indent=1)
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
