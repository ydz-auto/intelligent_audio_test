# -*- coding: utf-8 -*-
"""INT-1484 评估域深走查（真实库栈：前端 15173 / 后端 15000）。

覆盖：评估分类新建/编辑/重名、维度新建(输入/输出参数/端点/算法)/编辑/回读/删除闭环、
规则试算、API 健康测试(在线/离线)、取消重开、空态/错误态、联动计数、浅深色截图。
数据纪律：只写「接线测试_INT1484_」前缀记录，run 结束前经 API 删除。
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
CAT_NAME = P + '_分类'
DIM_NAME = P + '_维度'
DIM_NAME_EDITED = DIM_NAME + '_改'
HEALTH_DIM = P + '_在线维度'
OFFLINE_DIM = P + '_离线维度'
SEARCH_NONE = 'zzz_无匹配_1484'

RESULT = []
NET = []

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
      if (url.indexOf('/evaluation') !== -1 || url.indexOf('/algorithm/options') !== -1) {
        const ct = res.headers.get('content-type') || '';
        if (ct.indexOf('json') !== -1) {
          try { entry.resBody = await res.clone().text(); } catch (e) {}
        }
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
          json.dumps(detail, ensure_ascii=False, default=str)[:800], flush=True)


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


def wait_net(drv, substr, method=None, timeout=40):
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


def drain_net(drv):
    items = fetch_log(drv)
    NET.extend(items)
    try:
        drv.execute_script('window.__fetchLog = [];')
    except Exception:
        pass
    return items


def toast_texts(drv):
    return [e.text for e in drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]


def wait_toast(drv, text, timeout=20):
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


def select_by_label(drv, label_text, option_text, scope="//*"):
    trig = one(drv, "%s[.//label[contains(normalize-space(.), '%s')]]//button[@role='combobox']"
               % (scope, label_text), timeout=10)
    js_click(drv, trig)
    time.sleep(0.5)
    opt = one(drv, "//*[@data-slot='select-item'][contains(normalize-space(.), '%s')]" % option_text, timeout=10)
    js_click(drv, opt)
    time.sleep(0.4)


def combobox_labels(drv, label_text, scope="//*"):
    trig = one(drv, "%s[.//label[contains(normalize-space(.), '%s')]]//button[@role='combobox']"
               % (scope, label_text), timeout=10)
    js_click(drv, trig)
    time.sleep(0.6)
    items = drv.find_elements(By.XPATH, "//*[@data-slot='select-item']")
    return [i.text.strip() for i in items]


def close_open_listbox(drv):
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(0.4)


def trigger_text(drv, label_text, scope="//*"):
    trig = one(drv, "%s[.//label[contains(normalize-space(.), '%s')]]//button[@role='combobox']"
               % (scope, label_text), timeout=10)
    return (trig.text or '').strip()


def api_call(method, path, body=None):
    token = open(os.path.join(ART, 'token.txt'), encoding='utf-8').read().strip()
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + '/api/v1' + path, data=data, method=method,
                                 headers={'Authorization': 'Bearer ' + token,
                                          'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw


def api_dims():
    st, body = api_call('GET', '/evaluation/dimensions?per_page=1000')
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
    inp = one(drv, "//input[contains(@placeholder,'搜索评估维度')]", timeout=10)
    clear_and_type(drv, inp, keyword)
    time.sleep(1.2)


def tab_click(drv, label):
    js_click(drv, one(drv, "//button[@role='tab'][contains(normalize-space(.),'%s')]" % label, timeout=10))
    time.sleep(0.6)


def sheet(drv):
    return one(drv, "//*[@data-slot='sheet-content']", timeout=10)


def row_button(drv, aria_label):
    el = one(drv, "//button[@aria-label='%s']" % aria_label, timeout=12)
    js_click(drv, el)
    time.sleep(0.5)


# ---------- 分类 ----------

def category_create(drv):
    js_click(drv, one(drv, "//button[normalize-space(.)='新增分类']", timeout=10))
    dlg = one(drv, "//*[@data-slot='dialog-content'][.//*[@data-slot='dialog-title'][normalize-space(.)='新建分类']]", timeout=10)
    title = dlg.find_element(By.XPATH, ".//*[@data-slot='dialog-title']").text
    icon_val = dlg.find_element(By.ID, 'category-icon').get_attribute('value')
    submit = dlg.find_element(By.XPATH, ".//button[@type='submit']")
    disabled_empty = submit.get_attribute('disabled') is not None
    log('分类弹窗-1 打开/标题/默认图标/空名禁用',
        title == '新建分类' and icon_val == 'fas fa-folder' and disabled_empty,
        {'title': title, 'icon': icon_val, 'submit_disabled_when_empty': disabled_empty})
    shot(drv, '01_category_dialog_light')
    clear_and_type(drv, dlg.find_element(By.ID, 'category-name'), CAT_NAME)
    clear_and_type(drv, dlg.find_element(By.ID, 'category-description'), 'INT-1484 分类描述')
    js_click(drv, submit)
    hits = wait_net(drv, '/evaluation/categories', 'POST', timeout=30)
    ok_toast = wait_toast(drv, '分类添加成功', timeout=15)
    post = hits[-1] if hits else {}
    log('分类弹窗-2 新建提交 POST + toast',
        bool(post) and 200 <= int(post.get('status', 0)) < 300 and ok_toast,
        {'request': post.get('reqBody'), 'status': post.get('status'), 'toast_ok': ok_toast})
    st, body = api_call('GET', '/evaluation/categories?per_page=100')
    items = (body or {}).get('data', {}).get('items', []) if isinstance(body, dict) else []
    mine = [c for c in items if c.get('name') == CAT_NAME]
    log('分类弹窗-3 GET 回读（名称/描述/图标）',
        len(mine) == 1 and mine[0].get('description') == 'INT-1484 分类描述' and mine[0].get('icon') == 'fas fa-folder',
        {'id': mine[0]['id'] if mine else None, 'desc': mine[0].get('description') if mine else None,
         'icon': mine[0].get('icon') if mine else None, 'total_categories': len(items)})
    return mine[0]['id'] if mine else None


def category_duplicate(drv):
    js_click(drv, one(drv, "//button[normalize-space(.)='新增分类']", timeout=10))
    dlg = one(drv, "//*[@data-slot='dialog-content'][.//*[@data-slot='dialog-title'][normalize-space(.)='新建分类']]", timeout=10)
    clear_and_type(drv, dlg.find_element(By.ID, 'category-name'), CAT_NAME)
    js_click(drv, dlg.find_element(By.XPATH, ".//button[@type='submit']"))
    hits = wait_net(drv, '/evaluation/categories', 'POST', timeout=30)
    time.sleep(1.2)
    post = hits[-1] if hits else {}
    still_open = bool(drv.find_elements(
        By.XPATH, "//*[@data-slot='dialog-content'][.//*[@data-slot='dialog-title'][normalize-space(.)='新建分类']]"))
    toasts = toast_texts(drv)
    inline = drv.execute_script(
        "return [...document.querySelectorAll('[data-slot=dialog-content] p')].map(e=>e.textContent).join('|')")
    log('分类弹窗-4 重名校验（后端 400 时前端表现）',
        int(post.get('status', 0)) >= 400 and (still_open or bool(toasts)),
        {'status': post.get('status'), 'resp': (post.get('resBody') or '')[:200],
         'dialog_still_open': still_open, 'toasts': toasts, 'inline_errors': inline})
    if still_open:
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(0.6)


def category_edit_via_group(drv):
    tab_click(drv, '分组视图')
    time.sleep(1.0)
    js_click(drv, one(drv, "//button[@aria-label='编辑分类 %s']" % CAT_NAME, timeout=15))
    dlg = one(drv, "//*[@data-slot='dialog-content'][.//*[@data-slot='dialog-title'][normalize-space(.)='编辑分类']]", timeout=10)
    name_val = dlg.find_element(By.ID, 'category-name').get_attribute('value')
    desc_val = dlg.find_element(By.ID, 'category-description').get_attribute('value')
    log('分类弹窗-5 编辑反填（名称/描述）',
        name_val == CAT_NAME and desc_val == 'INT-1484 分类描述',
        {'name': name_val, 'desc': desc_val})
    shot(drv, '02_category_edit_light')
    clear_and_type(drv, dlg.find_element(By.ID, 'category-description'), 'INT-1484 分类描述(已改)')
    js_click(drv, dlg.find_element(By.XPATH, ".//button[@type='submit']"))
    hits = wait_net(drv, '/evaluation/categories', 'PUT', timeout=30)
    st, body = api_call('GET', '/evaluation/categories?per_page=100')
    items = (body or {}).get('data', {}).get('items', []) if isinstance(body, dict) else []
    mine = [c for c in items if c.get('name') == CAT_NAME]
    log('分类弹窗-6 编辑保存 PUT + 回读描述',
        bool(hits) and 200 <= int(hits[-1].get('status', 0)) < 300 and mine
        and mine[0].get('description') == 'INT-1484 分类描述(已改)',
        {'status': hits[-1].get('status') if hits else None,
         'readback_desc': mine[0].get('description') if mine else None})
    tab_click(drv, '列表视图')
    time.sleep(0.8)


# ---------- 维度抽屉 ----------

def open_create_drawer(drv):
    js_click(drv, one(drv, "//button[normalize-space(.)='新增维度']", timeout=10))
    sh = sheet(drv)
    title = sh.find_element(By.XPATH, ".//*[@data-slot='sheet-title']").text
    tabs = [t.text.strip() for t in sh.find_elements(By.XPATH, ".//button[@role='tab']")]
    return sh, title, tabs


def fill_dimension_create(drv, sh, name, with_params=True):
    clear_and_type(drv, sh.find_element(By.ID, 'dim-name'), name)
    clear_and_type(drv, sh.find_element(By.ID, 'dim-description'), 'INT-1484 维度描述')
    select_by_label(drv, '所属分类', CAT_NAME, scope="//*[@data-slot='sheet-content']")
    # 层级配置：切子维度看页签收敛，再切回主维度
    tab_click(drv, '层级配置')
    select_by_label(drv, '维度类型', '子维度', scope="//*[@data-slot='sheet-content']")
    time.sleep(0.5)
    sub_tabs = [t.text.strip() for t in sh.find_elements(By.XPATH, ".//button[@role='tab']")]
    select_by_label(drv, '维度类型', '主维度', scope="//*[@data-slot='sheet-content']")
    time.sleep(0.4)
    main_tabs = [t.text.strip() for t in sh.find_elements(By.XPATH, ".//button[@role='tab']")]
    clear_and_type(drv, sh.find_element(By.ID, 'dim-keywords'), '接线测试,关键词')
    log('维度抽屉-2 维度类型切换页签（主5/子3）',
        len(main_tabs) == 5 and len(sub_tabs) == 3,
        {'main_tabs': main_tabs, 'sub_tabs': sub_tabs})

    # 结果配置：规则默认行数 + 校验
    tab_click(drv, '结果配置')
    rule_rows = len(sh.find_elements(By.XPATH, ".//input[starts-with(@aria-label,'规则 ') and contains(@aria-label,'阈值')]"))
    clear_and_type(drv, sh.find_element(By.ID, 'dim-result-min'), '100')
    clear_and_type(drv, sh.find_element(By.ID, 'dim-result-max'), '0')
    time.sleep(0.5)
    err = drv.execute_script(
        "return [...document.querySelectorAll('[data-slot=sheet-content] p')].map(e=>e.textContent).join('|')")
    log('维度抽屉-3 结果配置默认规则行 + 最小值≥最大值校验',
        rule_rows == 5 and '结果最大值必须大于最小值' in (err or ''),
        {'default_rule_rows': rule_rows, 'inline_errors': (err or '')[:200]})
    clear_and_type(drv, sh.find_element(By.ID, 'dim-result-min'), '0')
    clear_and_type(drv, sh.find_element(By.ID, 'dim-result-max'), '100')
    time.sleep(0.3)

    if not with_params:
        return

    # API 配置
    tab_click(drv, 'API配置')
    method_opts = combobox_labels(drv, '请求方法', scope="//*[@data-slot='sheet-content']")
    close_open_listbox(drv)
    clear_and_type(drv, sh.find_element(By.ID, 'dim-api-url'), 'http://127.0.0.1:15000/health')
    clear_and_type(drv, sh.find_element(By.ID, 'dim-api-headers'), '{"content-type": "application/json"}')
    # 输入参数 1（默认已有 2 行，改第一行 + 追加第三行）
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='输入参数键名 1']"), 'asr_result')
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='输入显示标签 1']"), 'ASR识别结果')
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='输入默认值 1']"), '默认值A')
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='输入描述 1']"), '输入描述A')
    js_click(drv, one(drv, "//*[@data-slot='sheet-content']//button[normalize-space(.)='添加输入']", timeout=10))
    time.sleep(0.4)
    n_inputs = len(sh.find_elements(By.XPATH, ".//input[@aria-label[starts-with(.,'输入参数键名')]]"))
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='输入参数键名 %d']" % n_inputs), 'ref_text')
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='输入显示标签 %d']" % n_inputs), '参考文本')
    # 输出字段
    js_click(drv, one(drv, "//*[@data-slot='sheet-content']//button[normalize-space(.)='添加字段']", timeout=10))
    time.sleep(0.4)
    n_out = len(sh.find_elements(By.XPATH, ".//input[@aria-label[starts-with(.,'输出字段代码')]]"))
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='输出字段代码 %d']" % n_out), 'score')
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='输出显示名 %d']" % n_out), '评分')
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='输出提取路径 %d']" % n_out), 'data.score')
    # 聚合角色 → 达标线(≤) 使达标阈值可编辑
    agg_trig = one(drv, "//*[@data-slot='sheet-content']//button[@aria-label='输出字段代码 %d']/following::button[@role='combobox'][1]" % n_out, timeout=10)
    js_click(drv, agg_trig)
    time.sleep(0.5)
    close_open_listbox(drv)
    pass_thr_before = sh.find_element(By.XPATH, ".//input[@aria-label='输出达标阈值 %d']" % n_out).get_attribute('disabled')
    # API 端点
    js_click(drv, one(drv, "//*[@data-slot='sheet-content']//button[normalize-space(.)='添加端点']", timeout=10))
    time.sleep(0.4)
    n_ep = len(sh.find_elements(By.XPATH, ".//input[@aria-label[starts-with(.,'端点 URL')]]"))
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='端点 URL %d']" % n_ep), 'http://127.0.0.1:15000/health')
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='端点名称 %d']" % n_ep), '接线测试端点')
    log('维度抽屉-4 API配置：请求方法选项 / 输入行 / 输出行 / 端点行',
        method_opts == ['GET', 'POST', 'PUT', 'DELETE', 'PATCH'] and n_inputs == 3 and n_out == 1 and n_ep == 2,
        {'method_options': method_opts, 'inputs': n_inputs, 'outputs': n_out, 'endpoints': n_ep,
         'pass_threshold_disabled_before': pass_thr_before})

    # 关联算法
    tab_click(drv, '关联算法')
    js_click(drv, one(drv, "//*[@data-slot='sheet-content']//button[contains(normalize-space(.),'选择关联的算法类型')]", timeout=10))
    time.sleep(0.6)
    algo_boxes = drv.find_elements(By.XPATH, "//*[@data-slot='sheet-content']//*[@role='checkbox' and starts-with(@aria-label,'关联算法 ')]")
    algo_labels = [b.get_attribute('aria-label') for b in algo_boxes]
    if algo_boxes:
        js_click(drv, algo_boxes[0])
    time.sleep(0.4)
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(0.4)
    return {'algo_options': algo_labels}


def save_drawer(drv, expect_method='POST'):
    js_click(drv, drv.find_element(By.XPATH, "//*[@data-slot='sheet-content']//button[@type='submit' and @form='dimension-mutate-form']"))
    hits = wait_net(drv, '/evaluation/dimensions', expect_method, timeout=40)
    toast = wait_toast(drv, '成功', timeout=20)
    hit = hits[-1] if hits else {}
    log('维度抽屉-保存 %s' % expect_method,
        bool(hit) and 200 <= int(hit.get('status', 0)) < 300 and toast,
        {'status': hit.get('status'), 'reqBody': (hit.get('reqBody') or '')[:900], 'toast_ok': toast})
    time.sleep(1.2)
    return hit


def verify_dim_readback(drv, name):
    dims = api_dims()
    mine = [d for d in dims if d.get('name') == name]
    if not mine:
        log('维度回读：列表 GET 未找到 %s' % name, False, {'count': len(dims)})
        return None
    d = mine[0]
    st, body = api_call('GET', '/evaluation/dimensions/%s' % d['id'])
    detail = (body or {}).get('data', {}) if isinstance(body, dict) else {}
    ri = detail.get('required_inputs') or []
    of = detail.get('output_fields') or []
    ep = detail.get('api_endpoints') or []
    summary = {
        'id': d['id'], 'name': detail.get('name'), 'desc': detail.get('description'),
        'category_id': detail.get('category_id'), 'keywords': detail.get('keywords'),
        'weight': detail.get('weight'), 'rule_count': len((detail.get('rule') or {}).get('rules') or []),
        'inputs': [(x.get('param_code'), x.get('param_name'), x.get('default_value')) for x in ri],
        'outputs': [(x.get('param_code'), x.get('field_path'), x.get('pass_threshold')) for x in of],
        'endpoints': [(x.get('url'), x.get('name')) for x in ep],
        'algorithms': [a.get('algorithm_type') for a in (detail.get('associated_algorithms') or [])],
        'statistic_method': detail.get('statistic_method'), 'agg_denominator': detail.get('agg_denominator'),
        'result_type': detail.get('result_type'), 'result_min': detail.get('result_min'), 'result_max': detail.get('result_max'),
    }
    return summary


# ---------- 主流程 ----------

def phase_page_and_category(drv):
    goto_eval(drv)
    net = drain_net(drv)
    m = page_metrics(drv)
    dims = [n for n in net if n['url'].split('?')[0].endswith('/evaluation/dimensions') and n['method'] == 'GET']
    cats = [n for n in net if '/evaluation/categories' in n['url']]
    algos = [n for n in net if '/algorithm/options' in n['url']]
    cat_opts = combobox_labels(drv, '全部分类', scope="//*")
    close_open_listbox(drv)
    algo_opts = combobox_labels(drv, '全部', scope="//*")
    close_open_listbox(drv)
    log('页面-1 首屏三接口 + 计数口径（页脚/分类/算法下拉）',
        bool(dims) and bool(cats) and bool(algos) and '共 56 条' in (m['footer_total'] or '')
        and len(cat_opts) == 5 and len(algo_opts) == 4,
        {'dims': dims[-1]['status'] if dims else None, 'cats': cats[-1]['status'] if cats else None,
         'algos': algos[-1]['status'] if algos else None,
         'metrics': m, 'category_options': cat_opts, 'algorithm_options': algo_opts})
    shot(drv, '00_page_list_light')
    cat_id = category_create(drv)
    category_duplicate(drv)
    return cat_id


def phase_dimension_create(drv):
    sh, title, tabs = open_create_drawer(drv)
    log('维度抽屉-1 打开/标题/初始页签/默认值',
        title == '新增评估维度' and tabs == ['基本信息', '层级配置', '结果配置', 'API配置', '关联算法'],
        {'title': title, 'tabs': tabs})
    shot(drv, '03_dimension_drawer_light')
    algo_info = fill_dimension_create(drv, sh, DIM_NAME, with_params=True)
    log('维度抽屉-5 关联算法选项条数（= /algorithm/options 3 条）',
        bool(algo_info) and len(algo_info['algo_options']) == 3, algo_info)
    shot(drv, '04_dimension_drawer_api_light')
    save_drawer(drv, 'POST')
    return verify_dim_readback(drv, DIM_NAME)


def phase_dimension_edit(drv):
    search_dim(drv, DIM_NAME)
    row_button(drv, '编辑维度 %s' % DIM_NAME)
    sh = sheet(drv)
    title = sh.find_element(By.XPATH, ".//*[@data-slot='sheet-title']").text
    # 等详情反填
    WebDriverWait(drv, 25).until(lambda d: d.find_element(By.ID, 'dim-name').get_attribute('value') == DIM_NAME)
    time.sleep(1.2)
    name_val = sh.find_element(By.ID, 'dim-name').get_attribute('value')
    desc_val = sh.find_element(By.ID, 'dim-description').get_attribute('value')
    cat_text = trigger_text(drv, '所属分类', scope="//*[@data-slot='sheet-content']")
    tab_click(drv, 'API配置')
    in1 = sh.find_element(By.XPATH, ".//input[@aria-label='输入参数键名 1']").get_attribute('value')
    out1 = sh.find_element(By.XPATH, ".//input[@aria-label='输出字段代码 1']").get_attribute('value')
    ep_urls = [e.get_attribute('value') for e in sh.find_elements(By.XPATH, ".//input[@aria-label[starts-with(.,'端点 URL')]]")]
    tab_click(drv, '关联算法')
    algo_trigger = one(drv, "//*[@data-slot='sheet-content']//button[contains(normalize-space(.),'已选择')]", timeout=8)
    algo_text = algo_trigger.text.strip() if algo_trigger else ''
    log('维度抽屉-6 编辑反填（详情 GET：名称/描述/分类/输入/输出/端点/算法）',
        title == '编辑评估维度' and name_val == DIM_NAME and desc_val == 'INT-1484 维度描述'
        and cat_text == CAT_NAME and in1 == 'asr_result' and out1 == 'score'
        and 'http://127.0.0.1:15000/health' in ep_urls and '已选择 1 个算法' in algo_text,
        {'title': title, 'name': name_val, 'desc': desc_val, 'category': cat_text,
         'input1': in1, 'output1': out1, 'endpoints': ep_urls, 'algorithm': algo_text})
    shot(drv, '05_dimension_edit_prefill_light')

    # 改字段
    tab_click(drv, '基本信息')
    clear_and_type(drv, sh.find_element(By.ID, 'dim-name'), DIM_NAME_EDITED)
    clear_and_type(drv, sh.find_element(By.ID, 'dim-description'), 'INT-1484 维度描述(已改)')
    tab_click(drv, 'API配置')
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='输入显示标签 1']"), 'ASR识别结果(改)')
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='输出字段代码 1']"), 'score_v2')
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='端点名称 2']"), '接线测试端点(改)')
    save_drawer(drv, 'PUT')
    return verify_dim_readback(drv, DIM_NAME_EDITED)


def phase_rule_calc(drv):
    search_dim(drv, DIM_NAME_EDITED)
    row_button(drv, '规则试算维度 %s' % DIM_NAME_EDITED)
    dlg = one(drv, "//*[@data-slot='dialog-content'][.//*[@data-slot='dialog-title'][contains(.,'规则试算')]]", timeout=10)
    btn = dlg.find_element(By.XPATH, ".//button[normalize-space(.)='试算']")
    disabled_empty = btn.get_attribute('disabled') is not None
    clear_and_type(drv, dlg.find_element(By.ID, 'calc-value'), '92')
    time.sleep(0.3)
    js_click(drv, btn)
    hits = wait_net(drv, '/calculate', 'POST', timeout=30)
    time.sleep(1.2)
    body_txt = dlg.text
    has_score = '评分 9 分' in body_txt
    has_rule = '>= 90' in body_txt and '9 分' in body_txt
    log('规则试算-1 空值禁用 + 试算 92 → 评分 9 + 命中规则',
        disabled_empty and bool(hits) and has_score,
        {'disabled_when_empty': disabled_empty, 'status': hits[-1]['status'] if hits else None,
         'reqBody': hits[-1].get('reqBody') if hits else None, 'dialog_text': body_txt[:300],
         'has_score': has_score, 'has_rule_badge': has_rule})
    shot(drv, '06_rule_calc_light')
    # 非数字 / 极端值
    clear_and_type(drv, dlg.find_element(By.ID, 'calc-value'), '10')
    js_click(drv, dlg.find_element(By.XPATH, ".//button[normalize-space(.)='试算']"))
    wait_net(drv, '/calculate', 'POST', timeout=30)
    time.sleep(1.0)
    log('规则试算-2 无命中值 10 → 0 分提示', '没有规则命中' in (dlg.text or '') or '评分 0 分' in (dlg.text or ''),
        {'dialog_text': dlg.text[:300]})
    js_click(drv, dlg.find_element(By.XPATH, ".//button[normalize-space(.)='关闭']"))
    time.sleep(0.8)


def phase_health(drv):
    # 在线维度（端点 15000/health 可达）
    search_dim(drv, DIM_NAME_EDITED)
    row_button(drv, '测试维度 %s 的 API' % DIM_NAME_EDITED)
    dlg = one(drv, "//*[@data-slot='dialog-content'][.//*[@data-slot='dialog-title'][contains(.,'API健康测试')]]", timeout=10)
    hits = wait_net(drv, '/health', 'GET', timeout=40)
    time.sleep(1.5)
    txt = dlg.text
    rows = dlg.find_elements(By.CSS_SELECTOR, 'tbody tr')
    log('健康测试-1 在线端点（可达 15000/health）',
        bool(hits) and rows and '在线' in txt and 'http://127.0.0.1:15000/health' in txt,
        {'status': hits[-1]['status'] if hits else None,
         'resp': (hits[-1].get('resBody') or '')[:300] if hits else None,
         'rows': len(rows), 'dialog_text': txt[:400]})
    shot(drv, '07_health_online_light')
    js_click(drv, dlg.find_element(By.XPATH, ".//button[normalize-space(.)='关闭']"))
    time.sleep(0.8)


def phase_empty_state(drv):
    search_dim(drv, SEARCH_NONE)
    time.sleep(1.0)
    body = drv.find_element(By.TAG_NAME, 'body').text
    log('空态：搜索无匹配 → 暂无评估维度', '暂无评估维度' in body,
        {'has_empty': '暂无评估维度' in body})
    shot(drv, '08_empty_state_light')
    search_dim(drv, '')


def phase_error_state(drv):
    drv.execute_cdp_cmd('Network.enable', {})
    drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': ['*/evaluation/dimensions*']})
    try:
        drv.refresh()
        WebDriverWait(drv, 30).until(lambda d: '加载失败' in d.find_element(By.TAG_NAME, 'body').text)
        body = drv.find_element(By.TAG_NAME, 'body').text
        has_retry = bool(drv.find_elements(By.XPATH, "//button[normalize-space(.)='请重试']"))
        log('错误态：阻断 /evaluation/dimensions → 加载失败 + 请重试', '加载失败' in body and has_retry,
            {'has_error': '加载失败' in body, 'has_retry': has_retry})
        shot(drv, '09_error_state_light')
    finally:
        drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': []})
    js_click(drv, one(drv, "//button[normalize-space(.)='请重试']", timeout=10))
    WebDriverWait(drv, 30).until(lambda d: d.find_elements(By.CSS_SELECTOR, 'table tbody tr'))
    log('错误态-2 请重试恢复列表', len(drv.find_elements(By.CSS_SELECTOR, 'table tbody tr')) > 0, {})
    time.sleep(1.0)


def phase_cancel_reopen(drv):
    sh, title, tabs = open_create_drawer(drv)
    clear_and_type(drv, sh.find_element(By.ID, 'dim-name'), '临时输入_应清空')
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(1.0)
    closed = not bool(drv.find_elements(By.XPATH, "//*[@data-slot='sheet-content']"))
    sh2, _, _ = open_create_drawer(drv)
    value_after = sh2.find_element(By.ID, 'dim-name').get_attribute('value')
    log('取消重开：Esc 关闭后重开不残留上次输入', closed and value_after == '',
        {'closed_by_esc': closed, 'value_after_reopen': value_after})
    # 遮罩点击关闭
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(0.8)
    sh3, _, _ = open_create_drawer(drv)
    overlay = drv.find_elements(By.XPATH, "//*[@data-slot='sheet-overlay']")
    if overlay:
        # overlay 覆盖全屏，用坐标点左上角空白
        from selenium.webdriver.common.action_chains import ActionChains
        ActionChains(drv).move_to_element_with_offset(overlay[0], 5, 5).click().perform()
    time.sleep(1.0)
    closed_overlay = not bool(drv.find_elements(By.XPATH, "//*[@data-slot='sheet-content']"))
    log('取消重开：点遮罩关闭', closed_overlay, {'closed_by_overlay': closed_overlay})
    if not closed_overlay:
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(0.6)


def phase_dark(drv):
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark');")
    drv.get('about:blank')
    goto_eval(drv)
    time.sleep(1.0)
    shot(drv, '10_page_list_dark')
    js_click(drv, one(drv, "//button[@role='tab'][contains(normalize-space(.),'分组视图')]", timeout=10))
    time.sleep(1.2)
    shot(drv, '11_page_group_dark')
    tab_click(drv, '列表视图')
    sh, _, _ = open_create_drawer(drv)
    clear_and_type(drv, sh.find_element(By.ID, 'dim-name'), '接线测试_INT1484_darkobj')
    shot(drv, '12_dimension_drawer_dark')
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(0.8)
    js_click(drv, one(drv, "//button[normalize-space(.)='新增分类']", timeout=10))
    time.sleep(0.8)
    shot(drv, '13_category_dialog_dark')
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(0.6)
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode','light');")
    drv.get('about:blank')
    goto_eval(drv)


def phase_cleanup(drv, cat_id):
    created = [d for d in api_dims() if d.get('name', '').startswith('接线测试_INT1484_' + STAMP)]
    deleted = []
    for d in created:
        st, body = api_call('DELETE', '/evaluation/dimensions/%s' % d['id'])
        deleted.append({'id': d['id'], 'name': d['name'], 'status': st})
    cat_status = None
    if cat_id:
        cat_status, _ = api_call('DELETE', '/evaluation/categories/%s' % cat_id)
    time.sleep(1.0)
    remain_dim = [d for d in api_dims() if d.get('name', '').startswith('接线测试_INT1484_' + STAMP)]
    st, body = api_call('GET', '/evaluation/categories?per_page=100')
    cats = (body or {}).get('data', {}).get('items', []) if isinstance(body, dict) else []
    remain_cat = [c for c in cats if c.get('name', '').startswith('接线测试_INT1484_' + STAMP)]
    log('清理：删除本 run 测试维度/分类并复核无残留',
        not remain_dim and not remain_cat,
        {'deleted': deleted, 'category_delete_status': cat_status,
         'remain_dims': [d['name'] for d in remain_dim], 'remain_cats': [c['name'] for c in remain_cat]})
    goto_eval(drv)
    m = page_metrics(drv)
    log('清理后列表条数回到基线 56', '共 56 条' in (m['footer_total'] or ''), m)


def phase_category_group_edit(drv):
    tab_click(drv, '分组视图')
    time.sleep(1.2)
    js_click(drv, one(drv, "//button[@aria-label='编辑分类 %s']" % CAT_NAME, timeout=20))
    dlg = one(drv, "//*[@data-slot='dialog-content'][.//*[@data-slot='dialog-title'][normalize-space(.)='编辑分类']]", timeout=10)
    name_val = dlg.find_element(By.ID, 'category-name').get_attribute('value')
    desc_val = dlg.find_element(By.ID, 'category-description').get_attribute('value')
    log('分类弹窗-5 分组视图编辑反填', name_val == CAT_NAME and desc_val == 'INT-1484 分类描述',
        {'name': name_val, 'desc': desc_val})
    clear_and_type(drv, dlg.find_element(By.ID, 'category-description'), 'INT-1484 分类描述(分组改)')
    js_click(drv, dlg.find_element(By.XPATH, ".//button[@type='submit']"))
    hits = wait_net(drv, '/evaluation/categories', 'PUT', timeout=30)
    st, body = api_call('GET', '/evaluation/categories?per_page=100')
    items = (body or {}).get('data', {}).get('items', []) if isinstance(body, dict) else []
    mine = [c for c in items if c.get('name') == CAT_NAME]
    log('分类弹窗-6 编辑保存 PUT + GET 回读',
        bool(hits) and 200 <= int(hits[-1].get('status', 0)) < 300 and mine
        and mine[0].get('description') == 'INT-1484 分类描述(分组改)',
        {'status': hits[-1].get('status') if hits else None,
         'readback_desc': mine[0].get('description') if mine else None})
    return bool(mine)


def phase_delete_category(drv):
    js_click(drv, one(drv, "//button[@aria-label='删除分类 %s']" % CAT_NAME, timeout=15))
    dlg = one(drv, "//*[@data-slot='dialog-content'][contains(.,'删除分类')]", timeout=10)
    dlg_text = dlg.text
    confirm = dlg.find_element(By.XPATH, ".//button[normalize-space(.)='删除']")
    shot(drv, '14_delete_category_confirm_light')
    js_click(drv, confirm)
    hits = wait_net(drv, '/evaluation/categories', 'DELETE', timeout=30)
    time.sleep(1.2)
    st, body = api_call('GET', '/evaluation/categories?per_page=100')
    items = (body or {}).get('data', {}).get('items', []) if isinstance(body, dict) else []
    still = [c for c in items if c.get('name') == CAT_NAME]
    dims = [d for d in api_dims() if d.get('name') == DIM_NAME_EDITED]
    cat_of_dim = None
    if dims:
        st2, b2 = api_call('GET', '/evaluation/dimensions/%s' % dims[0]['id'])
        cat_of_dim = ((b2 or {}).get('data') or {}).get('category_id')
    log('分类删除：确认弹窗 + DELETE + GET 回读（分类消失、维度归属变化）',
        '确定删除分类' in dlg_text and bool(hits) and not still,
        {'confirm_text': dlg_text[:160], 'status': hits[-1].get('status') if hits else None,
         'category_still_exists': bool(still), 'dimension_category_id_after': cat_of_dim})
    return not still


def phase_delete_dimension(drv):
    tab_click(drv, '列表视图')
    time.sleep(1.0)
    search_dim(drv, DIM_NAME_EDITED)
    row_button(drv, '删除维度 %s' % DIM_NAME_EDITED)
    dlg = one(drv, "//*[@data-slot='dialog-content'][contains(.,'删除维度')]", timeout=10)
    dlg_text = dlg.text
    shot(drv, '15_delete_dimension_confirm_light')
    js_click(drv, dlg.find_element(By.XPATH, ".//button[normalize-space(.)='删除']"))
    hits = wait_net(drv, '/evaluation/dimensions', 'DELETE', timeout=30)
    time.sleep(1.2)
    dims = api_dims()
    still = [d for d in dims if d.get('name') == DIM_NAME_EDITED]
    log('维度删除：确认弹窗 + DELETE + GET 回读（列表消失）',
        '确定要删除维度' in dlg_text and bool(hits) and not still,
        {'confirm_text': dlg_text[:160], 'status': hits[-1].get('status') if hits else None,
         'still_in_list': bool(still), 'total': len(dims)})
    return not still


def phase_health_offline(drv):
    st, body = api_call('POST', '/evaluation/dimensions', {
        'name': OFFLINE_DIM, 'type': 'auto', 'dimension_type': 'main',
        'category_id': None, 'status': True, 'weight': 5,
        'result_type': 1, 'result_min': 0, 'result_max': 100, 'decimal_places': 2,
        'estimated_exec_time': 5,
        'rule': {'rules': [{'condition': '>=', 'value': 90, 'score': 10}]},
        'api_endpoints': [{'url': 'http://127.0.0.1:59999/health', 'name': '不可达端点', 'priority': 1,
                           'maxProcess': 5, 'maxTimeout': 30, 'maxAudioDuration': 60}],
        'api_settings': {'method': 'POST', 'timeout': 30000, 'headers': {}, 'bodyTemplate': {}},
    })
    dim_id = ((body or {}).get('data') or {}).get('id') if isinstance(body, dict) else None
    log('健康测试-0 建立离线维度（POST /evaluation/dimensions）', st in (200, 201) and dim_id is not None,
        {'status': st, 'id': dim_id, 'resp': json.dumps(body, ensure_ascii=False)[:200] if not dim_id else ''})
    goto_eval(drv)
    search_dim(drv, OFFLINE_DIM)
    row_button(drv, '测试维度 %s 的 API' % OFFLINE_DIM)
    dlg = one(drv, "//*[@data-slot='dialog-content'][.//*[@data-slot='dialog-title'][contains(.,'API健康测试')]]", timeout=10)
    hits = wait_net(drv, '/health', 'GET', timeout=40)
    time.sleep(1.5)
    txt = dlg.text
    rows = dlg.find_elements(By.CSS_SELECTOR, 'tbody tr')
    log('健康测试-2 离线端点（不可达 59999）',
        bool(hits) and rows and '离线' in txt,
        {'status': hits[-1]['status'] if hits else None,
         'resp': (hits[-1].get('resBody') or '')[:400] if hits else None,
         'rows': len(rows), 'dialog_text': txt[:400]})
    shot(drv, '16_health_offline_light')
    js_click(drv, dlg.find_element(By.XPATH, ".//button[normalize-space(.)='关闭']"))
    time.sleep(0.8)
    search_dim(drv, '')


def phase_health_no_endpoint(drv):
    """真实维度（无端点）健康测试：观察空结果时的总状态展示（只读观察，不改数据）。"""
    search_dim(drv, '拒识成功数量')
    time.sleep(0.8)
    try:
        row_button(drv, '测试维度 拒识成功数量 的 API')
    except Exception:
        log('健康测试-3 无端点真实维度（未找到行）', False, {})
        search_dim(drv, '')
        return
    dlg = one(drv, "//*[@data-slot='dialog-content'][.//*[@data-slot='dialog-title'][contains(.,'API健康测试')]]", timeout=10)
    hits = wait_net(drv, '/health', 'GET', timeout=40)
    time.sleep(1.5)
    txt = dlg.text
    rows = dlg.find_elements(By.CSS_SELECTOR, 'tbody tr')
    shot(drv, '17_health_no_endpoint_light')
    log('健康测试-3 无端点真实维度观察（端点表 0 行时总状态）', True,
        {'status': hits[-1]['status'] if hits else None,
         'resp': (hits[-1].get('resBody') or '')[:300] if hits else None,
         'rows': len(rows), 'dialog_text': txt[:300]})
    js_click(drv, dlg.find_element(By.XPATH, ".//button[normalize-space(.)='关闭']"))
    time.sleep(0.6)
    search_dim(drv, '')


def main():
    t0 = time.time()
    drv = _driver()
    cat_id = None
    try:
        login(drv)
        cat_id = phase_page_and_category(drv)
        create_info = phase_dimension_create(drv)
        log('维度回读-新建后 GET 详情字段核对',
            bool(create_info) and create_info['name'] == DIM_NAME
            and create_info['category_id'] is not None
            and len(create_info['inputs']) >= 2 and len(create_info['outputs']) >= 1
            and any('15000/health' in (u or '') for u, _ in create_info['endpoints'])
            and len(create_info['algorithms']) == 1,
            create_info)
        edit_info = phase_dimension_edit(drv)
        log('维度回读-编辑后 GET 详情字段核对',
            bool(edit_info) and edit_info['name'] == DIM_NAME_EDITED
            and edit_info['desc'] == 'INT-1484 维度描述(已改)'
            and any(i[0] == 'asr_result' for i in edit_info['inputs'])
            and any(o[0] == 'score_v2' for o in edit_info['outputs'])
            and any('(改)' in (e[1] or '') for e in edit_info['endpoints']),
            edit_info)
        phase_rule_calc(drv)
        phase_health(drv)
        phase_health_offline(drv)
        phase_health_no_endpoint(drv)
        phase_empty_state(drv)
        phase_error_state(drv)
        phase_cancel_reopen(drv)
        phase_dark(drv)
        # 分组视图分类编辑（此时分类下已有维度）
        cat_ok = phase_category_group_edit(drv)
        # 删除维度闭环
        phase_delete_dimension(drv)
    except Exception:
        log('EXCEPTION', False, traceback.format_exc()[-1800:])
    finally:
        try:
            phase_cleanup(drv, cat_id)
        except Exception:
            log('CLEANUP-EXCEPTION', False, traceback.format_exc()[-800:])
        with open(os.path.join(ART, 'result_main.json'), 'w', encoding='utf-8') as f:
            json.dump({'stamp': STAMP, 'elapsed_s': round(time.time() - t0, 1),
                       'result': RESULT, 'net': NET}, f, ensure_ascii=False, indent=1)
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
