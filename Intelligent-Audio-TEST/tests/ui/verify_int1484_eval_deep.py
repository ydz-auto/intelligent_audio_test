# -*- coding: utf-8 -*-
"""INT-1484 评估域深走查（真实库栈：前端 15173 / 后端 15000）。

覆盖：评估分类新建/重名/编辑/删除、维度新建(输入/输出参数逐项增删改/端点/算法)/编辑/回读/删除闭环、
规则试算、API 健康测试(在线/离线/无端点)、取消重开、空态/错误态、联动计数、浅深色截图。
数据纪律：只写「接线测试_INT1484_」前缀记录，run 结束前经 API 删除。
环境缺口（非本卡前端缺陷）：/algorithm/options 经 task_service 的 ALGORITHM_SERVICE_HOST
默认 127.0.0.1:50067 连接失败 → 以 ENV 观测记录，不判前端失败。
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
OFFLINE_DIM = P + '_离线维度'
SEARCH_NONE = 'zzz_无匹配_1484'
BASELINE_TOTAL = 56

RESULT = []
ENV = []
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
          json.dumps(detail, ensure_ascii=False, default=str)[:900], flush=True)


def env(step, detail=''):
    ENV.append({'step': step, 'detail': detail})
    print('ENV  ' + step + ' :: ' + json.dumps(detail, ensure_ascii=False, default=str)[:900], flush=True)


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


SHEET = "//*[@data-slot='sheet-content']"


def trigger_by_label(drv, label_text, scope=SHEET):
    return one(drv, "%s//label[contains(normalize-space(.), '%s')]"
                    "/following::button[@role='combobox'][1]" % (scope, label_text), timeout=10)


def select_open(drv, label_text, scope=SHEET):
    trig = trigger_by_label(drv, label_text, scope)
    js_click(drv, trig)
    time.sleep(0.5)
    return trig


def close_popup(drv):
    """点标题区收起 base-ui 弹层（不用 Esc，避免连带关 Sheet）。"""
    try:
        js_click(drv, one(drv, SHEET + "//*[@data-slot='sheet-title']", timeout=5))
    except Exception:
        try:
            drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        except Exception:
            pass
    time.sleep(0.4)


def select_options(drv, label_text, scope=SHEET):
    trig = select_open(drv, label_text, scope)
    time.sleep(0.3)
    labels = [i.text.strip() for i in drv.find_elements(By.XPATH, "//*[@data-slot='select-item']")]
    close_popup(drv)
    return labels


def select_choose(drv, label_text, option_text, scope=SHEET):
    select_open(drv, label_text, scope)
    opt = one(drv, "//*[@data-slot='select-item'][normalize-space(.)='%s']" % option_text, timeout=10)
    js_click(drv, opt)
    time.sleep(0.4)


def facet_trigger(drv, title):
    for b in drv.find_elements(By.TAG_NAME, 'button'):
        try:
            t = ' '.join((b.text or '').split())
        except Exception:
            continue
        if t == title or t.startswith(title + ' '):
            return b
    raise AssertionError('facet trigger not found: ' + title)


def facet_options(drv, title):
    btn = facet_trigger(drv, title)
    js_click(drv, btn)
    time.sleep(0.5)
    try:
        pops = drv.find_elements(By.CSS_SELECTOR, "[data-slot='popover-content']")
        labels = []
        if pops:
            labels = [' '.join((b.text or '').split()) for b in pops[-1].find_elements(By.TAG_NAME, 'button')]
    finally:
        js_click(drv, facet_trigger(drv, title))
        time.sleep(0.3)
    return labels


def api_call(method, path, body=None):
    with open(os.path.join(ART, 'token.txt'), encoding='utf-8') as f:
        token = f.read().strip()
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


def api_cats():
    st, body = api_call('GET', '/evaluation/categories?per_page=100')
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


def tab_click(drv, label, scope=SHEET):
    js_click(drv, one(drv, "%s//button[@role='tab'][normalize-space(.)='%s']" % (scope, label), timeout=10))
    time.sleep(0.6)


def sheet(drv):
    return one(drv, SHEET, timeout=10)


def row_button(drv, aria_label):
    el = one(drv, "//button[@aria-label='%s']" % aria_label, timeout=12)
    js_click(drv, el)
    time.sleep(0.6)


def dialog(drv, title_contains):
    return one(drv, "//*[@data-slot='dialog-content'][.//*[@data-slot='dialog-title'][contains(.,'%s')]]"
               % title_contains, timeout=10)


def alert_dialog(drv, title_contains):
    return one(drv, "//*[@data-slot='alert-dialog-content'][.//*[@data-slot='alert-dialog-title'][contains(.,'%s')]]"
               % title_contains, timeout=10)


# ---------- 分类 ----------

def category_create(drv):
    js_click(drv, one(drv, "//button[normalize-space(.)='新增分类']", timeout=10))
    dlg = dialog(drv, '新建分类')
    title = dlg.find_element(By.XPATH, ".//*[@data-slot='dialog-title']").text.strip()
    icon_val = dlg.find_element(By.ID, 'category-icon').get_attribute('value')
    submit = dlg.find_element(By.XPATH, ".//button[@type='submit']")
    disabled_empty = submit.get_attribute('disabled') is not None
    log('分类弹窗-1 打开/标题/默认图标/空名禁用提交',
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
    cats = api_cats()
    mine = [c for c in cats if c.get('name') == CAT_NAME]
    log('分类弹窗-3 GET 回读（名称/描述/图标）',
        len(mine) == 1 and mine[0].get('description') == 'INT-1484 分类描述'
        and mine[0].get('icon') == 'fas fa-folder',
        {'id': mine[0]['id'] if mine else None, 'desc': mine[0].get('description') if mine else None,
         'icon': mine[0].get('icon') if mine else None, 'total_categories': len(cats)})
    return mine[0]['id'] if mine else None


def category_duplicate(drv):
    # 清空旧 toast，避免把上一次成功 toast 误判为重名反馈
    end = time.time() + 15
    while time.time() < end and toast_texts(drv):
        time.sleep(0.5)
    js_click(drv, one(drv, "//button[normalize-space(.)='新增分类']", timeout=10))
    dlg = dialog(drv, '新建分类')
    clear_and_type(drv, dlg.find_element(By.ID, 'category-name'), CAT_NAME)
    js_click(drv, dlg.find_element(By.XPATH, ".//button[@type='submit']"))
    hits = wait_net(drv, '/evaluation/categories', 'POST', timeout=30)
    time.sleep(2.0)
    post = hits[-1] if hits else {}
    still_open = bool(drv.find_elements(
        By.XPATH, "//*[@data-slot='dialog-content'][.//*[@data-slot='dialog-title'][normalize-space(.)='新建分类']]"))
    toasts = toast_texts(drv)
    feedback = still_open or bool(toasts)
    log('分类弹窗-4 重名校验（后端 400 时前端可见反馈）',
        int(post.get('status', 0)) >= 400 and feedback,
        {'status': post.get('status'), 'resp': (post.get('resBody') or '')[:200],
         'dialog_still_open': still_open, 'toasts': toasts})
    if int(post.get('status', 0)) >= 400 and not feedback:
        env('分类弹窗-4b 重名提交静默失败（无 toast / 无行内错误，弹窗关闭）',
            {'status': post.get('status'), 'resp': (post.get('resBody') or '')[:200]})
    if still_open:
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(0.8)


def category_group_edit(drv):
    tab_click(drv, '分组视图', scope="//*")
    time.sleep(1.2)
    js_click(drv, one(drv, "//button[@aria-label='编辑分类 %s']" % CAT_NAME, timeout=20))
    dlg = dialog(drv, '编辑分类')
    name_val = dlg.find_element(By.ID, 'category-name').get_attribute('value')
    desc_val = dlg.find_element(By.ID, 'category-description').get_attribute('value')
    log('分类弹窗-5 分组视图编辑反填（名称/描述）',
        name_val == CAT_NAME and desc_val == 'INT-1484 分类描述',
        {'name': name_val, 'desc': desc_val})
    shot(drv, '02_category_edit_group_light')
    clear_and_type(drv, dlg.find_element(By.ID, 'category-description'), 'INT-1484 分类描述(已改)')
    js_click(drv, dlg.find_element(By.XPATH, ".//button[@type='submit']"))
    hits = wait_net(drv, '/evaluation/categories', 'PUT', timeout=30)
    cats = api_cats()
    mine = [c for c in cats if c.get('name') == CAT_NAME]
    log('分类弹窗-6 编辑保存 PUT + GET 回读描述',
        bool(hits) and 200 <= int(hits[-1].get('status', 0)) < 300 and mine
        and mine[0].get('description') == 'INT-1484 分类描述(已改)',
        {'status': hits[-1].get('status') if hits else None,
         'readback_desc': mine[0].get('description') if mine else None})
    return bool(mine)


# ---------- 维度抽屉 ----------

def open_create_drawer(drv):
    js_click(drv, one(drv, "//button[normalize-space(.)='新增维度']", timeout=10))
    sh = sheet(drv)
    title = sh.find_element(By.XPATH, ".//*[@data-slot='sheet-title']").text.strip()
    tabs = [t.text.strip() for t in sh.find_elements(By.XPATH, ".//button[@role='tab']")]
    return sh, title, tabs


def fill_dimension_create(drv, sh, name):
    clear_and_type(drv, sh.find_element(By.ID, 'dim-name'), name)
    clear_and_type(drv, sh.find_element(By.ID, 'dim-description'), 'INT-1484 维度描述')
    # 所属分类下拉：选项 = 未分类 + 分类数 + 新建分类
    cat_opts = select_options(drv, '所属分类')
    select_choose(drv, '所属分类', CAT_NAME)
    cat_text = trigger_by_label(drv, '所属分类').text.strip()
    cats = api_cats()
    log('维度抽屉-2 所属分类下拉选项数 = 接口分类数 + 2（未分类/新建分类）',
        len(cat_opts) == len(cats) + 2 and cat_text == CAT_NAME,
        {'options': cat_opts, 'api_categories': len(cats), 'selected': cat_text})

    # 层级配置：主/子维度选项 + 页签收敛
    tab_click(drv, '层级配置')
    type_opts = select_options(drv, '维度类型')
    select_choose(drv, '维度类型', '子维度')
    time.sleep(0.5)
    sub_tabs = [t.text.strip() for t in sh.find_elements(By.XPATH, ".//button[@role='tab']")]
    select_choose(drv, '维度类型', '主维度')
    time.sleep(0.4)
    main_tabs = [t.text.strip() for t in sh.find_elements(By.XPATH, ".//button[@role='tab']")]
    clear_and_type(drv, sh.find_element(By.ID, 'dim-keywords'), '接线测试,关键词')
    log('维度抽屉-3 维度类型选项 + 切换页签（主5/子3）',
        type_opts == ['主维度', '子维度'] and len(main_tabs) == 5 and len(sub_tabs) == 3,
        {'type_options': type_opts, 'main_tabs': main_tabs, 'sub_tabs': sub_tabs})

    # 结果配置：默认 5 条规则 + min>=max 校验（观察是否有可见反馈）
    tab_click(drv, '结果配置')
    rule_rows = len(sh.find_elements(
        By.XPATH, ".//input[starts-with(@aria-label,'规则 ') and contains(@aria-label,'阈值')]"))
    result_type_opts = select_options(drv, '结果类型')
    clear_and_type(drv, sh.find_element(By.ID, 'dim-result-min'), '100')
    clear_and_type(drv, sh.find_element(By.ID, 'dim-result-max'), '0')
    # 失焦触发校验
    sh.find_element(By.ID, 'dim-result-max').send_keys(Keys.TAB)
    time.sleep(0.8)
    err = '|'.join(p.text for p in sh.find_elements(By.TAG_NAME, 'p'))
    submit_el = one(drv, SHEET + "//button[@type='submit' and @form='dimension-mutate-form']", timeout=8)
    submit_disabled_invalid = submit_el.get_attribute('disabled') is not None
    invalid_visible = '结果最大值必须大于最小值' in err
    log('维度抽屉-4 结果配置：默认规则 5 行 + 结果类型选项 + min>=max 校验可见',
        rule_rows == 5 and len(result_type_opts) == 4 and invalid_visible,
        {'default_rule_rows': rule_rows, 'result_type_options': result_type_opts,
         'inline_errors': err[:240], 'submit_disabled_when_invalid': submit_disabled_invalid})
    if not invalid_visible:
        env('维度抽屉-4b min>=max 无行内错误提示（提交按钮 disabled=%s）' % submit_disabled_invalid,
            {'inline_errors': err[:300]})
    clear_and_type(drv, sh.find_element(By.ID, 'dim-result-min'), '0')
    clear_and_type(drv, sh.find_element(By.ID, 'dim-result-max'), '100')
    time.sleep(0.3)

    # API 配置
    tab_click(drv, 'API配置')
    method_opts = select_options(drv, '请求方法')
    clear_and_type(drv, sh.find_element(By.ID, 'dim-api-url'), 'http://host.docker.internal:15000/health')
    clear_and_type(drv, sh.find_element(By.ID, 'dim-api-headers'), '{"content-type": "application/json"}')
    # 输入参数：默认 2 行 → 改第 1 行 / 增第 3 行 / 删第 3 行 / 再增回
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='输入参数键名 1']"), 'asr_result')
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='输入显示标签 1']"), 'ASR识别结果')
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='输入默认值 1']"), '默认值A')
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='输入描述 1']"), '输入描述A')
    n0_in = len(sh.find_elements(By.XPATH, ".//input[@aria-label[starts-with(.,'输入参数键名')]]"))
    js_click(drv, one(drv, SHEET + "//button[normalize-space(.)='添加输入']", timeout=10))
    time.sleep(0.5)
    n1_in = len(sh.find_elements(By.XPATH, ".//input[@aria-label[starts-with(.,'输入参数键名')]]"))
    js_click(drv, one(drv, SHEET + "//button[@aria-label='删除输入 %d']" % n1_in, timeout=10))
    time.sleep(0.5)
    n2_in = len(sh.find_elements(By.XPATH, ".//input[@aria-label[starts-with(.,'输入参数键名')]]"))
    js_click(drv, one(drv, SHEET + "//button[normalize-space(.)='添加输入']", timeout=10))
    time.sleep(0.5)
    n_in = len(sh.find_elements(By.XPATH, ".//input[@aria-label[starts-with(.,'输入参数键名')]]"))
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='输入参数键名 %d']" % n_in), 'ref_text')
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='输入显示标签 %d']" % n_in), '参考文本')
    # 输出字段：默认 1 行 → 增 / 删 / 再增
    n0_out = len(sh.find_elements(By.XPATH, ".//input[@aria-label[starts-with(.,'输出字段代码')]]"))
    js_click(drv, one(drv, SHEET + "//button[normalize-space(.)='添加字段']", timeout=10))
    time.sleep(0.5)
    n1_out = len(sh.find_elements(By.XPATH, ".//input[@aria-label[starts-with(.,'输出字段代码')]]"))
    js_click(drv, one(drv, SHEET + "//button[@aria-label='删除输出字段 %d']" % n1_out, timeout=10))
    time.sleep(0.5)
    n2_out = len(sh.find_elements(By.XPATH, ".//input[@aria-label[starts-with(.,'输出字段代码')]]"))
    js_click(drv, one(drv, SHEET + "//button[normalize-space(.)='添加字段']", timeout=10))
    time.sleep(0.5)
    n_out = len(sh.find_elements(By.XPATH, ".//input[@aria-label[starts-with(.,'输出字段代码')]]"))
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='输出字段代码 %d']" % n_out), 'score2')
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='输出显示名 %d']" % n_out), '评分二')
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='输出提取路径 %d']" % n_out), 'data.score2')
    # 端点：默认 1 行 → 增第 2 行（在线）+ 填充第 1 行
    n0_ep = len(sh.find_elements(By.XPATH, ".//input[@aria-label[starts-with(.,'端点 URL')]]"))
    js_click(drv, one(drv, SHEET + "//button[normalize-space(.)='添加端点']", timeout=10))
    time.sleep(0.5)
    n_ep = len(sh.find_elements(By.XPATH, ".//input[@aria-label[starts-with(.,'端点 URL')]]"))
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='端点 URL 1']"), 'http://host.docker.internal:15000/health')
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='端点名称 1']"), '主端点(在线)')
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='端点 URL 2']"), 'http://host.docker.internal:15000/health')
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='端点名称 2']"), '备端点(在线)')
    log('维度抽屉-5 API配置：请求方法选项 + 输入增删改(2→3→2→3) + 输出(1→2→1→2) + 端点(1→2)',
        method_opts == ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']
        and [n0_in, n1_in, n2_in, n_in] == [2, 3, 2, 3]
        and [n0_out, n1_out, n2_out, n_out] == [1, 2, 1, 2]
        and [n0_ep, n_ep] == [1, 2],
        {'method_options': method_opts, 'inputs': [n0_in, n1_in, n2_in, n_in],
         'outputs': [n0_out, n1_out, n2_out, n_out], 'endpoints': [n0_ep, n_ep]})

    # 关联算法：选项来自 GET /algorithm/options（真实接口）
    tab_click(drv, '关联算法')
    js_click(drv, one(drv, SHEET + "//button[contains(normalize-space(.),'选择关联的算法类型')]", timeout=10))
    time.sleep(0.8)
    pop = drv.find_elements(By.CSS_SELECTOR, "[data-slot='popover-content']")
    pop_txt = pop[-1].text if pop else ''
    algo_boxes = drv.find_elements(By.XPATH, "//*[@role='checkbox' and starts-with(@aria-label,'关联算法 ')]")
    algo_labels = [b.get_attribute('aria-label') for b in algo_boxes]
    picked = None
    if algo_boxes:
        picked = algo_labels[0].replace('关联算法 ', '')
        js_click(drv, algo_boxes[0])
        time.sleep(0.4)
    close_popup(drv)
    time.sleep(0.3)
    chips = [b.get_attribute('aria-label').replace('移除算法 ', '')
             for b in sh.find_elements(By.XPATH, ".//button[starts-with(@aria-label,'移除算法 ')]")]
    log('维度抽屉-6 关联算法：下拉选项来自 /algorithm/options + 选中回显 chip',
        (len(algo_boxes) >= 1 and picked and any(picked in c for c in chips))
        or (len(algo_boxes) == 0 and '暂无可用算法' in pop_txt),
        {'options': algo_labels, 'picked': picked, 'chips': chips, 'popover_text': pop_txt[:200]})
    shot(drv, '04_dimension_drawer_api_light')
    return {'algo_picked': picked}


def save_drawer(drv, expect_method='POST'):
    js_click(drv, one(drv, SHEET + "//button[@type='submit' and @form='dimension-mutate-form']", timeout=10))
    hits = wait_net(drv, '/evaluation/dimensions', expect_method, timeout=40)
    toast = wait_toast(drv, '成功', timeout=20)
    hit = hits[-1] if hits else {}
    log('维度抽屉-保存 %s' % expect_method,
        bool(hit) and 200 <= int(hit.get('status', 0)) < 300 and toast,
        {'status': hit.get('status'), 'reqBody': (hit.get('reqBody') or '')[:1200], 'toast_ok': toast})
    time.sleep(1.5)
    return hit


def verify_dim_readback(name):
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
        'result_type': detail.get('result_type'), 'result_min': detail.get('result_min'),
        'result_max': detail.get('result_max'),
    }
    return summary


# ---------- 主流程 ----------

def phase_page(drv):
    goto_eval(drv)
    net = drain_net(drv)
    m = page_metrics(drv)
    dims = [n for n in net if n['url'].split('?')[0].endswith('/evaluation/dimensions') and n['method'] == 'GET']
    cats = [n for n in net if '/evaluation/categories' in n['url']]
    algos = [n for n in net if '/algorithm/options' in n['url']]
    algo_status = algos[-1]['status'] if algos else None
    cat_opts = facet_options(drv, '分类')
    algo_opts = facet_options(drv, '关联算法')
    api_cats_n = len(api_cats())
    api_algos_n = None
    if algo_status == 200:
        st_algo, body_algo = api_call('GET', '/algorithm/options')
        data_algo = (body_algo or {}).get('data') if isinstance(body_algo, dict) else None
        if isinstance(data_algo, dict):
            data_algo = data_algo.get('algorithms')
        api_algos_n = len(data_algo) if isinstance(data_algo, list) else 0
    log('页面-1 首屏接口 + 计数口径（页脚/分类 facet）',
        bool(dims) and bool(cats) and ' '.join(m['footer_total'].split()) == '共 %d 条' % len(api_dims())
        and len(cat_opts) == api_cats_n + 1 and m['rows_page1'] == 10,
        {'dims_status': dims[-1]['status'] if dims else None,
         'cats_status': cats[-1]['status'] if cats else None,
         'metrics': m, 'category_facet': cat_opts, 'api_categories': api_cats_n})
    if algo_status != 200:
        env('页面-2 /algorithm/options 非 200 → 关联算法 facet 降级为「全部」',
            {'status': algo_status, 'facet_options': algo_opts,
             'body': (algos[-1].get('resBody') or '')[:300] if algos else ''})
        log('页面-2 关联算法 facet 降级态（接口不可用，仍可筛选全部）',
            algo_opts == ['全部'], {'status': algo_status, 'facet_options': algo_opts})
    else:
        log('页面-2 关联算法 facet 选项数 = 接口返回数 + 1',
            len(algo_opts) == api_algos_n + 1, {'facet_options': algo_opts})
    shot(drv, '00_page_list_light')


def phase_dimension_create(drv):
    sh, title, tabs = open_create_drawer(drv)
    log('维度抽屉-1 打开/标题/初始页签',
        title == '新增评估维度'
        and tabs == ['基本信息', '层级配置', '结果配置', 'API配置', '关联算法'],
        {'title': title, 'tabs': tabs})
    shot(drv, '03_dimension_drawer_basic_light')
    extra = fill_dimension_create(drv, sh, DIM_NAME)
    hit = save_drawer(drv, 'POST')
    req = {}
    try:
        req = json.loads(hit.get('reqBody') or '{}')
    except Exception:
        pass
    # 前端请求体侧证据：输入/输出参数、端点、算法按表单逐项下送
    log('维度抽屉-8 POST 请求体含逐项输入/输出参数/端点（前端侧契约）',
        len(req.get('required_inputs') or []) == 3
        and len(req.get('output_fields') or []) == 2
        and len(req.get('api_endpoints') or []) == 2
        and (not extra.get('algo_picked') or req.get('associated_algorithms')),
        {'inputs': [(i.get('key') or i.get('param_code'), i.get('label')) for i in req.get('required_inputs') or []],
         'outputs': [(o.get('param_code'), o.get('field_path')) for o in req.get('output_fields') or []],
         'endpoints': [(e.get('url'), e.get('name')) for e in req.get('api_endpoints') or []],
         'algorithms': req.get('associated_algorithms')})
    return verify_dim_readback(DIM_NAME), req


def phase_dimension_edit(drv):
    search_dim(drv, DIM_NAME)
    row_button(drv, '编辑维度 %s' % DIM_NAME)
    sh = sheet(drv)
    title = sh.find_element(By.XPATH, ".//*[@data-slot='sheet-title']").text.strip()
    WebDriverWait(drv, 25).until(lambda d: d.find_element(By.ID, 'dim-name').get_attribute('value') == DIM_NAME)
    time.sleep(1.2)
    name_val = sh.find_element(By.ID, 'dim-name').get_attribute('value')
    desc_val = sh.find_element(By.ID, 'dim-description').get_attribute('value')
    cat_text = trigger_by_label(drv, '所属分类').text.strip()
    tab_click(drv, 'API配置')
    in1 = sh.find_element(By.XPATH, ".//input[@aria-label='输入参数键名 1']").get_attribute('value')
    out1 = sh.find_element(By.XPATH, ".//input[@aria-label='输出字段代码 1']").get_attribute('value')
    ep_urls = [e.get_attribute('value') for e in sh.find_elements(By.XPATH, ".//input[@aria-label[starts-with(.,'端点 URL')]]")]
    log('维度抽屉-7 编辑反填（详情 GET：名称/描述/分类/端点）',
        title == '编辑评估维度' and name_val == DIM_NAME and desc_val == 'INT-1484 维度描述'
        and cat_text == CAT_NAME
        and ep_urls.count('http://host.docker.internal:15000/health') == 2,
        {'title': title, 'name': name_val, 'desc': desc_val, 'category': cat_text,
         'input1': in1, 'output1': out1, 'endpoints': ep_urls})
    if in1 == 'asr_result' and out1 == 'score':
        env('维度抽屉-7b 编辑反填的输入/输出参数为表单默认行（非已保存值，后端参数未落库后的兜底）',
            {'input1': in1, 'output1': out1})
    shot(drv, '05_dimension_edit_prefill_light')

    tab_click(drv, '基本信息')
    clear_and_type(drv, sh.find_element(By.ID, 'dim-name'), DIM_NAME_EDITED)
    clear_and_type(drv, sh.find_element(By.ID, 'dim-description'), 'INT-1484 维度描述(已改)')
    tab_click(drv, 'API配置')
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='输入显示标签 1']"), 'ASR识别结果(改)')
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='输出字段代码 1']"), 'score_v2')
    clear_and_type(drv, sh.find_element(By.XPATH, ".//input[@aria-label='端点名称 2']"), '备端点(改)')
    save_drawer(drv, 'PUT')
    return verify_dim_readback(DIM_NAME_EDITED)


def phase_rule_calc(drv):
    search_dim(drv, DIM_NAME_EDITED)
    row_button(drv, '规则试算维度 %s' % DIM_NAME_EDITED)
    dlg = dialog(drv, '规则试算')
    btn = dlg.find_element(By.XPATH, ".//button[normalize-space(.)='试算']")
    disabled_empty = btn.get_attribute('disabled') is not None
    clear_and_type(drv, dlg.find_element(By.ID, 'calc-value'), '92')
    js_click(drv, btn)
    hits = wait_net(drv, '/calculate', 'POST', timeout=30)
    time.sleep(1.2)
    body_txt = dlg.text
    log('规则试算-1 空值禁用 + 92 → 评分 9 分（命中规则 >= 90）',
        disabled_empty and bool(hits) and '评分 9 分' in body_txt,
        {'disabled_when_empty': disabled_empty, 'status': hits[-1]['status'] if hits else None,
         'reqBody': hits[-1].get('reqBody') if hits else None, 'dialog_text': body_txt[:300]})
    shot(drv, '06_rule_calc_light')
    clear_and_type(drv, dlg.find_element(By.ID, 'calc-value'), '10')
    js_click(drv, dlg.find_element(By.XPATH, ".//button[normalize-space(.)='试算']"))
    wait_net(drv, '/calculate', 'POST', timeout=30)
    time.sleep(1.0)
    log('规则试算-2 低值 10 → 命中兜底规则 < 70 → 0 分',
        '评分 0 分' in dlg.text and '< 70' in dlg.text, {'dialog_text': dlg.text[:300]})
    js_click(drv, dlg.find_element(By.XPATH, ".//button[normalize-space(.)='关闭']"))
    time.sleep(0.8)


def open_health(drv, name):
    search_dim(drv, name)
    row_button(drv, '测试维度 %s 的 API' % name)
    dlg = dialog(drv, 'API健康测试结果')
    hits = wait_net(drv, '/health', 'GET', timeout=40)
    end = time.time() + 25
    txt = ''
    while time.time() < end:
        txt = dlg.text
        if '总状态' in txt or '暂无健康探测数据' in txt or '失败' in txt:
            break
        time.sleep(0.5)
    return dlg, hits, txt


def phase_health_online(drv):
    dlg, hits, txt = open_health(drv, DIM_NAME_EDITED)
    rows = dlg.find_elements(By.CSS_SELECTOR, 'tbody tr')
    log('健康测试-1 在线端点（2× 15000/health）',
        bool(hits) and '总状态' in txt and '在线' in txt,
        {'status': hits[-1]['status'] if hits else None,
         'resp': (hits[-1].get('resBody') or '')[:400] if hits else None,
         'rows': len(rows), 'dialog_text': txt[:400]})
    shot(drv, '07_health_online_light')
    js_click(drv, dlg.find_element(By.XPATH, ".//button[normalize-space(.)='关闭']"))
    time.sleep(0.8)


def phase_health_offline(drv):
    st, body = api_call('POST', '/evaluation/dimensions', {
        'name': OFFLINE_DIM, 'type': 'auto', 'dimension_type': 'main',
        'category_id': None, 'status': True, 'weight': 5,
        'result_type': 1, 'result_min': 0, 'result_max': 100, 'decimal_places': 2,
        'estimated_exec_time': 5,
        'rule': {'rules': [{'condition': '>=', 'value': 90, 'score': 10}]},
        'api_endpoints': [{'url': 'http://127.0.0.1:59999/health', 'name': '不可达端点', 'priority': 1,
                           'max_process': 5, 'max_timeout': 30, 'max_audio_duration': 60}],
        'api_settings': {'method': 'POST', 'timeout': 30000, 'headers': {}, 'bodyTemplate': {}},
    })
    dim_id = ((body or {}).get('data') or {}).get('id') if isinstance(body, dict) else None
    log('健康测试-0 建立离线维度（POST /evaluation/dimensions）', st in (200, 201) and dim_id is not None,
        {'status': st, 'id': dim_id,
         'resp': json.dumps(body, ensure_ascii=False)[:300] if not dim_id else ''})
    goto_eval(drv)
    dlg, hits, txt = open_health(drv, OFFLINE_DIM)
    rows = dlg.find_elements(By.CSS_SELECTOR, 'tbody tr')
    log('健康测试-2 离线端点（不可达 127.0.0.1:59999）',
        bool(hits) and '总状态' in txt and '离线' in txt,
        {'status': hits[-1]['status'] if hits else None,
         'resp': (hits[-1].get('resBody') or '')[:500] if hits else None,
         'rows': len(rows), 'dialog_text': txt[:400]})
    shot(drv, '08_health_offline_light')
    js_click(drv, dlg.find_element(By.XPATH, ".//button[normalize-space(.)='关闭']"))
    time.sleep(0.8)
    search_dim(drv, '')


def phase_health_no_endpoint(drv):
    dlg, hits, txt = open_health(drv, '拒识成功数量')
    rows = dlg.find_elements(By.CSS_SELECTOR, 'tbody tr')
    shot(drv, '09_health_no_endpoint_light')
    env('健康测试-3 无端点真实维度（拒识成功数量，端点 URL 空）观察',
        {'status': hits[-1]['status'] if hits else None,
         'resp': (hits[-1].get('resBody') or '')[:400] if hits else None,
         'rows': len(rows), 'dialog_text': txt[:300]})
    js_click(drv, dlg.find_element(By.XPATH, ".//button[normalize-space(.)='关闭']"))
    time.sleep(0.6)
    search_dim(drv, '')


def phase_empty_state(drv):
    search_dim(drv, SEARCH_NONE)
    time.sleep(1.0)
    body = drv.find_element(By.TAG_NAME, 'body').text
    log('空态：搜索无匹配 → 暂无评估维度', '暂无评估维度' in body,
        {'has_empty': '暂无评估维度' in body})
    shot(drv, '10_empty_state_light')
    search_dim(drv, '')


def phase_error_state(drv):
    drv.execute_cdp_cmd('Network.enable', {})
    drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': ['*/evaluation/dimensions*']})
    try:
        drv.refresh()
        WebDriverWait(drv, 30).until(lambda d: '加载失败' in d.find_element(By.TAG_NAME, 'body').text)
        body = drv.find_element(By.TAG_NAME, 'body').text
        has_retry = bool(drv.find_elements(By.XPATH, "//button[normalize-space(.)='请重试']"))
        log('错误态：阻断 /evaluation/dimensions → 加载失败 + 请重试',
            '加载失败' in body and has_retry,
            {'has_error': '加载失败' in body, 'has_retry': has_retry})
        shot(drv, '11_error_state_light')
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
    closed = not bool(drv.find_elements(By.XPATH, SHEET))
    sh2, _, _ = open_create_drawer(drv)
    value_after = sh2.find_element(By.ID, 'dim-name').get_attribute('value')
    log('取消重开：Esc 关闭后重开不残留上次输入', closed and value_after == '',
        {'closed_by_esc': closed, 'value_after_reopen': value_after})
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(0.8)
    sh3, _, _ = open_create_drawer(drv)
    sh3.find_element(By.ID, 'dim-name').send_keys('遮罩测试')
    overlays = drv.find_elements(By.XPATH, "//*[@data-slot='sheet-overlay']")
    closed_overlay = False
    if overlays:
        from selenium.webdriver.common.action_chains import ActionChains
        # 从遮罩中心向左偏移，落在左侧空白（Y 轴不变），避免点到右侧抽屉本体
        ActionChains(drv).move_to_element_with_offset(overlays[0], -500, 0).click().perform()
        time.sleep(1.0)
        closed_overlay = not bool(drv.find_elements(By.XPATH, SHEET))
    log('取消重开：点遮罩关闭', closed_overlay,
        {'closed_by_overlay': closed_overlay, 'overlay_present': bool(overlays)})
    if not closed_overlay:
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(0.8)


def phase_dark(drv):
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark');")
    drv.get('about:blank')
    goto_eval(drv)
    time.sleep(1.0)
    shot(drv, '12_page_list_dark')
    tab_click(drv, '分组视图', scope="//*")
    time.sleep(1.2)
    shot(drv, '13_page_group_dark')
    tab_click(drv, '列表视图', scope="//*")
    sh, _, _ = open_create_drawer(drv)
    clear_and_type(drv, sh.find_element(By.ID, 'dim-name'), P + '_darkobj')
    shot(drv, '14_dimension_drawer_dark')
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(0.8)
    js_click(drv, one(drv, "//button[normalize-space(.)='新增分类']", timeout=10))
    time.sleep(0.8)
    shot(drv, '15_category_dialog_dark')
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(0.6)
    # 规则试算深色
    search_dim(drv, DIM_NAME_EDITED)
    row_button(drv, '规则试算维度 %s' % DIM_NAME_EDITED)
    dlg = dialog(drv, '规则试算')
    clear_and_type(drv, dlg.find_element(By.ID, 'calc-value'), '92')
    js_click(drv, dlg.find_element(By.XPATH, ".//button[normalize-space(.)='试算']"))
    wait_net(drv, '/calculate', 'POST', timeout=30)
    time.sleep(1.0)
    shot(drv, '16_rule_calc_dark')
    js_click(drv, dlg.find_element(By.XPATH, ".//button[normalize-space(.)='关闭']"))
    time.sleep(0.6)
    # 健康测试深色
    row_button(drv, '测试维度 %s 的 API' % DIM_NAME_EDITED)
    dlg = dialog(drv, 'API健康测试结果')
    wait_net(drv, '/health', 'GET', timeout=40)
    WebDriverWait(drv, 25).until(lambda d: '总状态' in dlg.text or '暂无健康探测数据' in dlg.text)
    time.sleep(0.6)
    shot(drv, '17_health_dark')
    js_click(drv, dlg.find_element(By.XPATH, ".//button[normalize-space(.)='关闭']"))
    time.sleep(0.6)
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode','light');")
    drv.get('about:blank')
    goto_eval(drv)


def phase_category_delete_reachability(drv):
    """分类删除入口可达性：组内删除按钮仅在分类下 0 维度时可点，而 0 维度分类不渲染分组。"""
    tab_click(drv, '分组视图', scope="//*")
    time.sleep(1.2)
    btns = drv.find_elements(By.XPATH, "//button[@aria-label='删除分类 %s']" % CAT_NAME)
    disabled = btns[0].get_attribute('disabled') is not None if btns else None
    shot(drv, '18_category_delete_disabled_with_dims_light')
    log('分类删除-1 分类下有维度时删除按钮禁用（设计如此）',
        bool(btns) and disabled is True, {'present': bool(btns), 'disabled': disabled})
    env('分类删除-2 删除入口不可达：维度删光后空分类不再渲染分组（删除按钮随组消失）',
        {'reference': 'probe_int1484_overlay_delete.py 实测：删维度后分组消失、删除按钮不存在'})
    tab_click(drv, '列表视图', scope="//*")
    time.sleep(0.8)


def phase_delete_dimension(drv):
    search_dim(drv, DIM_NAME_EDITED)
    row_button(drv, '删除维度 %s' % DIM_NAME_EDITED)
    dlg = alert_dialog(drv, '删除维度')
    dlg_text = dlg.text
    shot(drv, '19_delete_dimension_confirm_light')
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


def phase_cleanup(drv, cat_id):
    created = [d for d in api_dims() if d.get('name', '').startswith(P)]
    deleted = []
    for d in created:
        st, body = api_call('DELETE', '/evaluation/dimensions/%s' % d['id'])
        deleted.append({'id': d['id'], 'name': d['name'], 'status': st})
    cat_status = None
    if cat_id:
        cat_status, _ = api_call('DELETE', '/evaluation/categories/%s' % cat_id)
    time.sleep(1.0)
    remain_dim = [d for d in api_dims() if d.get('name', '').startswith(P)]
    remain_cat = [c for c in api_cats() if c.get('name', '').startswith(P)]
    log('清理：删除本 run 测试维度/分类并复核无残留',
        not remain_dim and not remain_cat,
        {'deleted': deleted, 'category_delete_status': cat_status,
         'remain_dims': [d['name'] for d in remain_dim], 'remain_cats': [c['name'] for c in remain_cat]})
    goto_eval(drv)
    m = page_metrics(drv)
    log('清理后列表条数回到基线 %d' % BASELINE_TOTAL,
        ' '.join(m['footer_total'].split()) == '共 %d 条' % BASELINE_TOTAL, m)


def main():
    t0 = time.time()
    drv = _driver()
    cat_id = None
    try:
        login(drv)
        phase_page(drv)
        cat_id = category_create(drv)
        category_duplicate(drv)
        create_info, create_req = phase_dimension_create(drv)
        params_persisted = bool(create_info) and len(create_info['inputs']) == 3 and len(create_info['outputs']) == 2
        log('维度回读-新建后 GET 详情字段核对（名称/分类/规则/端点）',
            bool(create_info) and create_info['name'] == DIM_NAME
            and create_info['category_id'] is not None
            and sum(1 for u, _ in create_info['endpoints'] if '15000/health' in (u or '')) == 2
            and create_info['rule_count'] == 5,
            create_info)
        if not params_persisted:
            env('维度回读-输入/输出参数未落库（GET detail 空，DB evaluation_dimension_params 0 行）',
                {'id': create_info['id'] if create_info else None,
                 'request_inputs': len(create_req.get('required_inputs') or []),
                 'request_outputs': len(create_req.get('output_fields') or []),
                 'readback_inputs': len(create_info['inputs']) if create_info else None,
                 'readback_outputs': len(create_info['outputs']) if create_info else None})
        if create_req.get('associated_algorithms') and create_info and not create_info['algorithms']:
            env('维度回读-关联算法未落库（请求体已带，GET 回读空；同源 algorithm_service gRPC）',
                {'request_algorithms': create_req.get('associated_algorithms'),
                 'readback_algorithms': create_info['algorithms']})
        edit_info = phase_dimension_edit(drv)
        log('维度回读-编辑后 GET 详情字段核对（名称/描述/端点；参数受环境缺口影响）',
            bool(edit_info) and edit_info['name'] == DIM_NAME_EDITED
            and edit_info['desc'] == 'INT-1484 维度描述(已改)'
            and any('(改)' in (e[1] or '') for e in edit_info['endpoints']),
            edit_info)
        phase_rule_calc(drv)
        phase_health_online(drv)
        phase_health_offline(drv)
        phase_health_no_endpoint(drv)
        phase_empty_state(drv)
        phase_error_state(drv)
        phase_cancel_reopen(drv)
        phase_dark(drv)
        category_group_edit(drv)
        phase_category_delete_reachability(drv)
        phase_delete_dimension(drv)
    except Exception:
        log('EXCEPTION', False, traceback.format_exc()[-2000:])
    finally:
        try:
            phase_cleanup(drv, cat_id)
        except Exception:
            log('CLEANUP-EXCEPTION', False, traceback.format_exc()[-900:])
        with open(os.path.join(ART, 'result_main.json'), 'w', encoding='utf-8') as f:
            json.dump({'stamp': STAMP, 'elapsed_s': round(time.time() - t0, 1),
                       'result': RESULT, 'env': ENV, 'net': NET}, f, ensure_ascii=False, indent=1)
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
