# -*- coding: utf-8 -*-
"""INT-1690 验收：维度抽屉「输入显示标签」编辑落库（写 DTO 补 param_name，隐藏 label 不再压过 paramName）。

覆盖：
  1) 创建时输入的「显示标签」落库（POST 请求体 + GET 回读）；
  2) 编辑「输入显示标签」→ PUT 请求体带 param_name 新值 → GET 回读新值；
  3) 重开抽屉用户可见值（浅/深色截图）；
  4) 输出字段「输出显示名」不回归。

同一脚本可对修复旁路容器（REACT_BASE=http://127.0.0.1:15290）与共享旧镜像 15173 双跑，
TAG 用于区分截图/结果文件。只写「接线测试_INT1690_」前缀数据，结束前删除并复核无残留。

用法：
  REACT_BASE=http://127.0.0.1:15290 TAG=fix python verify_int1690_label_persist.py
  REACT_BASE=http://127.0.0.1:15173 TAG=old python verify_int1690_label_persist.py
"""
import json, os, time, traceback
import urllib.request, urllib.error
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15290')
API = os.environ.get('API_BASE', 'http://127.0.0.1:15000')
TAG = os.environ.get('TAG', 'fix')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.environ.get('ART', os.path.join(HERE, 'artifacts', 'int1690'))
os.makedirs(ART, exist_ok=True)

STAMP = str(int(time.time()))[-6:]
NAME = '接线测试_INT1690_标签落库_' + STAMP
PREFIX = '接线测试_INT1690_'
SHEET = "//*[@data-slot='sheet-content']"
NEW_CREATE_LABEL = '创建显示标签A'
NEW_EDIT_LABEL = '编辑后标签C'
NEW_OUT_LABEL = '输出新标签C'
OUT_LABEL_CREATE = '评分结果'

RESULT = []

FETCH_PATCH = r"""
window.__fetchLog = [];
(function(){
  const orig = window.fetch;
  window.fetch = async function(input, init) {
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    const method = ((init && init.method) || (input && input.method) || 'GET').toUpperCase();
    const reqBody = (init && init.body && typeof init.body === 'string') ? init.body : null;
    let res;
    try { res = await orig.apply(this, arguments); }
    catch (e) {
      window.__fetchLog.push({url: url, method: method, status: 'ERR', error: String(e), reqBody: reqBody});
      throw e;
    }
    const entry = {url: url, method: method, status: res.status, reqBody: reqBody};
    try {
      const ct = res.headers.get('content-type') || '';
      if (ct.indexOf('json') !== -1) {
        entry.resBody = await res.clone().text();
      }
    } catch (e) {}
    window.__fetchLog.push(entry);
    return res;
  };
})();
"""


def log(step, ok, detail=None):
    RESULT.append({'step': step, 'ok': bool(ok), 'detail': detail})
    print(('PASS ' if ok else 'FAIL ') + step + ' :: ' +
          json.dumps(detail, ensure_ascii=False, default=str)[:1600], flush=True)


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
    path = os.path.join(ART, 'INT1690_%s_%s.png' % (name, TAG))
    drv.save_screenshot(path)
    return path


def clear_and_type(drv, el, text):
    js_click(drv, el)
    el.send_keys(Keys.CONTROL, 'a')
    el.send_keys(Keys.DELETE)
    if text:
        el.send_keys(text)


def fetch_log(drv):
    try:
        return drv.execute_script('return window.__fetchLog || []') or []
    except Exception:
        return []


def wait_net(drv, substr, method=None, timeout=150):
    end = time.time() + timeout
    while time.time() < end:
        hits = [n for n in fetch_log(drv) if substr in n.get('url', '')
                and (method is None or n.get('method') == method)]
        if hits:
            print('NET  %s %s -> %s' % (hits[-1].get('method'), hits[-1].get('url'), hits[-1].get('status')),
                  flush=True)
            return hits
        time.sleep(0.3)
    return []


def api_call(method, path, body=None, timeout=180):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + '/api/v1' + path, data=data, method=method,
                                 headers={'Content-Type': 'application/json'})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode('utf-8', 'replace')
            try:
                return r.status, json.loads(raw), round(time.time() - t, 2)
            except Exception:
                return r.status, raw, round(time.time() - t, 2)
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
        try:
            return e.code, json.loads(raw), round(time.time() - t, 2)
        except Exception:
            return e.code, raw, round(time.time() - t, 2)


def api_dims():
    st, body, _ = api_call('GET', '/evaluation/dimensions?per_page=1000')
    return (body or {}).get('data', {}).get('items', []) if isinstance(body, dict) else []


def detail(dim_id):
    st, body, _ = api_call('GET', '/evaluation/dimensions/%s' % dim_id)
    return (body or {}).get('data', {}) if isinstance(body, dict) else {}, st


def dim_by_name(name):
    hits = [d for d in api_dims() if d.get('name') == name]
    return hits[0] if hits else None


def health():
    try:
        with urllib.request.urlopen(API + '/health', timeout=10) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception as e:
        return {'error': str(e)}


def goto_eval(drv):
    drv.get(BASE + '/Evaluation')
    WebDriverWait(drv, 40).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    WebDriverWait(drv, 30).until(lambda d: d.execute_script(
        "return !!document.querySelector('table tbody tr') || document.body.innerText.indexOf('暂无评估维度')>=0"))
    time.sleep(1.2)


def open_create(drv):
    btn = one(drv, "//button[contains(normalize-space(.),'新增维度')]", timeout=20)
    js_click(drv, btn)
    WebDriverWait(drv, 20).until(lambda d: d.find_elements(By.ID, 'dim-name'))
    time.sleep(0.8)
    return one(drv, SHEET, timeout=15)


def search_dim(drv, keyword):
    inp = one(drv, "//input[@aria-label='搜索评估维度']", timeout=15)
    clear_and_type(drv, inp, keyword)
    time.sleep(1.3)


def row_edit(drv, name):
    el = one(drv, "//button[@aria-label='编辑维度 %s']" % name, timeout=25)
    js_click(drv, el)
    time.sleep(0.8)
    sh = one(drv, SHEET, timeout=15)
    WebDriverWait(drv, 30).until(lambda d: d.find_element(By.ID, 'dim-name').get_attribute('value') == name)
    return sh


def tab_click(drv, label, scope=SHEET):
    js_click(drv, one(drv, "%s//button[@role='tab'][normalize-space(.)='%s']" % (scope, label), timeout=15))
    time.sleep(0.6)


def submit(drv):
    js_click(drv, one(drv, SHEET + "//button[@type='submit' and @form='dimension-mutate-form']", timeout=15))


def label_value(sh, aria):
    els = sh.find_elements(By.XPATH, ".//input[@aria-label='%s']" % aria)
    return els[0].get_attribute('value') if els else None


def reopen_after_escape(drv):
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(1.0)


def phase_create(drv):
    sh = open_create(drv)
    clear_and_type(drv, sh.find_element(By.ID, 'dim-name'), NAME)
    tab_click(drv, 'API配置')
    clear_and_type(drv, one(drv, SHEET + "//input[@aria-label='输入参数键名 1']", timeout=15), 'q_text')
    clear_and_type(drv, one(drv, SHEET + "//input[@aria-label='输入显示标签 1']", timeout=15), NEW_CREATE_LABEL)
    clear_and_type(drv, one(drv, SHEET + "//input[@aria-label='输出字段代码 1']", timeout=15), 'score')
    clear_and_type(drv, one(drv, SHEET + "//input[@aria-label='输出显示名 1']", timeout=15), OUT_LABEL_CREATE)
    shot(drv, '10_create_form_light')
    t0 = time.time()
    submit(drv)
    hits = wait_net(drv, '/evaluation/dimensions', 'POST', timeout=150)
    elapsed = round(time.time() - t0, 2)
    time.sleep(1.5)
    hit = hits[-1] if hits else {}
    try:
        req = json.loads(hit.get('reqBody') or '{}')
    except Exception:
        req = {}
    req_in = (req.get('required_inputs') or [{}])[0]
    log('创建-1 抽屉提交 POST 请求体（输入/输出显示标签）', True,
        {'status': hit.get('status'), 'elapsed_s': elapsed,
         'req_input': {k: req_in.get(k) for k in ('key', 'param_name', 'label')},
         'req_output': {k: (req.get('output_fields') or [{}])[0].get(k) for k in ('param_code', 'param_name', 'label')}})
    dim = dim_by_name(NAME)
    if not dim:
        # 网关超时但服务端可能已落库
        time.sleep(6)
        dim = dim_by_name(NAME)
    if not dim:
        log('创建-2 维度创建后 API 可查', False, {'name': NAME})
        return None
    d, st = detail(dim['id'])
    ri = (d.get('required_inputs') or [{}])[0]
    of = (d.get('output_fields') or [{}])[0]
    log('创建-2 GET 回读：创建时输入的显示标签落库（param_name）',
        ri.get('param_name') == NEW_CREATE_LABEL,
        {'dim_id': dim['id'], 'status': st,
         'readback_input': {k: ri.get(k) for k in ('key', 'param_code', 'param_name', 'label')},
         'expect_param_name': NEW_CREATE_LABEL})
    log('创建-3 GET 回读：输出显示名落库（不回归）',
        of.get('param_name') == OUT_LABEL_CREATE,
        {'readback_output': {k: of.get(k) for k in ('param_code', 'param_name', 'label')}})
    shot(drv, '15_create_done_light')
    return dim['id']


def phase_edit(drv, dim_id):
    # 重新加载列表，避免创建请求超时/缓存导致新维度不在当前页
    goto_eval(drv)
    search_dim(drv, NAME)
    sh = row_edit(drv, NAME)
    tab_click(drv, 'API配置')
    before_in = label_value(sh, '输入显示标签 1')
    before_out = label_value(sh, '输出显示名 1')
    shot(drv, '20_edit_prefill_light')
    clear_and_type(drv, one(drv, SHEET + "//input[@aria-label='输入显示标签 1']", timeout=15), NEW_EDIT_LABEL)
    clear_and_type(drv, one(drv, SHEET + "//input[@aria-label='输出显示名 1']", timeout=15), NEW_OUT_LABEL)
    t0 = time.time()
    submit(drv)
    hits = wait_net(drv, '/evaluation/dimensions/', 'PUT', timeout=150)
    elapsed = round(time.time() - t0, 2)
    time.sleep(1.5)
    hit = hits[-1] if hits else {}
    try:
        req = json.loads(hit.get('reqBody') or '{}')
    except Exception:
        req = {}
    req_in = (req.get('required_inputs') or [{}])[0]
    req_out = (req.get('output_fields') or [{}])[0]
    log('编辑-1 PUT 请求体带输入 param_name 新值', req_in.get('param_name') == NEW_EDIT_LABEL,
        {'status': hit.get('status'), 'elapsed_s': elapsed,
         'req_input': {k: req_in.get(k) for k in ('key', 'param_name', 'label')},
         'req_output': {k: req_out.get(k) for k in ('param_code', 'param_name', 'label')}})
    d, st = detail(dim_id)
    ri = (d.get('required_inputs') or [{}])[0]
    of = (d.get('output_fields') or [{}])[0]
    ok_in = ri.get('param_name') == NEW_EDIT_LABEL
    ok_out = of.get('param_name') == NEW_OUT_LABEL
    log('编辑-2 GET 回读：输入显示标签 = 新值（本卡核心）', ok_in,
        {'ui_before': before_in, 'readback_param_name': ri.get('param_name'),
         'readback_label': ri.get('label'), 'expect': NEW_EDIT_LABEL})
    log('编辑-3 GET 回读：输出显示名 = 新值（不回归）', ok_out,
        {'ui_before': before_out, 'readback_param_name': of.get('param_name'),
         'readback_label': of.get('label'), 'expect': NEW_OUT_LABEL})
    shot(drv, '25_after_edit_light')
    return {'in': ok_in, 'out': ok_out}


def phase_reopen(drv):
    reopen_after_escape(drv)
    search_dim(drv, NAME)
    sh = row_edit(drv, NAME)
    tab_click(drv, 'API配置')
    val_in = label_value(sh, '输入显示标签 1')
    val_out = label_value(sh, '输出显示名 1')
    shot(drv, '30_reopen_light')
    log('重开-1 同页重开抽屉用户可见值（输入显示标签/输出显示名）',
        val_in == NEW_EDIT_LABEL and val_out == NEW_OUT_LABEL,
        {'reopen_input': val_in, 'reopen_output': val_out,
         'expected': [NEW_EDIT_LABEL, NEW_OUT_LABEL]})
    return val_in, val_out


def phase_dark(drv):
    reopen_after_escape(drv)
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark')")
    drv.get('about:blank')
    goto_eval(drv)
    search_dim(drv, NAME)
    sh = row_edit(drv, NAME)
    tab_click(drv, 'API配置')
    val_in = label_value(sh, '输入显示标签 1')
    dark = drv.execute_script(
        "return document.documentElement.classList.contains('dark') || "
        "getComputedStyle(document.body).backgroundColor")
    shot(drv, '35_reopen_dark')
    log('深色-1 深色下重开抽屉回显新值 + 深色样式生效',
        val_in == NEW_EDIT_LABEL and (dark is True or dark not in ('rgb(255, 255, 255)', None)),
        {'reopen_input': val_in, 'dark_marker': dark})
    reopen_after_escape(drv)
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode','light')")


def cleanup():
    dims = [d for d in api_dims() if str(d.get('name', '')).startswith(PREFIX)]
    deleted = []
    for d in dims:
        st, _, _ = api_call('DELETE', '/evaluation/dimensions/%s' % d['id'])
        deleted.append({'id': d['id'], 'name': d['name'], 'status': st})
    time.sleep(1.5)
    remain = [d['name'] for d in api_dims() if str(d.get('name', '')).startswith(PREFIX)]
    log('清理：删除本 run 自建维度并复核无残留', not remain,
        {'deleted': deleted, 'remain': remain})


def main():
    t0 = time.time()
    h0 = health()
    total0 = len(api_dims())
    log('环境-0 真实库栈健康与库名（开工）',
        h0.get('database') == 'intelligent_audio_test',
        {'base': BASE, 'tag': TAG, 'health': h0, 'dims_total': total0})
    drv = _driver()
    try:
        goto_eval(drv)
        log('环境-1 /Evaluation 首屏可用', True,
            {'rows_page1': len(drv.find_elements(By.CSS_SELECTOR, 'table tbody tr'))})
        dim_id = phase_create(drv)
        if dim_id:
            reopen_after_escape(drv)
            time.sleep(1.2)
            phase_edit(drv, dim_id)
            phase_reopen(drv)
            phase_dark(drv)
    except Exception:
        log('EXCEPTION', False, traceback.format_exc()[-2500:])
    finally:
        try:
            cleanup()
        except Exception:
            log('CLEANUP-EXCEPTION', False, traceback.format_exc()[-800:])
        h1 = health()
        log('环境-2 真实库栈健康与库名（收尾）',
            h1.get('database') == 'intelligent_audio_test',
            {'health': h1, 'dims_total': len(api_dims())})
        with open(os.path.join(ART, 'result_int1690_%s.json' % TAG), 'w', encoding='utf-8') as f:
            json.dump({'stamp': STAMP, 'tag': TAG, 'base': BASE,
                       'elapsed_s': round(time.time() - t0, 1), 'result': RESULT},
                      f, ensure_ascii=False, indent=1)
        try:
            drv.quit()
        except Exception:
            pass
    passed = sum(1 for r in RESULT if r['ok'])
    print('SUMMARY %s: %d/%d passed, elapsed %.1fs' % (TAG, passed, len(RESULT), time.time() - t0), flush=True)


if __name__ == '__main__':
    main()
