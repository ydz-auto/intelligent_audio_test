# -*- coding: utf-8 -*-
"""INT-1484 前端UX审计独立复跑（共享 15173，镜像 916bc83ed4d9 / wiring-react 2c35bf65d）。

审计口径：不是复述实施者的结论，而是自己在真实库栈上重走评估域 4 个模态窗 +
INT-1732 修复段（P2 主路径 + P3 三项），并留浅/深截图与请求/响应。
分阶段运行（--phase），避免单条命令超过 10 分钟：
  env   环境三次核对之一 + 首页/列表基线
  cat   分类弹窗：新建 → 重名 → 编辑 → 删除
  dim   维度抽屉：空规则夹具（反填/保存/回读）+ 输入输出参数增删改 + 删除闭环
  rules 有规则夹具：加一条/删一条保存回读 + 规则试算 + 健康测试（在线/离线/无端点）
  p3    筛选无匹配空态 + 新建维度端点为空 + 深色列表
"""
import argparse
import copy
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import winreg

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE = 'http://127.0.0.1:15173'
API = 'http://127.0.0.1:15000/api/v1'
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
PREFIX = '接线测试_INT1484AUD_'
STAMP = time.strftime('%H%M%S')
ART = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1484_audit')
USER = '接线测试_admin'
PASSWORD = 'JieXianTest@2026'

REPORT = {'stamp': STAMP, 'steps': [], 'requests': [], 'console': []}


def log(msg):
    line = '[%s] %s' % (time.strftime('%H:%M:%S'), msg)
    print(line, flush=True)
    REPORT['steps'].append(line)


# ------------------------------------------------------------------ http --
def http(url, method='GET', payload=None, timeout=240, attempts=3):
    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    last = None
    for i in range(attempts):
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header('content-type', 'application/json')
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
                raw = resp.read()
                return resp.status, json.loads(raw.decode('utf-8') or '{}')
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                body = json.loads(raw.decode('utf-8') or '{}')
            except Exception:  # noqa: BLE001
                body = {'_raw': raw[:400].decode('utf-8', 'replace')}
            if exc.code < 500:
                return exc.code, body
            last = RuntimeError('HTTP %s %r' % (exc.code, body))
        except Exception as exc:  # noqa: BLE001
            last = exc
        time.sleep(2 + 2 * i)
    raise last if last else RuntimeError('request failed')


def get_json(path):
    st, body = http(API + path)
    assert st == 200, (path, st, body)
    return body.get('data')


def dim_total():
    return get_json('/evaluation/dimensions?page=1&per_page=1').get('total')


def get_dim(dim_id):
    return get_json('/evaluation/dimensions/%s' % dim_id)


def create_dim(name, rule, result_type, n_inputs=1, n_outputs=1, endpoints=None):
    real = copy.deepcopy(get_dim(121))
    for key in ('id', 'created_at', 'updated_at', 'created_by_user_id'):
        real.pop(key, None)
    for key in ('required_inputs', 'output_fields'):
        rows = real.get(key) or []
        keep = n_inputs if key == 'required_inputs' else n_outputs
        real[key] = [
            {k: v for k, v in row.items() if k not in ('id', 'dimension_id')}
            for row in rows[:keep]
        ]
    real['name'] = name
    real['rule'] = rule
    real['result_type'] = result_type
    real['api_endpoints'] = endpoints if endpoints is not None else []
    real['api_url'] = ''
    real['associated_algorithms'] = []
    t0 = time.time()
    st, body = http(API + '/evaluation/dimensions', method='POST', payload=real)
    dt = time.time() - t0
    assert st in (200, 201), 'create failed %s %r' % (st, body)
    dim_id = body['data']['id']
    log('POST /evaluation/dimensions → %s %.2fs id=%s rule=%s rt=%s'
        % (st, dt, dim_id, json.dumps(rule, ensure_ascii=False), result_type))
    return dim_id, dt


def delete_dim(dim_id):
    t0 = time.time()
    try:
        st, body = http(API + '/evaluation/dimensions/%s' % dim_id, method='DELETE')
    except Exception as exc:  # noqa: BLE001
        return repr(exc), time.time() - t0
    return st, time.time() - t0


# -------------------------------------------------------------- selenium --
def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
    chrome_major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:  # noqa: BLE001
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    drv_path = ''
    if chrome_major and os.path.isdir(cache_root):
        cands = []
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
                except ValueError:
                    continue
        same = [exe for ver, exe in cands if ver and ver[0] == chrome_major]
        if same:
            drv_path = max(same)
    service = Service(executable_path=drv_path) if drv_path else Service()
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(120)
    return drv


def wait_for(fn, timeout=45, desc='condition', interval=0.3):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        try:
            value = fn()
            if value:
                return value
        except Exception as exc:  # noqa: BLE001
            last = exc
        time.sleep(interval)
    raise AssertionError('timeout: %s (last=%r)' % (desc, last))


def shot(drv, name):
    os.makedirs(ART, exist_ok=True)
    path = os.path.join(ART, name)
    drv.save_screenshot(path)
    log('shot %s' % name)
    return path


def set_theme(drv, mode):
    drv.execute_script(
        "localStorage.setItem('iatp:theme:v1:mode', arguments[0]);"
        "document.documentElement.classList.toggle('dark', arguments[0]==='dark');",
        mode,
    )
    time.sleep(0.6)


def visible(el):
    try:
        return el.is_displayed()
    except Exception:  # noqa: BLE001
        return False


def drain_perf(drv):
    try:
        drv.get_log('performance')
    except Exception:  # noqa: BLE001
        pass


def collect_perf(drv):
    out = []
    try:
        for entry in drv.get_log('performance'):
            try:
                msg = json.loads(entry.get('message', '') or '')
                m = msg.get('message') or {}
                method = m.get('method') or ''
                params = m.get('params') or {}
            except Exception:  # noqa: BLE001
                continue
            if method == 'Network.requestWillBeSent':
                req = params.get('request') or {}
                out.append({'method': req.get('method'), 'url': req.get('url'),
                            'postData': req.get('postData') or '', 'status': None})
            elif method == 'Network.responseReceived':
                resp = params.get('response') or {}
                url = resp.get('url') or ''
                for item in reversed(out):
                    if item['url'] == url and item['status'] is None:
                        item['status'] = resp.get('status')
                        break
    except Exception:  # noqa: BLE001
        pass
    return out


def dump_console(drv):
    try:
        entries = drv.get_log('browser')
    except Exception:  # noqa: BLE001
        return []
    severe = [e for e in entries if (e.get('level') or '').upper() == 'SEVERE']
    REPORT['console'].extend(severe)
    return severe


def login_and_open(drv):
    drv.get(BASE + '/Evaluation')
    time.sleep(2)
    if drv.find_elements(By.XPATH, "//input[@placeholder='请输入用户名或邮箱']"):
        log('需要登录 → %s' % USER)
        drv.find_element(By.XPATH, "//input[@placeholder='请输入用户名或邮箱']").send_keys(USER)
        drv.find_element(By.XPATH, "//input[@placeholder='请输入密码']").send_keys(PASSWORD)
        try:
            btn = drv.find_element(By.XPATH, "//button[@type='submit']")
        except Exception:  # noqa: BLE001
            btn = drv.find_element(By.XPATH, "//button[contains(normalize-space(.),'登录')]")
        drv.execute_script('arguments[0].click()', btn)
        time.sleep(3)
        if '/login' in drv.current_url:
            drv.get(BASE + '/Evaluation')
    if '/Evaluation' not in drv.current_url:
        drv.get(BASE + '/Evaluation')
    wait_for(lambda: drv.find_elements(By.CSS_SELECTOR, 'input[placeholder="搜索评估维度..."]'),
             timeout=90, desc='/Evaluation 搜索框')
    time.sleep(1.5)
    log('已进入 /Evaluation，url=%s' % drv.current_url)


def search(drv, kw):
    box = wait_for(lambda: drv.find_elements(By.CSS_SELECTOR, 'input[placeholder="搜索评估维度..."]'),
                   desc='搜索框')[0]
    box.click()
    box.send_keys(Keys.CONTROL, 'a')
    box.send_keys(Keys.DELETE)
    if kw:
        box.send_keys(kw)
    time.sleep(1.0)


def reload_eval(drv):
    drv.get(BASE + '/Evaluation')
    wait_for(lambda: drv.find_elements(By.CSS_SELECTOR, 'input[placeholder="搜索评估维度..."]'),
             timeout=90, desc='/Evaluation 重载')
    time.sleep(1.5)


def sheet(drv):
    els = [e for e in drv.find_elements(By.CSS_SELECTOR, '[data-slot="sheet-content"]') if visible(e)]
    return els[-1] if els else None


def dialog(drv):
    els = [e for e in drv.find_elements(
        By.XPATH, "//*[@role='dialog' or @role='alertdialog']") if visible(e)]
    return els[-1] if els else None


def dialog_text(drv):
    d = dialog(drv) or sheet(drv)
    return d.text if d else ''


def open_edit(drv, name):
    btn = wait_for(lambda: drv.find_elements(By.XPATH, "//button[@aria-label='编辑维度 %s']" % name),
                   timeout=45, desc='编辑维度按钮')
    drv.execute_script('arguments[0].click()', btn[0])
    wait_for(lambda: sheet(drv) is not None, desc='维度抽屉')
    wait_for(lambda: drv.find_elements(By.ID, 'dim-name'), desc='抽屉渲染')
    time.sleep(0.6)


def open_tab(drv, label):
    tab = wait_for(lambda: drv.find_elements(
        By.XPATH, "//button[@role='tab'][contains(normalize-space(.),'%s')]" % label), desc='tab %s' % label)
    drv.execute_script('arguments[0].click()', tab[0])
    time.sleep(0.8)


def save(drv, timeout=240):
    btn = drv.find_element(By.XPATH, "//button[@type='submit' and @form='dimension-mutate-form']")
    assert btn.get_attribute('disabled') is None, '保存按钮被禁用'
    t0 = time.time()
    drv.execute_script('arguments[0].click()', btn)
    wait_for(lambda: sheet(drv) is None, timeout=timeout, desc='抽屉关闭（保存完成）')
    dt = time.time() - t0
    time.sleep(1.2)
    log('保存完成 %.2fs' % dt)
    return dt


def close_sheet(drv):
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    wait_for(lambda: sheet(drv) is None, timeout=20, desc='Esc 关闭抽屉')


def rule_rows(drv):
    return len(drv.find_elements(By.CSS_SELECTOR, 'input[aria-label$="阈值"]'))


def last_request(reqs, method, frag):
    hits = [r for r in reqs if r['method'] == method and frag in r['url']]
    return hits[-1] if hits else None


def dimension_count_label(drv):
    rows = [r for r in drv.find_elements(By.XPATH, "//tbody/tr") if visible(r)]
    return len(rows)


# ---------------------------------------------------------------- phases --
def confirm_yes(drv):
    d = wait_for(lambda: dialog(drv), desc='确认弹窗')
    time.sleep(0.5)
    btns = [b for b in d.find_elements(By.TAG_NAME, 'button') if visible(b)]
    target = [b for b in btns if b.text.strip() in ('删除', '确定', '继续')]
    assert target, '确认按钮未找到: %s' % [b.text for b in btns]
    label = target[-1].text.strip()
    drv.execute_script('arguments[0].click()', target[-1])
    return label


def phase_dd(drv):
    """下拉选项条数 vs 接口：分类 facet / 状态 facet / 关联算法 facet / 抽屉分类 Select / 算法勾选。"""
    cats = get_json('/evaluation/categories')['items']
    _, alg = http(API + '/algorithm/options')
    algs = (alg.get('data') or {}).get('algorithms') or []
    log('接口：categories=%d %s；algorithm/options=%d %s' % (
        len(cats), [c['name'] for c in cats], len(algs),
        [a.get('name') for a in algs]))

    def facet(title, expect):
        trig = wait_for(lambda: [b for b in drv.find_elements(By.TAG_NAME, 'button')
                                 if visible(b) and b.text.strip().startswith(title)], desc='facet %s' % title)
        drv.execute_script('arguments[0].click()', trig[0])
        time.sleep(0.6)
        pop = [p for p in drv.find_elements(By.CSS_SELECTOR, '[data-slot="popover-content"]') if visible(p)]
        assert pop, 'facet %s 未弹出' % title
        labels = [ln.strip() for ln in pop[-1].text.split('\n') if ln.strip()]
        log('facet「%s」弹出项=%s（含全部项）' % (title, labels))
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(0.4)
        return labels

    f_cat = facet('分类', len(cats))
    f_status = facet('状态', 3)
    f_alg = facet('关联算法', len(algs))
    # 弹出层文本首行是标题，其后是「全部」+ 选项
    assert len(f_cat) == len(cats) + 2, f_cat
    assert len(f_status) == 4, f_status
    assert len(f_alg) == len(algs) + 2, f_alg

    # 抽屉：所属分类 Select + 关联算法勾选 + 结果类型
    add = wait_for(lambda: drv.find_elements(
        By.XPATH, "//button[contains(normalize-space(.),'新增维度')]"), desc='新增维度')[0]
    drv.execute_script('arguments[0].click()', add)
    wait_for(lambda: drv.find_elements(By.ID, 'dim-name'), desc='新建抽屉')
    open_tab(drv, '关联算法')
    checks = [c for c in drv.find_elements(By.CSS_SELECTOR, '[aria-label^="关联算法 "]') if visible(c)]
    log('关联算法勾选项=%s' % [c.get_attribute('aria-label') for c in checks])
    assert len(checks) == len(algs), len(checks)
    open_tab(drv, '结果配置')
    labels = [b.text.strip() for b in drv.find_elements(By.CSS_SELECTOR, 'button[role="combobox"]') if visible(b)]
    log('结果配置 combobox 文案=%s' % labels)
    open_tab(drv, '基本信息')
    triggers = [b for b in drv.find_elements(By.CSS_SELECTOR, 'button[role="combobox"]') if visible(b)]
    log('抽屉 combobox 数=%d' % len(triggers))
    cat_trigger = None
    for b in triggers:
        if '全部' in b.text or '分类' in b.text or b.text.strip() in [c['name'] for c in cats]:
            cat_trigger = b
    assert cat_trigger is not None, [b.text for b in triggers]
    drv.execute_script('arguments[0].click()', cat_trigger)
    time.sleep(0.6)
    opts = [o for o in drv.find_elements(By.CSS_SELECTOR, '[role="option"]') if visible(o)]
    texts = [o.text.strip() for o in opts]
    log('抽屉「所属分类」选项=%s' % texts)
    assert len(opts) == len(cats) + 2, texts  # 未分类 + 「+ 新建分类」
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(0.4)
    log('下拉口径核对完成 ✅')


def phase_env(drv):
    st, health = http('http://127.0.0.1:15000/health')
    log('health %s %s' % (st, json.dumps(health, ensure_ascii=False)))
    total = dim_total()
    log('维度 total=%s' % total)
    try:
        out = subprocess.run(
            ['docker', 'inspect', 'iat-react-frontend:latest', '--format',
             '{{.Id}} {{.Created}}'], capture_output=True, text=True, timeout=60)
        log('镜像 %s' % (out.stdout.strip() or out.stderr.strip()))
    except Exception as exc:  # noqa: BLE001
        log('docker inspect 失败 %r' % exc)
    lib = subprocess.run(
        ['powershell', '-NoProfile', '-Command',
         "(Invoke-WebRequest -UseBasicParsing http://127.0.0.1:15173/).Content"],
        capture_output=True, text=True, timeout=60)
    import re
    m = re.search(r'lib-react[^"\']*', lib.stdout)
    log('前端 lib-react=%s' % (m.group(0) if m else 'NOT-FOUND'))
    chunk = subprocess.run(
        ['powershell', '-NoProfile', '-Command',
         "(Invoke-WebRequest -UseBasicParsing http://127.0.0.1:15173/static/js/async/so.d1f02df358.js).Content"],
        capture_output=True, text=True, timeout=60)
    body = chunk.stdout
    log('bundle so.d1f02df358.js len=%s 命中未配置提示=%s 暂无评估维度数据=%s 未设置=%s api.example=%s'
        % (len(body), '该维度未配置评分规则' in body, '暂无评估维度数据' in body,
           '"未设置"' in body or "'未设置'" in body or '未设置' in body,
           'api.example.com' in body))
    set_theme(drv, 'light')
    shot(drv, '00_list_light.png')
    set_theme(drv, 'dark')
    shot(drv, '01_list_dark.png')
    set_theme(drv, 'light')
    log('列表可见行数=%s' % dimension_count_label(drv))
    return total


def phase_cat(drv):
    cat = PREFIX + 'cat_' + STAMP
    before = get_json('/evaluation/categories')['items']
    log('分类 before=%d' % len(before))

    # 新建
    add = wait_for(lambda: drv.find_elements(
        By.XPATH, "//button[contains(normalize-space(.),'新增分类')]"), desc='新增分类按钮')[0]
    drain_perf(drv)
    drv.execute_script('arguments[0].click()', add)
    wait_for(lambda: dialog(drv) is not None, desc='分类弹窗')
    wait_for(lambda: drv.find_elements(By.ID, 'category-name'), desc='分类表单')
    log('分类弹窗标题=%s' % dialog_text(drv).split('\n')[0])
    drv.find_element(By.ID, 'category-name').send_keys(cat)
    drv.find_element(By.ID, 'category-description').send_keys('审计自建分类')
    icon_el = drv.find_element(By.ID, 'category-icon')
    log('新建分类图标默认值=%r' % icon_el.get_attribute('value'))
    icon_el.send_keys(Keys.CONTROL, 'a')
    icon_el.send_keys(Keys.DELETE)
    icon_el.send_keys('fas fa-folder')
    shot(drv, '02_category_create_light.png')
    submit = drv.find_element(By.XPATH, "//button[@type='submit' and @form='category-form']")
    drv.execute_script('arguments[0].click()', submit)
    wait_for(lambda: dialog(drv) is None, timeout=40, desc='分类弹窗关闭')
    time.sleep(1.5)
    reqs = collect_perf(drv)
    post = last_request(reqs, 'POST', '/evaluation/categories')
    REPORT['requests'].append(post)
    log('分类 POST status=%s body=%s' % (post['status'] if post else None, post['postData'][:300] if post else None))
    after = get_json('/evaluation/categories')['items']
    mine = [c for c in after if c['name'] == cat]
    assert mine, 'GET 分类未回读到新建分类'
    log('分类回读 id=%s name=%s desc=%s' % (mine[0]['id'], mine[0]['name'], mine[0].get('description')))

    # 重名
    add = wait_for(lambda: drv.find_elements(
        By.XPATH, "//button[contains(normalize-space(.),'新增分类')]"), desc='新增分类按钮')[0]
    drv.execute_script('arguments[0].click()', add)
    wait_for(lambda: drv.find_elements(By.ID, 'category-name'), desc='分类表单2')
    drv.find_element(By.ID, 'category-name').send_keys('话轮接管')
    drv.find_element(By.XPATH, "//button[@type='submit' and @form='category-form']").click()
    wait_for(lambda: '已存在' in dialog_text(drv), timeout=40, desc='重名错误就地提示')
    log('重名提示=%s' % [ln for ln in dialog_text(drv).split('\n') if '存在' in ln])
    shot(drv, '03_category_duplicate_light.png')
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    wait_for(lambda: dialog(drv) is None, timeout=20, desc='取消重名弹窗')

    # 编辑（分组视图）
    tab = wait_for(lambda: drv.find_elements(
        By.XPATH, "//button[@role='tab'][contains(normalize-space(.),'分组视图')]"), desc='分组视图 tab')
    drv.execute_script('arguments[0].click()', tab[0])
    time.sleep(1.5)
    eb = wait_for(lambda: drv.find_elements(By.XPATH, "//button[@aria-label='编辑分类 %s']" % cat),
                  timeout=40, desc='编辑分类按钮')
    drain_perf(drv)
    drv.execute_script('arguments[0].click()', eb[0])
    wait_for(lambda: drv.find_elements(By.ID, 'category-name'), desc='编辑分类表单')
    log('编辑弹窗标题=%s 回填name=%s desc=%s' % (
        dialog_text(drv).split('\n')[0],
        drv.find_element(By.ID, 'category-name').get_attribute('value'),
        drv.find_element(By.ID, 'category-description').get_attribute('value')))
    desc_el = drv.find_element(By.ID, 'category-description')
    desc_el.click()
    desc_el.send_keys(Keys.CONTROL, 'a')
    desc_el.send_keys(Keys.DELETE)
    desc_el.send_keys('审计改名后描述')
    drv.find_element(By.XPATH, "//button[@type='submit' and @form='category-form']").click()
    wait_for(lambda: dialog(drv) is None, timeout=40, desc='编辑弹窗关闭')
    time.sleep(1.2)
    reqs = collect_perf(drv)
    put = last_request(reqs, 'PUT', '/evaluation/categories')
    REPORT['requests'].append(put)
    log('分类 PUT status=%s body=%s' % (put['status'] if put else None, put['postData'][:300] if put else None))
    got = [c for c in get_json('/evaluation/categories')['items'] if c['name'] == cat][0]
    assert got.get('description') == '审计改名后描述', got
    log('分类 PUT 回读 desc=%s' % got.get('description'))

    # 删除（空分类分组视图）
    db = wait_for(lambda: drv.find_elements(By.XPATH, "//button[@aria-label='删除分类 %s']" % cat),
                  timeout=40, desc='删除分类按钮')
    drain_perf(drv)
    drv.execute_script('arguments[0].click()', db[0])
    wait_for(lambda: dialog(drv) is not None, desc='删除确认弹窗')
    log('删除确认=%s' % dialog_text(drv).replace('\n', ' | ')[:160])
    shot(drv, '04_category_delete_confirm_light.png')
    log('确认按钮=%s' % confirm_yes(drv))
    wait_for(lambda: dialog(drv) is None, timeout=40, desc='删除弹窗关闭')
    time.sleep(1.5)
    reqs = collect_perf(drv)
    dele = last_request(reqs, 'DELETE', '/evaluation/categories')
    REPORT['requests'].append(dele)
    log('分类 DELETE status=%s url=%s' % (dele['status'] if dele else None, dele['url'] if dele else None))
    names = [c['name'] for c in get_json('/evaluation/categories')['items']]
    assert cat not in names, '分类删除后仍在列表'
    log('分类删除回读消失 ✅（分类数 %d）' % len(names))


def phase_dim(drv, total_before):
    name_a = PREFIX + 'emptyrules_' + STAMP
    endpoints = [{'url': '', 'name': '', 'priority': 1, 'maxProcess': 5,
                  'maxTimeout': 30, 'maxAudioDuration': 60}]
    id_a, _ = create_dim(name_a, {'rules': [], 'defaultScore': 7}, 0,
                         n_inputs=2, n_outputs=1, endpoints=endpoints)
    d0 = get_dim(id_a)
    assert d0['rule'] == {'rules': [], 'defaultScore': 7}, d0['rule']
    log('夹具A 回读 rule=%s rt=%s inputs=%d outputs=%d' % (
        json.dumps(d0['rule'], ensure_ascii=False), d0['result_type'],
        len(d0.get('required_inputs') or []), len(d0.get('output_fields') or [])))

    reload_eval(drv)
    search(drv, name_a)
    open_edit(drv, name_a)
    open_tab(drv, '结果配置')
    rows = rule_rows(drv)
    txt = sheet(drv).text
    log('抽屉：规则行=%d 未配置提示=%s 未设置=%s 请选择结果类型=%s 保存可用=%s'
        % (rows, '该维度未配置评分规则' in txt, '未设置' in txt, '请选择结果类型' in txt,
           drv.find_element(By.XPATH, "//button[@type='submit' and @form='dimension-mutate-form']").get_attribute('disabled') is None))
    assert rows == 0, '空规则维度冒出规则行 %d' % rows
    assert '该维度未配置评分规则' in txt
    assert '未设置' in txt and '请选择结果类型' not in txt
    set_theme(drv, 'light')
    shot(drv, '10_dim_emptyrules_result_light.png')
    set_theme(drv, 'dark')
    shot(drv, '11_dim_emptyrules_result_dark.png')
    set_theme(drv, 'light')

    # 不改字段保存
    drain_perf(drv)
    save(drv)
    reqs = collect_perf(drv)
    put = last_request(reqs, 'PUT', '/evaluation/dimensions/%s' % id_a)
    body = json.loads(put['postData'] or '{}')
    REPORT['requests'].append(put)
    log('PUT(%s) status=%s rule=%s result_type=%s inputs=%d outputs=%d' % (
        id_a, put['status'], json.dumps(body.get('rule'), ensure_ascii=False), body.get('result_type'),
        len(body.get('required_inputs') or []), len(body.get('output_fields') or [])))
    assert body['rule'] == {'rules': [], 'defaultScore': 7}, body['rule']
    assert body.get('result_type') == 0
    d1 = get_dim(id_a)
    assert d1['rule'] == {'rules': [], 'defaultScore': 7}, d1['rule']
    log('回读 rule=%s rt=%s（原样保存未改配置）✅' % (json.dumps(d1['rule'], ensure_ascii=False), d1['result_type']))

    # 输入/输出参数增删改：改输入标签1、删输入2、加输出2
    reload_eval(drv)
    search(drv, name_a)
    open_edit(drv, name_a)
    open_tab(drv, 'API配置')
    label1 = wait_for(lambda: drv.find_elements(By.CSS_SELECTOR, 'input[aria-label="输入显示标签 1"]'),
                      desc='输入显示标签 1')
    old_label = label1[0].get_attribute('value')
    label1[0].click()
    label1[0].send_keys(Keys.CONTROL, 'a')
    label1[0].send_keys(Keys.DELETE)
    label1[0].send_keys('审计输入标签X')
    # 删第 2 条输入
    dels = drv.find_elements(By.CSS_SELECTOR, 'button[aria-label="删除输入 2"]')
    if dels:
        drv.execute_script('arguments[0].click()', dels[0])
    # 加输出
    add_out = wait_for(lambda: drv.find_elements(
        By.XPATH, "//button[contains(normalize-space(.),'添加字段')]"), desc='添加字段')
    drv.execute_script('arguments[0].click()', add_out[0])
    time.sleep(0.5)
    outs = drv.find_elements(By.CSS_SELECTOR, 'input[aria-label="输出字段代码 2"]')
    if outs:
        outs[0].send_keys('audit_out')
        dn = drv.find_elements(By.CSS_SELECTOR, 'input[aria-label="输出显示名 2"]')
        if dn:
            dn[0].send_keys('审计输出')
        pth = drv.find_elements(By.CSS_SELECTOR, 'input[aria-label="输出提取路径 2"]')
        if pth:
            pth[0].send_keys('data.audit_out')
    shot(drv, '12_dim_api_tab_light.png')
    drain_perf(drv)
    save(drv)
    reqs = collect_perf(drv)
    put2 = last_request(reqs, 'PUT', '/evaluation/dimensions/%s' % id_a)
    body2 = json.loads(put2['postData'] or '{}')
    REPORT['requests'].append(put2)
    d2 = get_dim(id_a)
    ins = d2.get('required_inputs') or []
    outs2 = d2.get('output_fields') or []
    log('参数保存 PUT status=%s rule=%s 回读 inputs=%d(首个param_name=%s) outputs=%d(%s)'
        % (put2['status'], json.dumps(body2.get('rule'), ensure_ascii=False), len(ins),
           ins[0].get('param_name') if ins else None, len(outs2),
           [o.get('param_code') for o in outs2]))
    assert len(ins) == 1, '删除输入未生效 %d' % len(ins)
    assert ins[0].get('param_name') == '审计输入标签X', ins[0].get('param_name')
    assert len(outs2) == 2 and any(o.get('param_code') == 'audit_out' for o in outs2), outs2
    assert d2['rule'] == {'rules': [], 'defaultScore': 7}, d2['rule']
    log('输入改/删 + 输出增 均回读生效，rule 仍保留 ✅')

    # 删除闭环（UI）
    reload_eval(drv)
    search(drv, name_a)
    db = wait_for(lambda: drv.find_elements(By.XPATH, "//button[@aria-label='删除维度 %s']" % name_a),
                  timeout=45, desc='删除维度按钮')
    drain_perf(drv)
    drv.execute_script('arguments[0].click()', db[0])
    wait_for(lambda: dialog(drv) is not None, desc='删除维度确认弹窗')
    log('删除维度确认=%s' % dialog_text(drv).replace('\n', ' | ')[:160])
    log('确认按钮=%s' % confirm_yes(drv))
    wait_for(lambda: dialog(drv) is None, timeout=40, desc='删除维度弹窗关闭')
    time.sleep(1.2)
    reqs = collect_perf(drv)
    dele = last_request(reqs, 'DELETE', '/evaluation/dimensions/%s' % id_a)
    REPORT['requests'].append(dele)
    log('DELETE 维度 status=%s' % (dele['status'] if dele else None))
    st, body = http(API + '/evaluation/dimensions/%s' % id_a)
    log('删除后 GET 详情 → HTTP %s envelope code=%s message=%s' % (st, body.get('code'), body.get('message')))
    assert body.get('success') is False and body.get('code') == 404, body
    assert not any(i['id'] == id_a for i in
                   get_json('/evaluation/dimensions?page=1&per_page=100')['items']), '删除后仍在列表'
    log('删除闭环：详情 404 信封 + 列表消失 ✅')
    log('维度 total 回到 %s（开工 %s）' % (dim_total(), total_before))


def phase_rules(drv, total_before):
    name_b = PREFIX + 'rules_' + STAMP
    rule_b = {'rules': [{'condition': '>=', 'value': 95, 'score': 10},
                        {'condition': '<', 'value': 95, 'score': 0}],
              'defaultScore': 3}
    endpoints = [
        {'url': 'http://host.docker.internal:15000/health', 'name': 'int1484aud',
         'priority': 1, 'maxProcess': 1, 'maxTimeout': 10, 'maxAudioDuration': 60},
        {'url': 'http://127.0.0.1:1/int1484aud', 'name': 'dead',
         'priority': 2, 'maxProcess': 1, 'maxTimeout': 5, 'maxAudioDuration': 60},
    ]
    id_b, _ = create_dim(name_b, rule_b, 1, n_inputs=1, n_outputs=1, endpoints=endpoints)
    d0 = get_dim(id_b)
    log('夹具B 回读 rule=%s rt=%s endpoints=%s' % (
        json.dumps(d0['rule'], ensure_ascii=False), d0['result_type'],
        [e.get('url') for e in d0.get('api_endpoints') or []]))

    reload_eval(drv)
    search(drv, name_b)
    open_edit(drv, name_b)
    open_tab(drv, '结果配置')
    log('夹具B 抽屉规则行=%d 保存可用=%s' % (
        rule_rows(drv),
        drv.find_element(By.XPATH, "//button[@type='submit' and @form='dimension-mutate-form']").get_attribute('disabled') is None))
    assert rule_rows(drv) == 2

    # 加一条
    add_rule = wait_for(lambda: drv.find_elements(
        By.XPATH, "//button[contains(normalize-space(.),'添加规则')]"), desc='添加规则')
    drv.execute_script('arguments[0].click()', add_rule[0])
    time.sleep(0.4)
    thr = drv.find_elements(By.CSS_SELECTOR, 'input[aria-label="规则 3 阈值"]')
    thr[0].send_keys('99')
    sc = drv.find_elements(By.CSS_SELECTOR, 'input[aria-label="规则 3 得分"]')
    sc[0].send_keys('20')
    set_theme(drv, 'light')
    shot(drv, '20_dim_rules_light.png')
    set_theme(drv, 'dark')
    shot(drv, '21_dim_rules_dark.png')
    set_theme(drv, 'light')
    drain_perf(drv)
    save(drv)
    reqs = collect_perf(drv)
    put = last_request(reqs, 'PUT', '/evaluation/dimensions/%s' % id_b)
    REPORT['requests'].append(put)
    d1 = get_dim(id_b)
    rules1 = (d1.get('rule') or {}).get('rules') or []
    log('加规则 PUT status=%s 载荷rule=%s 回读 %d 条 defaultScore=%s' % (
        put['status'], json.dumps(json.loads(put['postData'] or '{}').get('rule'), ensure_ascii=False),
        len(rules1), (d1.get('rule') or {}).get('defaultScore')))
    assert len(rules1) == 3 and (d1.get('rule') or {}).get('defaultScore') == 3

    # 删一条
    reload_eval(drv)
    search(drv, name_b)
    open_edit(drv, name_b)
    open_tab(drv, '结果配置')
    assert rule_rows(drv) == 3
    db = wait_for(lambda: drv.find_elements(By.CSS_SELECTOR, 'button[aria-label="删除规则 3"]'),
                  desc='删除规则 3')
    drv.execute_script('arguments[0].click()', db[0])
    time.sleep(0.4)
    drain_perf(drv)
    save(drv)
    reqs = collect_perf(drv)
    put2 = last_request(reqs, 'PUT', '/evaluation/dimensions/%s' % id_b)
    REPORT['requests'].append(put2)
    d2 = get_dim(id_b)
    rules2 = (d2.get('rule') or {}).get('rules') or []
    log('删规则 PUT status=%s 回读 %d 条 defaultScore=%s' % (
        put2['status'], len(rules2), (d2.get('rule') or {}).get('defaultScore')))
    assert len(rules2) == 2 and (d2.get('rule') or {}).get('defaultScore') == 3

    # 规则试算
    reload_eval(drv)
    search(drv, name_b)
    calc_btn = wait_for(lambda: drv.find_elements(By.XPATH, "//button[@aria-label='规则试算维度 %s']" % name_b),
                        timeout=45, desc='规则试算按钮')
    drain_perf(drv)
    drv.execute_script('arguments[0].click()', calc_btn[0])
    wait_for(lambda: dialog(drv) is not None, desc='试算弹窗')
    wait_for(lambda: drv.find_elements(By.ID, 'calc-value'), desc='试算输入框')
    drv.find_element(By.ID, 'calc-value').send_keys('97')
    drv.find_element(By.XPATH, "//button[contains(normalize-space(.),'试算')]").click()
    wait_for(lambda: '评分' in dialog_text(drv), timeout=40, desc='试算结果')
    log('试算 97 → %s' % dialog_text(drv).replace('\n', ' | ')[:180])
    shot(drv, '22_rule_calc_light.png')
    reqs = collect_perf(drv)
    post = last_request(reqs, 'POST', '/calculate')
    REPORT['requests'].append(post)
    log('试算 POST status=%s body=%s' % (post['status'] if post else None, post['postData'] if post else None))
    assert '评分 10 分' in dialog_text(drv), dialog_text(drv)
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    wait_for(lambda: dialog(drv) is None, timeout=20, desc='关闭试算')

    # 健康测试（在线 + 离线混合）
    hb = wait_for(lambda: drv.find_elements(By.XPATH, "//button[@aria-label='测试维度 %s 的 API']" % name_b),
                  timeout=45, desc='测试API按钮')
    drain_perf(drv)
    drv.execute_script('arguments[0].click()', hb[0])
    wait_for(lambda: dialog(drv) is not None, desc='健康弹窗')
    wait_for(lambda: '总状态' in dialog_text(drv), timeout=90, desc='健康结果')
    txt = dialog_text(drv)
    log('健康测试 → %s' % txt.replace('\n', ' | ')[:400])
    shot(drv, '23_health_mixed_light.png')
    reqs = collect_perf(drv)
    hp = last_request(reqs, 'GET', '/health')
    REPORT['requests'].append(hp)
    log('健康 GET status=%s url=%s' % (hp['status'] if hp else None, hp['url'] if hp else None))
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    wait_for(lambda: dialog(drv) is None, timeout=20, desc='关闭健康')

    # 无端点：真实维度 121
    reload_eval(drv)
    search(drv, '拒识成功数量')
    hb = wait_for(lambda: drv.find_elements(By.XPATH, "//button[@aria-label='测试维度 拒识成功数量 的 API']"),
                  timeout=45, desc='121 测试API')
    drv.execute_script('arguments[0].click()', hb[0])
    wait_for(lambda: dialog(drv) is not None, desc='121 健康弹窗')
    time.sleep(3)
    txt = dialog_text(drv)
    log('121 无端点健康 → %s' % txt.replace('\n', ' | ')[:300])
    shot(drv, '24_health_noendpoint_light.png')
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)

    # 真实维度 121 原样保存（P2 复现路径）
    reload_eval(drv)
    search(drv, '拒识成功数量')
    before = get_dim(121)
    log('121 before rule=%s rt=%s' % (json.dumps(before['rule'], ensure_ascii=False), before['result_type']))
    open_edit(drv, '拒识成功数量')
    open_tab(drv, '结果配置')
    log('121 抽屉规则行=%d 未配置提示=%s 未设置=%s' % (
        rule_rows(drv), '该维度未配置评分规则' in sheet(drv).text, '未设置' in sheet(drv).text))
    drain_perf(drv)
    save(drv)
    reqs = collect_perf(drv)
    put = last_request(reqs, 'PUT', '/evaluation/dimensions/121')
    REPORT['requests'].append(put)
    after = get_dim(121)
    log('121 PUT status=%s 载荷rule=%s；after rule=%s rt=%s name=%s' % (
        put['status'], json.dumps(json.loads(put['postData'] or '{}').get('rule'), ensure_ascii=False),
        json.dumps(after['rule'], ensure_ascii=False), after['result_type'], after['name']))
    assert after['rule'] == before['rule'], '真实维度 rule 被改'
    assert after['result_type'] == before['result_type']
    assert after['name'] == before['name']

    # 收尾删除夹具 B
    for did, label in ((id_b, 'B'),):
        st, dt = delete_dim(did)
        log('DELETE 夹具%s id=%s → %s %.2fs' % (label, did, st, dt))
    log('维度 total 回到 %s（开工 %s）' % (dim_total(), total_before))


def phase_newdef(drv):
    """新建维度默认值：规则条数 / 输出字段 / 端点（V9.7.10 对照；保存后回读）。"""
    name = PREFIX + 'newdef_' + STAMP
    add = wait_for(lambda: drv.find_elements(
        By.XPATH, "//button[contains(normalize-space(.),'新增维度')]"), desc='新增维度按钮')[0]
    drv.execute_script('arguments[0].click()', add)
    wait_for(lambda: drv.find_elements(By.ID, 'dim-name'), desc='新建抽屉')
    open_tab(drv, '结果配置')
    rows = rule_rows(drv)
    log('新建→结果配置 默认规则行=%d' % rows)
    set_theme(drv, 'light')
    shot(drv, '40_new_dim_result_default_light.png')
    set_theme(drv, 'dark')
    shot(drv, '41_new_dim_result_default_dark.png')
    set_theme(drv, 'light')
    open_tab(drv, 'API配置')
    out_codes = [e.get_attribute('value') for e in
                 drv.find_elements(By.CSS_SELECTOR, 'input[aria-label^="输出字段代码"]')]
    log('新建→API配置 默认输出字段代码=%s' % out_codes)
    open_tab(drv, '基本信息')
    nm = drv.find_element(By.ID, 'dim-name')
    nm.click()
    nm.send_keys(name)
    drain_perf(drv)
    try:
        save(drv, timeout=180)
    except Exception as exc:  # noqa: BLE001
        log('新建保存失败：%r' % exc)
        shot(drv, '42_new_dim_save_failed_light.png')
        raise
    reqs = collect_perf(drv)
    post = last_request(reqs, 'POST', '/evaluation/dimensions')
    body = json.loads(post['postData'] or '{}')
    REPORT['requests'].append(post)
    log('新建 POST status=%s rule=%s output_fields=%s endpoints=%s' % (
        post['status'], json.dumps(body.get('rule'), ensure_ascii=False),
        json.dumps(body.get('output_fields'), ensure_ascii=False)[:300],
        json.dumps(body.get('api_endpoints'), ensure_ascii=False)[:200]))
    items = get_json('/evaluation/dimensions?page=1&per_page=100')['items']
    mine = [i for i in items if i['name'] == name]
    if mine:
        did = mine[0]['id']
        got = get_dim(did)
        log('新建回读 id=%s rule条数=%d output_fields=%s' % (
            did, len((got.get('rule') or {}).get('rules') or []),
            [o.get('param_code') for o in got.get('output_fields') or []]))
        st, dt = delete_dim(did)
        log('清理新建维度 id=%s → %s %.2fs' % (did, st, dt))
    log('维度 total=%s' % dim_total())


def phase_p3(drv):
    # P3-2 筛选无匹配
    search(drv, 'zzz_int1484_audit_无匹配')
    txt = drv.find_element(By.TAG_NAME, 'body').text
    assert '暂无评估维度数据' in txt, '无匹配空态标题不符'
    assert '当前筛选条件下没有匹配的评估维度' in txt
    assert '创建第一个评估维度' not in txt, '无匹配仍引导创建第一个'
    log('P3-2 无匹配空态：文案正确、无创建引导 ✅')
    set_theme(drv, 'light')
    shot(drv, '30_filter_empty_light.png')
    set_theme(drv, 'dark')
    shot(drv, '31_filter_empty_dark.png')
    set_theme(drv, 'light')
    search(drv, '')

    # P3-3 新建维度端点为空
    add = wait_for(lambda: drv.find_elements(
        By.XPATH, "//button[contains(normalize-space(.),'新增维度')]"), desc='新增维度按钮')[0]
    drv.execute_script('arguments[0].click()', add)
    wait_for(lambda: sheet(drv) is not None, desc='新建维度抽屉')
    wait_for(lambda: drv.find_elements(By.ID, 'dim-name'), desc='新建表单')
    log('新建抽屉标题=%s' % sheet(drv).text.split('\n')[0])
    log('新建结果配置默认规则行=%d' % rule_rows(drv))
    open_tab(drv, 'API配置')
    urls = drv.find_elements(By.CSS_SELECTOR, 'input[aria-label="端点 URL 1"]')
    names = drv.find_elements(By.CSS_SELECTOR, 'input[aria-label="端点名称 1"]')
    val_url = urls[0].get_attribute('value') if urls else 'NO-INPUT'
    val_name = names[0].get_attribute('value') if names else 'NO-INPUT'
    log('P3-3 新建端点 URL=%r 名称=%r' % (val_url, val_name))
    assert val_url == '' and val_name == '', (val_url, val_name)
    shot(drv, '32_new_dim_api_light.png')
    set_theme(drv, 'dark')
    shot(drv, '33_new_dim_api_dark.png')
    set_theme(drv, 'light')
    close_sheet(drv)
    log('P3-3 端点初始为空 ✅')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--phase', required=True,
                    choices=('env', 'cat', 'dim', 'rules', 'p3', 'newdef', 'dd', 'all'))
    args = ap.parse_args()
    os.makedirs(ART, exist_ok=True)
    total_before = dim_total()
    drv = _driver()
    try:
        login_and_open(drv)
        if args.phase in ('env', 'all'):
            phase_env(drv)
        if args.phase in ('cat', 'all'):
            phase_cat(drv)
        if args.phase in ('dim', 'all'):
            phase_dim(drv, total_before)
        if args.phase in ('rules', 'all'):
            phase_rules(drv, total_before)
        if args.phase in ('p3', 'all'):
            phase_p3(drv)
        if args.phase in ('newdef', 'all'):
            phase_newdef(drv)
        if args.phase in ('dd', 'all'):
            phase_dd(drv)
        severe = dump_console(drv)
        log('控制台 SEVERE 条数=%d' % len(severe))
        REPORT['dim_total_before'] = total_before
        REPORT['dim_total_after'] = dim_total()
        with open(os.path.join(ART, 'report_%s.json' % args.phase), 'w', encoding='utf-8') as fh:
            json.dump(REPORT, fh, ensure_ascii=False, indent=1)
        log('DONE total %s → %s' % (total_before, REPORT['dim_total_after']))
    finally:
        try:
            drv.quit()
        except Exception:  # noqa: BLE001
            pass


if __name__ == '__main__':
    main()
