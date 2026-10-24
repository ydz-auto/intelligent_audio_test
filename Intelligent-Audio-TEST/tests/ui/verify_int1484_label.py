# -*- coding: utf-8 -*-
"""INT-1484 复测（只走一段）：维度抽屉「输入参数显示标签」保存回读。

前置：共享 15173 镜像已按 wiring/react@7efe4a37b 重建（INT-1713），含 INT-1690 修复。
口径（规划师 2026-10-24 裁定·第 2 轮）：精简载荷 ≤1 输入 + 1 输出 + 1 端点。

步骤：API 建夹具维度（1 输入 param_name=输入原名A / label=输入原标签B，1 输出，1 端点）
  → 抽屉 API配置 反填 → 改「输入显示标签」→ 保存 → PUT 请求体 → GET 回读 param_name
  → 同页重开抽屉回显 → 浅色 / 深色截图。其余窗沿用 2026-10-24 08:27 轮结论。
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
P = '接线测试_INT1484_LBL_' + STAMP
DIM = P + '_维度'
OLD_IN_NAME = '输入原名A'
OLD_IN_LABEL = '输入原标签B'
NEW_LABEL = '输入新标签C'
OUT_NAME = '输出原名A'
ENDPOINT = 'http://host.docker.internal:15000/health'

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


def wait_toast(drv, text, timeout=30):
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
    env('登录后 token 长度', {'len': len(token or '')})


def goto_eval(drv):
    drv.get(BASE + '/Evaluation')
    WebDriverWait(drv, 40).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    WebDriverWait(drv, 30).until(lambda d: d.execute_script(
        "return !!document.querySelector('table tbody tr') || document.body.innerText.indexOf('暂无评估维度')>=0"))
    time.sleep(1.2)


def search_dim(drv, keyword):
    inp = one(drv, "//input[@aria-label='搜索评估维度']", timeout=15)
    clear_and_type(drv, inp, keyword)
    time.sleep(1.4)


def row_button(drv, aria_label, timeout=60):
    el = one(drv, "//button[@aria-label='%s']" % aria_label, timeout=timeout)
    js_click(drv, el)
    time.sleep(0.8)


def detail(dim_id):
    st, body, dt = api_call('GET', '/evaluation/dimensions/%s' % dim_id)
    return (body or {}).get('data', {}) if isinstance(body, dict) else {}


def open_edit_drawer(drv):
    last = None
    for attempt in (1, 2):
        search_dim(drv, DIM)
        try:
            row_button(drv, '编辑维度 %s' % DIM, timeout=60)
            break
        except Exception as e:  # 后端写慢时列表可能滞后，重搜一次
            last = e
            if attempt == 2:
                shot(drv, 'L00_open_drawer_fail')
                raise
            time.sleep(3)
    sh = one(drv, SHEET, timeout=15)
    WebDriverWait(drv, 30).until(lambda x: x.find_element(By.ID, 'dim-name').get_attribute('value') == DIM)
    time.sleep(1.4)
    tab_click(drv, 'API配置')
    return sh


def read_label(sh):
    return sh.find_element(By.XPATH, ".//input[@aria-label='输入显示标签 1']").get_attribute('value')


def read_output_name(sh):
    return sh.find_element(By.XPATH, ".//input[@aria-label='输出显示名 1']").get_attribute('value')


def make_fixture():
    body = {
        'name': DIM, 'description': 'INT-1484 显示标签复测', 'type': 'auto', 'dimension_type': 'main',
        'category_id': None, 'status': True, 'weight': 5, 'result_type': 1,
        'result_min': 0, 'result_max': 100, 'decimal_places': 2, 'estimated_exec_time': 5,
        'rule': {'rules': [{'condition': '>=', 'value': 90, 'score': 10},
                           {'condition': '<', 'value': 70, 'score': 0}]},
        'required_inputs': [{'key': 'q_text', 'param_name': OLD_IN_NAME, 'label': OLD_IN_LABEL,
                             'field_type': 'text', 'required': True, 'default_value': '',
                             'description': '输入描述', 'ui_order': 1}],
        'output_fields': [{'param_code': 'score', 'param_name': OUT_NAME, 'label': '输出原标签B',
                           'field_path': 'score', 'field_type': 'number', 'output_role': 'main',
                           'agg_role': 'value', 'default_value': '', 'pass_threshold': None,
                           'visible_in_report': True, 'help_text': '', 'ui_order': 1}],
        'api_endpoints': [{'url': ENDPOINT, 'name': '在线端点', 'priority': 1,
                           'max_process': 5, 'max_timeout': 30, 'max_audio_duration': 60}],
        'api_settings': {'method': 'POST', 'timeout': 30000, 'headers': {}, 'bodyTemplate': {}},
    }
    st, resp, dt = api_call('POST', '/evaluation/dimensions', body)
    did = ((resp or {}).get('data') or {}).get('id') if isinstance(resp, dict) else None
    log('夹具：API 建维度（1 输入 / 1 输出 / 1 端点，POST）', st in (200, 201) and did is not None,
        {'status': st, 'elapsed_s': dt, 'id': did})
    if did is None:
        # 网关 60s 放弃但服务端仍落库是 INT-1666 已知行为：按名字回查，避免重复创建
        time.sleep(8)
        same = [d for d in api_dims() if d.get('name') == DIM]
        if same:
            did = same[0]['id']
            log('夹具：POST 未返 2xx（%ss）但服务端已落库，按名字回查命中' % dt, True,
                {'status': st, 'elapsed_s': dt, 'id': did})
        else:
            raise RuntimeError('夹具维度创建失败: %s' % json.dumps(resp, ensure_ascii=False)[:400])
    d = detail(did)
    ri = (d.get('required_inputs') or [{}])[0]
    log('夹具：建立后 GET 回读（输入 param_name / label 应分别为旧名 / 旧标签）',
        ri.get('param_name') == OLD_IN_NAME and ri.get('label') == OLD_IN_LABEL,
        {'param_name': ri.get('param_name'), 'label': ri.get('label'), 'key': ri.get('key') or ri.get('param_code')})
    return did


def phase_light(drv, dim_id):
    sh = open_edit_drawer(drv)
    before_in = read_label(sh)
    before_out = read_output_name(sh)
    shot(drv, 'L01_label_prefill_light')
    log('浅色-1 抽屉反填：显示标签为旧 param_name', before_in == OLD_IN_NAME,
        {'input_label': before_in, 'output_name': before_out,
         'expect_input': OLD_IN_NAME, 'expect_output': OUT_NAME})

    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='输入显示标签 1']"), NEW_LABEL)
    typed = read_label(sh)
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

    # 网关 60s 放弃但服务端仍落库是已知环境行为（INT-1666），这里以落库为准，轮询回读
    d2, waited = {}, 0.0
    tw = time.time()
    while time.time() - tw < 90:
        d2 = detail(dim_id)
        ri_tmp = (d2.get('required_inputs') or [{}])[0]
        if ri_tmp.get('param_name') == NEW_LABEL:
            break
        time.sleep(3)
        waited = round(time.time() - tw, 1)
    ri2 = (d2.get('required_inputs') or [{}])[0]
    of2 = (d2.get('output_fields') or [{}])[0]
    log('浅色-2 改「输入显示标签」→ PUT 请求体带新 param_name',
        bool(hits) and req_in.get('param_name') == NEW_LABEL,
        {'put_status': hit.get('status'), 'elapsed_s': elapsed, 'typed': typed,
         'gateway_timeout_60s': hit.get('status') in (400, 502, 504) and elapsed >= 59,
         'req_input': {k: req_in.get(k) for k in ('key', 'param_name', 'label')},
         'req_output': {k: req_out.get(k) for k in ('param_code', 'param_name', 'label')}})
    log('浅色-3 GET 回读：输入 param_name / label 均为新值',
        ri2.get('param_name') == NEW_LABEL and ri2.get('label') == NEW_LABEL,
        {'readback_input': {k: ri2.get(k) for k in ('key', 'param_code', 'param_name', 'label')},
         'readback_output': {k: of2.get(k) for k in ('param_code', 'param_name', 'label')},
         'expect': NEW_LABEL, 'poll_extra_s': waited})

    # 同页重开（不导航，避免导航清状态造成假通过）
    if drv.find_elements(By.XPATH, SHEET):
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(1.2)
    sh2 = open_edit_drawer(drv)
    after_in = read_label(sh2)
    after_out = read_output_name(sh2)
    shot(drv, 'L02_label_reopen_light')
    log('浅色-4 重开抽屉回显新值',
        after_in == NEW_LABEL and after_out == OUT_NAME,
        {'reopen_input_label': after_in, 'reopen_output_name': after_out,
         'expect': [NEW_LABEL, OUT_NAME]})
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(1.0)
    return {'req_ok': req_in.get('param_name') == NEW_LABEL,
            'get_ok': ri2.get('param_name') == NEW_LABEL,
            'reopen_ok': after_in == NEW_LABEL,
            'elapsed_s': elapsed}


def phase_dark(drv):
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark');")
    drv.get('about:blank')
    goto_eval(drv)
    time.sleep(1.5)
    sh = open_edit_drawer(drv)
    dark_in = read_label(sh)
    shot(drv, 'L03_label_reopen_dark')
    log('深色-5 同源 reload 后重开抽屉回显新值', dark_in == NEW_LABEL,
        {'dark_input_label': dark_in, 'expect': NEW_LABEL})
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(0.8)
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode','light');")
    drv.get('about:blank')
    goto_eval(drv)
    return dark_in


def phase_cleanup(dim_id):
    st, body, dt = api_call('DELETE', '/evaluation/dimensions/%s' % dim_id)
    time.sleep(1.0)
    remain = [d.get('name') for d in api_dims() if d.get('name') == DIM]
    total = len(api_dims())
    log('清理：删除夹具维度并复核 0 残留 + 列表回到基线',
        not remain and total == BASELINE_TOTAL,
        {'status': st, 'elapsed_s': dt, 'id': dim_id, 'remain': remain,
         'total_now': total, 'baseline': BASELINE_TOTAL,
         'note': '维度列表页为 per_page=1000 全量拉取 + 前端过滤，故以接口与总数复核残留'})


def main():
    global BASELINE_TOTAL, DIM
    t0 = time.time()
    drv = _driver()
    dim_id = None
    try:
        login(drv)
        goto_eval(drv)
        BASELINE_TOTAL = len(api_dims())
        log('开工基线：维度 %d 条' % BASELINE_TOTAL, BASELINE_TOTAL > 0, {'baseline': BASELINE_TOTAL})
        fid = os.environ.get('FIXTURE_ID')
        if fid:
            # 复用已建好的夹具（后端写慢时避免再付一次 60s 创建）
            dim_id = int(fid)
            BASELINE_TOTAL = max(BASELINE_TOTAL - 1, 0)  # 基线不含本卡夹具
            d0 = detail(dim_id)
            DIM = d0.get('name') or DIM
            ri0 = (d0.get('required_inputs') or [{}])[0]
            log('夹具：复用已有维度 %s' % DIM,
                ri0.get('param_name') == OLD_IN_NAME and ri0.get('label') == OLD_IN_LABEL,
                {'id': dim_id, 'param_name': ri0.get('param_name'), 'label': ri0.get('label')})
        else:
            dim_id = make_fixture()
        # 列表页是 per_page=1000 全量拉取 + 前端过滤，API 旁路建记录后需 reload 才能出现在表格里
        goto_eval(drv)
        light = phase_light(drv, dim_id)
        dark_in = phase_dark(drv)
        log('小结：显示标签保存→回读→重开回显 全链路（浅/深）',
            light['req_ok'] and light['get_ok'] and light['reopen_ok'] and dark_in == NEW_LABEL,
            {'light': light, 'dark_reopen': dark_in})
    except Exception:
        try:
            shot(drv, 'L99_exception')
        except Exception:
            pass
        log('EXCEPTION', False, traceback.format_exc()[-2500:])
    finally:
        try:
            if dim_id:
                phase_cleanup(dim_id)
        except Exception:
            log('CLEANUP-EXCEPTION', False, traceback.format_exc()[-900:])
        with open(os.path.join(ART, 'result_label.json'), 'w', encoding='utf-8') as f:
            json.dump({'stamp': STAMP, 'elapsed_s': round(time.time() - t0, 1),
                       'baseline_total': BASELINE_TOTAL, 'dim_id': dim_id,
                       'result': RESULT, 'env': ENV, 'net': NET},
                      f, ensure_ascii=False, indent=1)
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
