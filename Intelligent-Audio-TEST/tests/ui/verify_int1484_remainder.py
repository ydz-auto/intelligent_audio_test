# -*- coding: utf-8 -*-
"""INT-1484 评估域深走查·补走（真实库栈：前端 15173 / 后端 15000）。

口径：需求规划师 2026-10-24 裁定·第 2 轮「放行精简载荷」——
每次 POST/PUT ≤1 输入参数 + 1 输出参数 + 1 端点（不关联算法），耗时只记录不作门禁。

本轮只补上一轮未完成项（不重做已完成的 4 个模态窗首屏）：
编辑保存 PUT 闭环、维度删除闭环、规则试算、健康测试(在线/离线/无端点)、
空态/错误态、取消重开、深色截图 12~17。

数据纪律：只写「接线测试_INT1484_」前缀记录，run 结束前删除并回读 0 残留。
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
P = '接线测试_INT1484_' + STAMP
DIM = P + '_维度'
DIM_EDIT = DIM + '_改'
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
      if (ct.indexOf('json') !== -1 && (url.indexOf('/evaluation') !== -1 ||
          url.indexOf('/algorithm/options') !== -1)) {
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


# ---------- 通用 ----------

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


def trigger_by_label(drv, label_text, scope=SHEET):
    return one(drv, "%s//label[contains(normalize-space(.), '%s')]"
                    "/following::button[@role='combobox'][1]" % (scope, label_text), timeout=10)


def select_open(drv, label_text, scope=SHEET):
    trig = trigger_by_label(drv, label_text, scope)
    js_click(drv, trig)
    time.sleep(0.5)
    return trig


def close_popup(drv):
    try:
        js_click(drv, one(drv, SHEET + "//*[@data-slot='sheet-title']", timeout=5))
    except Exception:
        try:
            drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        except Exception:
            pass
    time.sleep(0.4)


def select_options(drv, label_text, scope=SHEET):
    select_open(drv, label_text, scope)
    time.sleep(0.3)
    labels = [i.text.strip() for i in drv.find_elements(By.XPATH, "//*[@data-slot='select-item']")]
    close_popup(drv)
    return labels


def select_choose(drv, label_text, option_text, scope=SHEET):
    select_open(drv, label_text, scope)
    opt = one(drv, "//*[@data-slot='select-item'][normalize-space(.)='%s']" % option_text, timeout=10)
    js_click(drv, opt)
    time.sleep(0.4)


def tab_click(drv, label, scope=SHEET):
    js_click(drv, one(drv, "%s//button[@role='tab'][normalize-space(.)='%s']" % (scope, label), timeout=10))
    time.sleep(0.6)


def sheet(drv):
    return one(drv, SHEET, timeout=15)


def row_button(drv, aria_label):
    el = one(drv, "//button[@aria-label='%s']" % aria_label, timeout=20)
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


def api_cats():
    st, body, _ = api_call('GET', '/evaluation/categories?per_page=100')
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
    time.sleep(1.0)


def page_metrics(drv):
    total = drv.execute_script(r"""
      const els=[...document.querySelectorAll('span')];
      const e=els.find(x=>/\u5171\s*\d+\s*\u6761/.test(x.textContent||''));
      return e?e.textContent.trim():'';
    """)
    return {'footer_total': total,
            'rows_page1': len(drv.find_elements(By.CSS_SELECTOR, 'table tbody tr'))}


def search_dim(drv, keyword):
    inp = one(drv, "//input[@aria-label='搜索评估维度']", timeout=10)
    clear_and_type(drv, inp, keyword)
    time.sleep(1.2)


def verify_dim_readback(name):
    dims = api_dims()
    mine = [d for d in dims if d.get('name') == name]
    if not mine:
        log('维度回读：列表 GET 未找到 %s' % name, False, {'count': len(dims)})
        return None
    d = mine[0]
    st, body, dt = api_call('GET', '/evaluation/dimensions/%s' % d['id'])
    detail = (body or {}).get('data', {}) if isinstance(body, dict) else {}
    ri = detail.get('required_inputs') or []
    of = detail.get('output_fields') or []
    ep = detail.get('api_endpoints') or []
    return {
        'id': d['id'], 'status': st, 'elapsed_s': dt,
        'name': detail.get('name'), 'desc': detail.get('description'),
        'category_id': detail.get('category_id'), 'keywords': detail.get('keywords'),
        'rule_count': len((detail.get('rule') or {}).get('rules') or []),
        'inputs': [(x.get('param_code'), x.get('param_name'), x.get('default_value')) for x in ri],
        'outputs': [(x.get('param_code'), x.get('field_path'), x.get('pass_threshold')) for x in of],
        'endpoints': [(x.get('url'), x.get('name')) for x in ep],
        'algorithms': [a.get('algorithm_type') for a in (detail.get('associated_algorithms') or [])],
        'result_type': detail.get('result_type'), 'result_min': detail.get('result_min'),
        'result_max': detail.get('result_max'),
    }


# ---------- 维度抽屉（精简载荷） ----------

def open_create_drawer(drv):
    js_click(drv, one(drv, "//button[normalize-space(.)='新增维度']", timeout=15))
    sh = sheet(drv)
    title = sh.find_element(By.XPATH, ".//*[@data-slot='sheet-title']").text.strip()
    tabs = [t.text.strip() for t in sh.find_elements(By.XPATH, ".//button[@role='tab']")]
    return sh, title, tabs


def count_aria(sh, prefix):
    return len(sh.find_elements(By.XPATH, ".//input[@aria-label[starts-with(.,'%s')]]" % prefix))


def fill_dimension_minimal(drv, sh, name, cat_name):
    clear_and_type(drv, sh.find_element(By.ID, 'dim-name'), name)
    clear_and_type(drv, sh.find_element(By.ID, 'dim-description'), 'INT-1484 复走维度描述')
    cat_opts = select_options(drv, '所属分类')
    select_choose(drv, '所属分类', cat_name)
    cat_text = trigger_by_label(drv, '所属分类').text.strip()
    log('维度抽屉-1 精简载荷建立：名称/描述/所属分类（选项数 = 接口分类数 + 2）',
        len(cat_opts) == len(api_cats()) + 2 and cat_text == cat_name,
        {'options': cat_opts, 'selected': cat_text, 'api_categories': len(api_cats())})

    tab_click(drv, '结果配置')
    clear_and_type(drv, sh.find_element(By.ID, 'dim-result-min'), '0')
    clear_and_type(drv, sh.find_element(By.ID, 'dim-result-max'), '100')

    tab_click(drv, 'API配置')
    clear_and_type(drv, sh.find_element(By.ID, 'dim-api-url'), ONLINE_URL)
    clear_and_type(drv, sh.find_element(By.ID, 'dim-api-headers'), '{"content-type": "application/json"}')

    # 输入参数：默认 2 行 → 改第1行(改) → 删第2行(删) → 增回(增) → 删回 1 行
    n0 = count_aria(sh, '输入参数键名')
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='输入参数键名 1']"), 'q_text')
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='输入显示标签 1']"), '提问文本')
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='输入默认值 1']"), '你好')
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='输入描述 1']"), '输入描述')
    js_click(drv, one(drv, SHEET + "//button[@aria-label='删除输入 %d']" % n0, timeout=15))
    time.sleep(0.5)
    n1 = count_aria(sh, '输入参数键名')
    js_click(drv, one(drv, SHEET + "//button[normalize-space(.)='添加输入']", timeout=15))
    time.sleep(0.5)
    n2 = count_aria(sh, '输入参数键名')
    js_click(drv, one(drv, SHEET + "//button[@aria-label='删除输入 %d']" % n2, timeout=15))
    time.sleep(0.5)
    n3 = count_aria(sh, '输入参数键名')
    log('维度抽屉-2 输入参数逐项增/删/改（%d→%d→%d→%d，末态 1 条）' % (n0, n1, n2, n3),
        [n0, n1, n2, n3] == [2, 1, 2, 1],
        {'counts': [n0, n1, n2, n3],
         'row1': [sh.find_element(By.XPATH, ".//input[@aria-label='%s 1']" % x).get_attribute('value')
                  for x in ('输入参数键名', '输入显示标签', '输入默认值', '输入描述')]})

    # 输出字段：默认 1 行 → 改第1行(改) → 增(增) → 删(删) → 1 行
    m0 = count_aria(sh, '输出字段代码')
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='输出字段代码 1']"), 'score')
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='输出显示名 1']"), '评分')
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='输出提取路径 1']"), 'data.score')
    js_click(drv, one(drv, SHEET + "//button[normalize-space(.)='添加字段']", timeout=15))
    time.sleep(0.5)
    m1 = count_aria(sh, '输出字段代码')
    js_click(drv, one(drv, SHEET + "//button[@aria-label='删除输出字段 %d']" % m1, timeout=15))
    time.sleep(0.5)
    m2 = count_aria(sh, '输出字段代码')
    log('维度抽屉-3 输出字段逐项增/删/改（%d→%d→%d，末态 1 条）' % (m0, m1, m2),
        [m0, m1, m2] == [1, 2, 1],
        {'counts': [m0, m1, m2],
         'row1': [sh.find_element(By.XPATH, ".//input[@aria-label='%s 1']" % x).get_attribute('value')
                  for x in ('输出字段代码', '输出显示名', '输出提取路径')]})

    # 端点：默认 1 行，填在线端点
    e0 = count_aria(sh, '端点 URL')
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='端点 URL 1']"), ONLINE_URL)
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='端点名称 1']"), '在线端点')
    log('维度抽屉-4 端点（默认 %d 行，精简载荷保留 1 个在线端点）' % e0, e0 == 1, {'endpoints': e0})

    # 关联算法：只看选项来源，不选（精简载荷不关联算法）
    tab_click(drv, '关联算法')
    js_click(drv, one(drv, SHEET + "//button[contains(normalize-space(.),'选择关联的算法类型')]", timeout=15))
    time.sleep(0.9)
    pops = drv.find_elements(By.CSS_SELECTOR, "[data-slot='popover-content']")
    pop_txt = pops[-1].text if pops else ''
    boxes = drv.find_elements(By.XPATH, "//*[@role='checkbox' and starts-with(@aria-label,'关联算法 ')]")
    log('维度抽屉-5 关联算法选项来源（/algorithm/options，本轮不选中以保持精简载荷）',
        len(boxes) >= 1 or '暂无可用算法' in pop_txt,
        {'options': [b.get_attribute('aria-label') for b in boxes], 'popover_text': pop_txt[:200]})
    close_popup(drv)


def save_drawer(drv, expect_method='POST'):
    t0 = time.time()
    js_click(drv, one(drv, SHEET + "//button[@type='submit' and @form='dimension-mutate-form']", timeout=15))
    hits = wait_net(drv, '/evaluation/dimensions', expect_method, timeout=150)
    elapsed = round(time.time() - t0, 2)
    toast = wait_toast(drv, '成功', timeout=30)
    hit = hits[-1] if hits else {}
    log('维度抽屉-保存 %s（0-120s，耗时只记录）' % expect_method,
        bool(hit) and 200 <= int(hit.get('status', 0)) < 300 and toast,
        {'status': hit.get('status'), 'elapsed_s': elapsed, 'toast_ok': toast,
         'reqBody': (hit.get('reqBody') or '')[:1200]})
    time.sleep(2.0)
    return hit, elapsed


def phase_create(drv):
    sh, title, tabs = open_create_drawer(drv)
    log('维度抽屉-0 打开/标题/页签', title == '新增评估维度'
        and tabs == ['基本信息', '层级配置', '结果配置', 'API配置', '关联算法'],
        {'title': title, 'tabs': tabs})
    fill_dimension_minimal(drv, sh, DIM, CAT_PICK)
    hit, dt = save_drawer(drv, 'POST')
    req = {}
    try:
        req = json.loads(hit.get('reqBody') or '{}')
    except Exception:
        pass
    log('维度抽屉-6 POST 请求体（精简载荷：1 输入 / 1 输出 / 1 端点，无算法）',
        len(req.get('required_inputs') or []) == 1 and len(req.get('output_fields') or []) == 1
        and len(req.get('api_endpoints') or []) == 1,
        {'inputs': [(i.get('key') or i.get('param_code'), i.get('label')) for i in req.get('required_inputs') or []],
         'outputs': [(o.get('param_code'), o.get('field_path')) for o in req.get('output_fields') or []],
         'endpoints': [(e.get('url'), e.get('name')) for e in req.get('api_endpoints') or []],
         'algorithms': req.get('associated_algorithms')})
    info = verify_dim_readback(DIM)
    log('维度回读-新建后 GET 逐字段（名称/描述/分类/1 输入/1 输出/1 端点/5 规则）',
        bool(info) and info['name'] == DIM and info['desc'] == 'INT-1484 复走维度描述'
        and len(info['inputs']) == 1 and info['inputs'][0][0] == 'q_text'
        and len(info['outputs']) == 1 and info['outputs'][0][0] == 'score'
        and len(info['endpoints']) == 1 and info['rule_count'] == 5,
        info)
    return info


def phase_edit(drv):
    search_dim(drv, DIM)
    row_button(drv, '编辑维度 %s' % DIM)
    sh = sheet(drv)
    title = sh.find_element(By.XPATH, ".//*[@data-slot='sheet-title']").text.strip()
    WebDriverWait(drv, 30).until(lambda d: d.find_element(By.ID, 'dim-name').get_attribute('value') == DIM)
    time.sleep(1.5)
    name_val = sh.find_element(By.ID, 'dim-name').get_attribute('value')
    desc_val = sh.find_element(By.ID, 'dim-description').get_attribute('value')
    cat_text = trigger_by_label(drv, '所属分类').text.strip()
    tab_click(drv, 'API配置')
    in1 = sh.find_element(By.XPATH, ".//input[@aria-label='输入参数键名 1']").get_attribute('value')
    in_label = sh.find_element(By.XPATH, ".//input[@aria-label='输入显示标签 1']").get_attribute('value')
    out1 = sh.find_element(By.XPATH, ".//input[@aria-label='输出字段代码 1']").get_attribute('value')
    ep_url = sh.find_element(By.XPATH, ".//input[@aria-label='端点 URL 1']").get_attribute('value')
    log('维度抽屉-7 编辑反填（已保存值，非表单默认行）',
        title == '编辑评估维度' and name_val == DIM and desc_val == 'INT-1484 复走维度描述'
        and cat_text == CAT_PICK and in1 == 'q_text' and out1 == 'score' and ep_url == ONLINE_URL,
        {'title': title, 'name': name_val, 'desc': desc_val, 'category': cat_text,
         'input1': in1, 'input_label': in_label, 'output1': out1, 'endpoint1': ep_url})
    shot(drv, '05_dimension_edit_prefill_light')

    tab_click(drv, '基本信息')
    clear_and_type(drv, sh.find_element(By.ID, 'dim-name'), DIM_EDIT)
    clear_and_type(drv, sh.find_element(By.ID, 'dim-description'), 'INT-1484 复走维度描述(已改)')
    tab_click(drv, 'API配置')
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='输入显示标签 1']"), '提问文本(改)')
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='输出显示名 1']"), '评分(改)')
    hit, dt = save_drawer(drv, 'PUT')
    info = verify_dim_readback(DIM_EDIT)
    log('维度回读-编辑后 GET 逐字段（PUT 闭环：名称/描述/输入标签/输出显示名/端点保留）',
        bool(info) and info['name'] == DIM_EDIT and info['desc'] == 'INT-1484 复走维度描述(已改)'
        and len(info['inputs']) == 1 and info['inputs'][0][0] == 'q_text'
        and len(info['outputs']) == 1 and info['outputs'][0][0] == 'score'
        and len(info['endpoints']) == 1,
        {'elapsed_s': dt, **info})
    return info


def phase_rule_calc(drv, tag='light'):
    search_dim(drv, DIM_EDIT)
    row_button(drv, '规则试算维度 %s' % DIM_EDIT)
    dlg = dialog(drv, '规则试算')
    btn = dlg.find_element(By.XPATH, ".//button[normalize-space(.)='试算']")
    disabled_empty = btn.get_attribute('disabled') is not None
    clear_and_type(drv, dlg.find_element(By.ID, 'calc-value'), '92')
    js_click(drv, btn)
    hits = wait_net(drv, '/calculate', 'POST', timeout=30)
    time.sleep(1.2)
    txt = dlg.text
    log('规则试算-1[%s] 空值禁用 + 92 → 评分 9 分（命中 >= 90）' % tag,
        disabled_empty and bool(hits) and '评分 9 分' in txt,
        {'disabled_when_empty': disabled_empty, 'status': hits[-1]['status'] if hits else None,
         'reqBody': hits[-1].get('reqBody') if hits else None, 'dialog_text': txt[:400]})
    shot(drv, '06_rule_calc_' + tag)
    clear_and_type(drv, dlg.find_element(By.ID, 'calc-value'), '10')
    js_click(drv, dlg.find_element(By.XPATH, ".//button[normalize-space(.)='试算']"))
    wait_net(drv, '/calculate', 'POST', timeout=30)
    time.sleep(1.0)
    log('规则试算-2[%s] 低值 10 → 命中兜底规则 < 70 → 0 分' % tag,
        '评分 0 分' in dlg.text and '< 70' in dlg.text, {'dialog_text': dlg.text[:400]})
    js_click(drv, dlg.find_element(By.XPATH, ".//button[normalize-space(.)='关闭']"))
    time.sleep(0.8)


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


def phase_health_online(drv, tag='light'):
    dlg, hits, txt = open_health(drv, DIM_EDIT)
    rows = dlg.find_elements(By.CSS_SELECTOR, 'tbody tr')
    log('健康测试-1[%s] 在线端点（15000/health）→ 总状态在线' % tag,
        bool(hits) and '总状态' in txt and '在线' in txt,
        {'status': hits[-1]['status'] if hits else None,
         'resp': (hits[-1].get('resBody') or '')[:400] if hits else None,
         'rows': len(rows), 'dialog_text': txt[:400]})
    shot(drv, '07_health_online_' + tag)
    js_click(drv, dlg.find_element(By.XPATH, ".//button[normalize-space(.)='关闭']"))
    time.sleep(0.8)
    search_dim(drv, '')


def create_offline_dim():
    body = {
        'name': OFFLINE_DIM, 'type': 'auto', 'dimension_type': 'main', 'category_id': None,
        'status': True, 'weight': 5, 'result_type': 1, 'result_min': 0, 'result_max': 100,
        'decimal_places': 2, 'estimated_exec_time': 5,
        'rule': {'rules': [{'condition': '>=', 'value': 90, 'score': 10}]},
        'required_inputs': [{'param_code': 'q_text', 'param_name': '提问文本', 'label': '提问文本',
                             'field_type': 'text', 'required': True, 'default_value': '',
                             'help_text': '', 'ui_order': 1}],
        'output_fields': [{'param_code': 'score', 'param_name': '评分', 'label': '评分',
                           'field_path': 'score', 'field_type': 'number', 'output_role': 'main',
                           'agg_role': 'value', 'default_value': '', 'pass_threshold': None,
                           'visible_in_report': True, 'help_text': '', 'ui_order': 1}],
        'api_endpoints': [{'url': 'http://127.0.0.1:59999/health', 'name': '不可达端点', 'priority': 1,
                           'max_process': 5, 'max_timeout': 30, 'max_audio_duration': 60}],
        'api_settings': {'method': 'POST', 'timeout': 30000, 'headers': {}, 'bodyTemplate': {}},
    }
    st, resp, dt = api_call('POST', '/evaluation/dimensions', body)
    did = ((resp or {}).get('data') or {}).get('id') if isinstance(resp, dict) else None
    log('健康测试-0[离线] 建立离线维度（精简载荷 POST）', st in (200, 201) and did is not None,
        {'status': st, 'elapsed_s': dt, 'id': did,
         'resp': json.dumps(resp, ensure_ascii=False)[:300] if not did else ''})
    return did


def phase_health_offline(drv):
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
        env('健康测试-3 无端点真实维度「%s」不可达（列表未找到/入口缺失）' % NO_EP_DIM, {'error': str(e)[:300]})
        search_dim(drv, '')
        return
    rows = dlg.find_elements(By.CSS_SELECTOR, 'tbody tr')
    shot(drv, '09_health_no_endpoint_light')
    log('健康测试-3 无端点维度「%s」：页面给出确定态（总状态或空态提示）' % NO_EP_DIM,
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
    sh, _, _ = open_create_drawer(drv)
    clear_and_type(drv, sh.find_element(By.ID, 'dim-name'), '临时输入_应清空')
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(1.0)
    closed = not bool(drv.find_elements(By.XPATH, SHEET))
    sh2, _, _ = open_create_drawer(drv)
    value_after = sh2.find_element(By.ID, 'dim-name').get_attribute('value')
    log('取消重开-1 Esc 关闭后重开不残留上次输入', closed and value_after == '',
        {'closed_by_esc': closed, 'value_after_reopen': value_after})
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(0.8)
    sh3, _, _ = open_create_drawer(drv)
    sh3.find_element(By.ID, 'dim-name').send_keys('遮罩测试')
    overlays = drv.find_elements(By.XPATH, "//*[@data-slot='sheet-overlay']")
    closed_overlay = False
    if overlays:
        from selenium.webdriver.common.action_chains import ActionChains
        ActionChains(drv).move_to_element_with_offset(overlays[0], -500, 0).click().perform()
        time.sleep(1.0)
        closed_overlay = not bool(drv.find_elements(By.XPATH, SHEET))
    log('取消重开-2 点遮罩关闭', closed_overlay,
        {'closed_by_overlay': closed_overlay, 'overlay_present': bool(overlays)})
    if not closed_overlay:
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
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
    sh, _, _ = open_create_drawer(drv)
    clear_and_type(drv, sh.find_element(By.ID, 'dim-name'), P + '_darkobj')
    shot(drv, '14_dimension_drawer_dark')
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(1.0)
    js_click(drv, one(drv, "//button[normalize-space(.)='新增分类']", timeout=15))
    time.sleep(1.0)
    shot(drv, '15_category_dialog_dark')
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(0.8)
    phase_rule_calc(drv, tag='dark')
    phase_health_online(drv, tag='dark_17')
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode','light');")
    drv.get('about:blank')
    goto_eval(drv)


def phase_delete_dimension(drv):
    search_dim(drv, DIM_EDIT)
    row_button(drv, '删除维度 %s' % DIM_EDIT)
    dlg = alert_dialog(drv, '删除维度')
    dlg_text = dlg.text
    shot(drv, '19_delete_dimension_confirm_light')
    t0 = time.time()
    js_click(drv, dlg.find_element(By.XPATH, ".//button[normalize-space(.)='删除']"))
    hits = wait_net(drv, '/evaluation/dimensions', 'DELETE', timeout=120)
    elapsed = round(time.time() - t0, 2)
    time.sleep(1.5)
    dims = api_dims()
    still = [d for d in dims if d.get('name') == DIM_EDIT]
    log('维度删除闭环：确认弹窗 + DELETE + GET 回读（列表消失）',
        '确定要删除维度' in dlg_text and bool(hits) and not still,
        {'confirm_text': dlg_text[:160], 'status': hits[-1].get('status') if hits else None,
         'elapsed_s': elapsed, 'still_in_list': bool(still), 'total': len(dims)})
    return not still


def phase_cleanup(drv, offline_id):
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
        {'deleted': deleted, 'offline_dim_id': offline_id, 'remain': remain,
         'footer': m['footer_total'], 'baseline': BASELINE_TOTAL})


def main():
    global BASELINE_TOTAL, CAT_PICK
    t0 = time.time()
    drv = _driver()
    offline_id = None
    try:
        login(drv)
        goto_eval(drv)
        BASELINE_TOTAL = len(api_dims())
        cats = api_cats()
        CAT_PICK = cats[0]['name'] if cats else '未分类'
        log('开工基线：维度 %d 条 / 分类 %d 条（分类下拉选用既有分类 %s，不新建）'
            % (BASELINE_TOTAL, len(cats), CAT_PICK), bool(cats), {'baseline': BASELINE_TOTAL})
        info = phase_create(drv)
        phase_edit(drv)
        phase_rule_calc(drv)
        phase_health_online(drv)
        offline_id = create_offline_dim()
        phase_health_offline(drv)
        phase_health_no_endpoint(drv)
        phase_empty_state(drv)
        phase_error_state(drv)
        phase_cancel_reopen(drv)
        phase_dark(drv)
        phase_delete_dimension(drv)
    except Exception:
        log('EXCEPTION', False, traceback.format_exc()[-2500:])
    finally:
        try:
            phase_cleanup(drv, offline_id)
        except Exception:
            log('CLEANUP-EXCEPTION', False, traceback.format_exc()[-900:])
        with open(os.path.join(ART, 'result_remainder.json'), 'w', encoding='utf-8') as f:
            json.dump({'stamp': STAMP, 'elapsed_s': round(time.time() - t0, 1),
                       'baseline_total': BASELINE_TOTAL,
                       'result': RESULT, 'env': ENV, 'net': NET}, f, ensure_ascii=False, indent=1)
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
