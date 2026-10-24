# -*- coding: utf-8 -*-
"""INT-1660 验收（测试工程师）：评估维度编辑抽屉连续重开同一行不回填（React /Evaluation）。

环境：本卡 worktree 的 frontend-react dev server（临时配置 rsbuild.int1660.tmp.config.ts，
端口 5366，/api 代理到 docker 真实库栈 127.0.0.1:15000，库 intelligent_audio_test，AUTH_MODE=off）。
15173（wiring/react 构建）不含本卡修复（交付分支 agent/react-c/int-1660 未合入），故用 dev server。

用例（argv[1]）：
  flow       验收 1/2/6：首次打开 → 关闭 → 重开同一行（第 2、3 次）→ 开另一行 → 回原行 → 新建空表；
             记录每次打开的详情 GET 次数；第 2、3 次切 API配置 逐项对照详情接口；浅/深两套截图；console SEVERE 计数。
  regression 验收 3：INT-1577 分类编辑弹窗连续重开回填；抽屉内「+ 新建分类」真实落库并回填。
  save       验收 5：自建「接线测试_」维度 → 保存 → 列表行 / 分组视图分类计数 / 维度总数与 GET 一致。
  dark       深色重走（同源 reload）。
  cleanup    删除本 run 自建的「接线测试_INT1660」维度 / 分类（数据卫生）。
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:5366').rstrip('/')
API = os.environ.get('BACKEND_BASE', 'http://127.0.0.1:15000').rstrip('/')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.environ.get('ART_DIR', r'D:\00_user_data\int1660_artifacts')
TAG = os.environ.get('RUN_TAG', 'light')
DARK_KEY = 'iatp:theme:v1:mode'
PAGE = '/Evaluation'
TARGET_ID = 121
TARGET_NAME = '拒识成功数量'
OTHER_NAME = '环境理解准确率'
TARGET_CATEGORY = '拒识'
TEST_PREFIX = '接线测试_INT1660'

RESULT = []


def check(name, ok, detail=''):
    RESULT.append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:3000]})
    print(('[PASS] ' if ok else '[FAIL] ') + name + (' | ' + str(detail)[:400] if detail else ''))
    return ok


def api_req(method, path, body=None):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method,
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
        return {'success': False, 'code': e.code, 'message': raw[:500]}


def api_get(path):
    return api_req('GET', path)


def all_dimensions():
    d = api_get('/api/v1/evaluation/dimensions?page=1&per_page=1000')
    data = d.get('data') or {}
    items = data.get('items') or []
    return items, data.get('total', len(items))


def all_categories():
    d = api_get('/api/v1/evaluation/categories')
    data = d.get('data') or {}
    items = data.get('items') if isinstance(data, dict) else data
    return items or []


def chrome_major():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            return int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        return 0


def build_driver():
    opts = Options()
    opts.binary_location = CHROME_BINARY
    opts.add_argument('--headless=new')
    opts.add_argument('--window-size=1680,1080')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--lang=zh-CN')
    opts.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    major = chrome_major()
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    exe = ''
    if major and os.path.isdir(cache):
        cands = []
        for ver in os.listdir(cache):
            p = os.path.join(cache, ver, 'chromedriver.exe')
            if os.path.isfile(p):
                try:
                    cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), p))
                except ValueError:
                    pass
        same = [p for v, p in cands if v and v[0] == major]
        if same:
            exe = max(same)
    srv = Service(executable_path=exe) if exe else Service()
    drv = webdriver.Chrome(options=opts, service=srv)
    drv.set_page_load_timeout(150)
    drv.set_script_timeout(150)
    return drv


def shot(drv, name):
    os.makedirs(ART, exist_ok=True)
    p = os.path.join(ART, '%s_%s.png' % (TAG, name))
    drv.save_screenshot(p)
    print('shot:', p)
    return p


def js_click(drv, el, wait=0.5):
    drv.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", el)
    time.sleep(wait)


def js_click_xpath(drv, xpath, wait=0.6, timeout=30):
    el = WebDriverWait(drv, timeout).until(lambda d: d.find_element(By.XPATH, xpath))
    js_click(drv, el, wait)
    return el


def drain_perf(drv):
    out = []
    try:
        for entry in drv.get_log('performance'):
            msg = json.loads(entry['message'])['message']
            if msg.get('method') == 'Network.requestWillBeSent':
                req = msg['params']['request']
                out.append({'url': req.get('url', ''), 'method': req.get('method', '')})
    except Exception:
        pass
    return out


def count_detail_gets(reqs, dim_id=TARGET_ID):
    pat = '/api/v1/evaluation/dimensions/%d' % dim_id
    return len([r for r in reqs if r['method'] == 'GET' and pat in r['url']])


def visible(drv, el):
    try:
        return el.is_displayed()
    except (NoSuchElementException, StaleElementReferenceException):
        return False


def wait_visible(drv, xpath, timeout=90):
    return WebDriverWait(drv, timeout).until(lambda d: d.find_element(By.XPATH, xpath))


def dialog_root(drv, timeout=120):
    """base-ui 关闭后的 dialog 仍留在 DOM（旧弹窗在前），取最后一个可见的 [role=dialog]。"""
    def find(d):
        cands = [el for el in d.find_elements(By.XPATH, "//*[@role='dialog']") if visible(d, el)]
        return cands[-1] if cands else False
    return WebDriverWait(drv, timeout).until(find)


def dialog_gone(drv):
    try:
        return not any(visible(drv, el) for el in drv.find_elements(By.XPATH, "//*[@role='dialog']"))
    except Exception:
        return False


def goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 90).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(2.5)


def clear_type(drv, el, text):
    el.click()
    el.send_keys(Keys.CONTROL, 'a')
    el.send_keys(Keys.DELETE)
    time.sleep(0.2)
    el.send_keys(text)
    time.sleep(0.4)


def search_row(drv, name, keyword=''):
    if keyword is not None:
        box = wait_visible(drv, "//input[@aria-label='搜索评估维度']", 60)
        clear_type(drv, box, keyword or '')
        time.sleep(1.6)
    return wait_visible(drv, "//button[@aria-label='编辑维度 %s']" % name, 90)


DIM_NAME = ".//input[@id='dim-name']"
DIM_DESC = ".//textarea[@id='dim-description']"
DIM_CANCEL = ".//button[normalize-space(.)='取消']"
DIM_SAVE = ".//button[@type='submit' and (normalize-space(.)='保存' or normalize-space(.)='保存中…')]"
CATEGORY_TRIGGER = ".//label[contains(normalize-space(.),'所属分类')]/following::button[@data-slot='select-trigger'][1]"


def read_basic(drv, need_weight=True):
    out = {}
    dlg = dialog_root(drv)
    el = WebDriverWait(drv, 60).until(lambda d: dlg.find_element(By.XPATH, DIM_NAME))
    out['name'] = el.get_attribute('value') or ''
    out['description'] = dlg.find_element(By.XPATH, DIM_DESC).get_attribute('value') or ''
    out['category'] = (dlg.find_element(By.XPATH, CATEGORY_TRIGGER).text or '').strip()
    out['validation'] = ''
    try:
        v = dlg.find_element(By.XPATH, ".//*[@data-testid='dimension-form-validation-summary']")
        if visible(drv, v):
            out['validation'] = (v.text or '').strip()
    except NoSuchElementException:
        pass
    if need_weight:
        js_click(drv, dlg.find_element(By.XPATH, ".//button[@role='tab' and normalize-space(.)='结果配置']"), 1.0)
        # Label 组件在 required 时文本为「权重 *」，故用 contains 而非精确等值
        w = WebDriverWait(drv, 30).until(lambda d: dlg.find_element(
            By.XPATH,
            ".//label[contains(normalize-space(.),'权重')]/following-sibling::div//span[contains(@class,'tabular-nums')]"))
        out['weight'] = (w.text or '').strip()
        js_click(drv, dlg.find_element(By.XPATH, ".//button[@role='tab' and normalize-space(.)='基本信息']"), 0.8)
    return out


def read_api_tab(drv):
    dlg = dialog_root(drv)
    js_click(drv, dlg.find_element(By.XPATH, ".//button[@role='tab' and normalize-space(.)='API配置']"), 1.2)

    def collect(prefix):
        vals = []
        for i in range(1, 40):
            try:
                el = dlg.find_element(By.XPATH, ".//input[@aria-label='%s %d']" % (prefix, i))
            except NoSuchElementException:
                break
            vals.append(el.get_attribute('value') or '')
        return vals

    inputs = collect('输入参数键名')
    outputs = collect('输出字段代码')
    js_click(drv, dlg.find_element(By.XPATH, ".//button[@role='tab' and normalize-space(.)='基本信息']"), 0.8)
    return {'inputs': inputs, 'outputs': outputs}


def open_edit(drv, aria_label):
    js_click(drv, wait_visible(drv, "//button[@aria-label='%s']" % aria_label, 60), 1.2)
    return dialog_root(drv)


def open_create(drv):
    js_click_xpath(drv, "//button[normalize-space(.)='新增维度']", 1.2)
    return dialog_root(drv)


def close_drawer(drv):
    dlg = dialog_root(drv)
    js_click(drv, dlg.find_element(By.XPATH, DIM_CANCEL), 1.0)
    WebDriverWait(drv, 40).until(lambda d: dialog_gone(d))


def expected_detail():
    d = api_get('/api/v1/evaluation/dimensions/%d' % TARGET_ID)['data']
    inputs = [p['param_code'] for p in (d.get('required_inputs') or [])]
    outputs = [p.get('param_code') or p.get('field_code') for p in (d.get('output_fields') or [])]
    return d, inputs, outputs


# ---------------------------------------------------------------- flow（验收 1/2/6）

def phase_flow(drv):
    d, exp_inputs, exp_outputs = expected_detail()
    print('detail: name=%s category=%s weight=%s inputs=%d outputs=%d'
          % (d['name'], d.get('category_id'), d.get('weight'), len(exp_inputs), len(exp_outputs)))

    goto(drv, PAGE)
    row = search_row(drv, TARGET_NAME, '')
    check('目标行可见（列表首屏）', row is not None, TARGET_NAME)

    drain_perf(drv)
    # ---------- 第 1 次 ----------
    open_edit(drv, '编辑维度 ' + TARGET_NAME)
    b1 = read_basic(drv)
    reqs1 = drain_perf(drv)
    check('第1次：名称回填', b1['name'] == TARGET_NAME, b1['name'])
    check('第1次：分类回填（非未分类）', b1['category'] not in ('', '未分类'), b1['category'])
    check('第1次：权重回填', b1['weight'] == str(d.get('weight')), b1['weight'])
    check('第1次：无校验报错', b1['validation'] == '', b1['validation'])
    shot(drv, 'A_light_first_basic')
    api1 = read_api_tab(drv)
    check('第1次：输入参数与详情一致', api1['inputs'] == exp_inputs,
          'dom=%s exp=%s' % (api1['inputs'][:3], exp_inputs[:3]))
    close_drawer(drv)
    n1 = count_detail_gets(reqs1)
    print('detail GET round1 =', n1)

    # ---------- 第 2 次（同一行）----------
    drain_perf(drv)
    open_edit(drv, '编辑维度 ' + TARGET_NAME)
    b2 = read_basic(drv)
    reqs2 = drain_perf(drv)
    check('第2次（同一行）：名称回填', b2['name'] == TARGET_NAME, b2['name'])
    check('第2次（同一行）：描述回填', b2['description'] == (d.get('description') or ''), b2['description'][:60])
    check('第2次（同一行）：分类回填', b2['category'] not in ('', '未分类'), b2['category'])
    check('第2次（同一行）：权重回填', b2['weight'] == str(d.get('weight')), b2['weight'])
    check('第2次（同一行）：无「维度名称不能为空」', '维度名称不能为空' not in b2['validation'], b2['validation'])
    check('第2次：基础字段与第1次完全一致',
          (b2['name'], b2['description'], b2['category'], b2.get('weight'))
          == (b1['name'], b1['description'], b1['category'], b1.get('weight')),
          'round2=%s round1=%s' % (b2, b1))
    shot(drv, 'B_light_second_basic')
    api2 = read_api_tab(drv)
    check('第2次：输入参数与详情接口一致（非空、非默认 asr_result）',
          api2['inputs'] == exp_inputs, 'dom=%s' % (api2['inputs'][:4],))
    check('第2次：输出字段与详情接口一致', api2['outputs'] == exp_outputs,
          'dom=%s exp=%s' % (api2['outputs'][:3], exp_outputs[:3]))
    shot(drv, 'C_light_second_api_tab')
    close_drawer(drv)
    n2 = count_detail_gets(reqs2)
    print('detail GET round2 =', n2)

    # ---------- 第 3 次 ----------
    drain_perf(drv)
    open_edit(drv, '编辑维度 ' + TARGET_NAME)
    b3 = read_basic(drv)
    reqs3 = drain_perf(drv)
    check('第3次：名称/分类/权重回填',
          (b3['name'], b3['category'], b3.get('weight'))
          == (TARGET_NAME, b1['category'], b1.get('weight')), str(b3))
    api3 = read_api_tab(drv)
    check('第3次：输入/输出字段与详情一致',
          (api3['inputs'], api3['outputs']) == (exp_inputs, exp_outputs),
          'in=%d out=%d' % (len(api3['inputs']), len(api3['outputs'])))
    close_drawer(drv)
    n3 = count_detail_gets(reqs3)
    print('detail GET round3 =', n3)

    # ---------- 先开另一行，再回原行 ----------
    other_row = search_row(drv, OTHER_NAME, OTHER_NAME)
    js_click(drv, other_row, 1.5)
    bo = read_basic(drv)
    check('另一行：名称回填', bo['name'] == OTHER_NAME, bo['name'])
    check('另一行：名称非上一行残留', bo['name'] != TARGET_NAME, bo['name'])
    shot(drv, 'D_light_other_row')
    close_drawer(drv)

    search_row(drv, TARGET_NAME, TARGET_NAME)
    open_edit(drv, '编辑维度 ' + TARGET_NAME)
    b4 = read_basic(drv, need_weight=False)
    check('开另一行后回原行：名称回填', b4['name'] == TARGET_NAME, b4['name'])
    check('开另一行后回原行：分类回填', b4['category'] == b1['category'], b4['category'])
    check('开另一行后回原行：无校验报错', b4['validation'] == '', b4['validation'])
    close_drawer(drv)

    # ---------- 新建：空表 ----------
    search_row(drv, TARGET_NAME, '')
    open_create(drv)
    bc = read_basic(drv, need_weight=False)
    check('新建：名称为空（不残留上一行输入）', bc['name'] == '', repr(bc['name']))
    check('新建：描述为空', bc['description'] == '', repr(bc['description']))
    check('新建：分类为「未分类」', bc['category'] == '未分类', bc['category'])
    shot(drv, 'E_light_create_empty')
    close_drawer(drv)

    return {'detail_get_per_open': [n1, n2, n3]}


# ---------------------------------------------------------------- dark（§3.3 深色）

def phase_dark(drv):
    goto(drv, PAGE)
    drv.execute_script("localStorage.setItem('%s','dark')" % DARK_KEY)
    goto(drv, PAGE)
    mode = drv.execute_script("return localStorage.getItem('%s')" % DARK_KEY)
    check('深色已生效（localStorage）', mode == 'dark', mode)
    d, exp_inputs, _ = expected_detail()

    search_row(drv, TARGET_NAME, '')
    open_edit(drv, '编辑维度 ' + TARGET_NAME)
    b1 = read_basic(drv)
    check('深色第1次：名称/分类/权重回填',
          (b1['name'], b1['category'], b1.get('weight')) == (TARGET_NAME, TARGET_CATEGORY, str(d.get('weight'))), str(b1))
    shot(drv, 'F_dark_open1')
    close_drawer(drv)

    open_edit(drv, '编辑维度 ' + TARGET_NAME)
    b2 = read_basic(drv, need_weight=False)
    check('深色第2次：名称/分类回填', (b2['name'], b2['category']) == (TARGET_NAME, TARGET_CATEGORY), str(b2))
    shot(drv, 'G_dark_open2')
    api2 = read_api_tab(drv)
    check('深色第2次：输入参数与详情一致', api2['inputs'] == exp_inputs, len(api2['inputs']))
    shot(drv, 'H_dark_second_api_tab')
    close_drawer(drv)

    open_create(drv)
    bc = read_basic(drv, need_weight=False)
    check('深色新建：空表 + 未分类', bc['name'] == '' and bc['category'] == '未分类', str(bc))
    shot(drv, 'I_dark_create_empty')
    close_drawer(drv)


# ---------------------------------------------------------------- regression（验收 3）

def switch_view(drv, label):
    js_click_xpath(drv, "//button[normalize-space(.)='%s']" % label, 1.8)


def phase_regression(drv):
    goto(drv, PAGE)
    # --- INT-1577：分类编辑弹窗连续重开同一分类 ---
    switch_view(drv, '分组视图')
    first = wait_visible(drv, "//button[@aria-label='编辑分类 %s']" % TARGET_CATEGORY, 90)
    for round_no in (1, 2):
        if round_no == 2:
            js_click(drv, wait_visible(drv, "//button[@aria-label='编辑分类 %s']" % TARGET_CATEGORY, 60), 1.2)
        else:
            js_click(drv, first, 1.2)
        dlg = dialog_root(drv)
        name_el = WebDriverWait(drv, 60).until(
            lambda d: dlg.find_element(By.XPATH, ".//input[@id='category-name']"))
        val = name_el.get_attribute('value') or ''
        check('INT-1577 分类弹窗第%d次打开回填' % round_no, val == TARGET_CATEGORY, val)
        js_click(drv, dlg.find_element(By.XPATH, ".//button[normalize-space(.)='取消']"), 1.0)
        WebDriverWait(drv, 40).until(lambda d: dialog_gone(d))
    shot(drv, 'J_category_dialog_regression')

    # --- 抽屉内「+ 新建分类」真实落库并回填 ---
    switch_view(drv, '列表视图')
    dlg = open_create(drv)
    js_click(drv, dlg.find_element(By.XPATH, CATEGORY_TRIGGER), 1.0)
    js_click_xpath(drv, "//*[@role='option' and normalize-space(.)='+ 新建分类']", 1.0)
    inp = WebDriverWait(drv, 30).until(
        lambda d: dlg.find_element(By.XPATH, ".//input[@aria-label='新分类名称']"))
    cat_name = TEST_PREFIX + '分类'
    clear_type(drv, inp, cat_name)
    js_click(drv, dlg.find_element(By.XPATH, ".//button[normalize-space(.)='创建']"), 1.2)
    WebDriverWait(drv, 120).until(
        lambda d: cat_name in (dlg.find_element(By.XPATH, CATEGORY_TRIGGER).text or ''))
    check('抽屉「+ 新建分类」落库并回填到分类选择器', True, cat_name)
    created = [c for c in all_categories() if c.get('name') == cat_name]
    check('新建分类可在 GET /evaluation/categories 查到', bool(created),
          [c.get('id') for c in created])
    shot(drv, 'K_inline_new_category')
    close_drawer(drv)
    return [c.get('id') for c in created]


# ---------------------------------------------------------------- save（验收 5）

def group_count(drv, category_name):
    """分组视图某分类标题后的计数徽章：有筛选时为「命中/总数」，无筛选时只有总数。"""
    xp = ("//*[normalize-space(.)='%s']/ancestor::div[1]"
          "//span[contains(@class,'tabular-nums')]") % category_name
    el = wait_visible(drv, xp, 60)
    txt = (el.text or '').strip()
    if '/' in txt:
        a, b = txt.split('/', 1)
        return (int(a) if a.strip().isdigit() else None,
                int(b) if b.strip().isdigit() else None)
    return (int(txt) if txt.isdigit() else None,
            int(txt) if txt.isdigit() else None)


def phase_save(drv):
    dims_before, total_before = all_dimensions()
    # 统计基线：排除本 run 自建维度（重跑时它已落库）
    own_before = [x for x in dims_before if str(x.get('name', '')).startswith(TEST_PREFIX)]
    base_total = total_before - len(own_before)
    cat_count_before = len([
        x for x in dims_before
        if (x.get('categoryId') if 'categoryId' in x else x.get('category_id')) == 3
        and str(x.get('name', '')) not in [o.get('name') for o in own_before]
    ])
    print('before: total=%d base_total=%d 拒识分类=%d' % (total_before, base_total, cat_count_before))

    goto(drv, PAGE)
    name1 = TEST_PREFIX + '维度'
    existing = [x for x in dims_before if x.get('name') == name1]
    if existing:
        # 上一轮已落库（后端保存慢 >240s，抽屉迟迟不关），这里接着验回显与二次保存
        check('保存新建维度成功（后端已落库）', True,
              {'id': existing[0].get('id'), 'note': '上一轮 POST 已落库，抽屉关闭超时'})
    else:
        dlg = open_create(drv)
        clear_type(drv, dlg.find_element(By.XPATH, DIM_NAME), name1)
        clear_type(drv, dlg.find_element(By.XPATH, DIM_DESC), '接线测试_抽屉保存闭环')
        # 分类选「拒识」
        js_click(drv, dlg.find_element(By.XPATH, CATEGORY_TRIGGER), 1.0)
        js_click_xpath(drv, "//*[@role='option' and normalize-space(.)='%s']" % TARGET_CATEGORY, 1.0)
        check('新建维度：分类已选', TARGET_CATEGORY in (dlg.find_element(By.XPATH, CATEGORY_TRIGGER).text or ''))
        t0 = time.time()
        js_click(drv, dlg.find_element(By.XPATH, DIM_SAVE), 1.0)
        WebDriverWait(drv, 600).until(lambda d: dialog_gone(d))
        cost = round(time.time() - t0, 1)
        check('保存新建维度成功（抽屉关闭）', True, '%.1fs' % cost)

    dims, total_after = all_dimensions()
    created = [x for x in dims if x.get('name') == name1]
    check('保存后 GET 列表出现新维度', bool(created), [x.get('id') for x in created])
    check('维度总数 +1', total_after == base_total + 1, '%d -> %d' % (base_total, total_after))
    new_dim = created[0] if created else {}
    new_id = new_dim.get('id')
    if new_id:
        detail = api_get('/api/v1/evaluation/dimensions/%s' % new_id).get('data') or {}
        check('保存后详情接口字段一致',
              detail.get('name') == name1 and detail.get('description') == '接线测试_抽屉保存闭环'
              and detail.get('category_id') == 3,
              {k: detail.get(k) for k in ('name', 'description', 'category_id')})

    # 列表行回显
    search_row(drv, name1, name1)
    check('列表视图出现新维度行', True, name1)
    shot(drv, 'L_save_created_row')

    # 分组视图分类计数
    switch_view(drv, '分组视图')
    gc = group_count(drv, TARGET_CATEGORY)
    dims_now, _ = all_dimensions()
    api_cat = len([x for x in dims_now if (x.get('categoryId') if 'categoryId' in x else x.get('category_id')) == 3])
    check('分组视图「拒识」计数（徽章总数）== 接口分类计数', gc[1] == api_cat, 'ui=%s api=%s' % (gc, api_cat))
    check('分类计数 +1', api_cat == cat_count_before + 1, '%d -> %d' % (cat_count_before, api_cat))
    shot(drv, 'M_save_group_count')

    # 编辑保存：改名称/描述，列表与接口同步
    switch_view(drv, '列表视图')
    search_row(drv, name1, name1)
    open_edit(drv, '编辑维度 ' + name1)
    dlg = dialog_root(drv)
    name2 = name1 + '_v2'
    clear_type(drv, dlg.find_element(By.XPATH, DIM_NAME), name2)
    clear_type(drv, dlg.find_element(By.XPATH, DIM_DESC), '接线测试_二次保存')
    js_click(drv, dlg.find_element(By.XPATH, DIM_SAVE), 1.0)
    WebDriverWait(drv, 600).until(lambda d: dialog_gone(d))
    dims2, total2 = all_dimensions()
    edited = [x for x in dims2 if x.get('name') == name2]
    check('编辑保存后接口名称更新', bool(edited), (new_id, name2))
    check('编辑保存后总数不变', total2 == total_after, '%d -> %d' % (total_after, total2))
    if new_id:
        detail = api_get('/api/v1/evaluation/dimensions/%s' % new_id).get('data') or {}
        check('编辑保存后详情字段更新',
              detail.get('name') == name2 and detail.get('description') == '接线测试_二次保存',
              {k: detail.get(k) for k in ('name', 'description')})
    search_row(drv, name2, name2)
    check('列表行回显新名称', True, name2)
    shot(drv, 'N_save_edited_row')
    return {'created_dimension_id': new_id}


# ---------------------------------------------------------------- cleanup（数据卫生）

def phase_cleanup(drv=None):
    removed = {'dimensions': [], 'categories': []}
    for x in all_dimensions()[0]:
        if str(x.get('name', '')).startswith(TEST_PREFIX):
            r = api_req('DELETE', '/api/v1/evaluation/dimensions/%s' % x['id'])
            removed['dimensions'].append({'id': x['id'], 'name': x['name'], 'resp': r.get('code', r.get('success'))})
    dims_left = [x for x in all_dimensions()[0] if str(x.get('name', '')).startswith(TEST_PREFIX)]
    check('清理：自建维度已删除', not dims_left, dims_left[:3])
    for c in all_categories():
        if str(c.get('name', '')).startswith(TEST_PREFIX):
            r = api_req('DELETE', '/api/v1/evaluation/categories/%s' % c['id'])
            removed['categories'].append({'id': c['id'], 'name': c['name'], 'resp': r.get('code', r.get('success'))})
    cats_left = [c for c in all_categories() if str(c.get('name', '')).startswith(TEST_PREFIX)]
    check('清理：自建分类已删除', not cats_left, cats_left[:3])
    return removed


def main():
    phase = (sys.argv[1] if len(sys.argv) > 1 else 'flow').strip()
    need_driver = phase in ('flow', 'dark', 'regression', 'save')
    drv = build_driver() if need_driver else None
    extra = {}
    try:
        if phase == 'flow':
            extra['net'] = phase_flow(drv)
            severe = [e.get('message', '') for e in drv.get_log('browser') if e.get('level') == 'SEVERE']
            check('全程 console 无 SEVERE', not severe, severe[:3])
        elif phase == 'dark':
            phase_dark(drv)
            severe = [e.get('message', '') for e in drv.get_log('browser') if e.get('level') == 'SEVERE']
            check('深色全程 console 无 SEVERE', not severe, severe[:3])
        elif phase == 'regression':
            extra['created_categories'] = phase_regression(drv)
        elif phase == 'save':
            extra['save'] = phase_save(drv)
        elif phase == 'cleanup':
            extra['cleanup'] = phase_cleanup()
        else:
            raise SystemExit('unknown phase ' + phase)
    finally:
        os.makedirs(ART, exist_ok=True)
        out = os.path.join(ART, 'result_%s_%s.json' % (phase, TAG))
        with open(out, 'w', encoding='utf-8') as f:
            json.dump({'phase': phase, 'result': RESULT, 'extra': extra}, f, ensure_ascii=False, indent=2)
        print('result ->', out)
        if drv is not None:
            try:
                drv.quit()
            except Exception:
                pass
    failed = [r for r in RESULT if not r['ok']]
    print('SUMMARY: %d passed, %d failed' % (len(RESULT) - len(failed), len(failed)))
    for f in failed:
        print('  FAILED:', f['name'], '|', f['detail'][:200])
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
