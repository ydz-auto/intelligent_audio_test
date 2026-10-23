# -*- coding: utf-8 -*-
"""INT-1487 标签域深走查（docker 15173 React + 15000 真实库栈）。
标签管理页：分类/标签 新建-编辑-删除-回读、必填/同名校验、取消重开残留、空态/错误态、
深浅色截图、联动刷新。只用「接线测试_INT1487」前缀数据，结束前清理。
"""
import json
import os
import re
import sys
import time
import urllib.request
import winreg

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from selenium import webdriver
from selenium.webdriver import ActionChains
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://localhost:15173')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1487_tags')
os.makedirs(ART, exist_ok=True)

P = '接线测试_INT1487'
CAT_A = P + '分类A'
CAT_B = P + '分类B'
TAG_A = P + '标签A'
TAG_A2 = P + '标签A改'
ERRORS = []
EVID = []


def log(*a):
    print(*a, flush=True)


def ev(label, value):
    EVID.append((label, value))
    log(f'[EV] {label}: {value}')


def step(name):
    log('\n' + '=' * 20, name)


def driver():
    o = Options()
    o.binary_location = CHROME
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1050')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--disable-dev-shm-usage')
    o.add_argument('--disable-extensions')
    o.add_argument('--no-proxy-server')
    o.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    path = ''
    if major and os.path.isdir(cache):
        cands = []
        for ver in os.listdir(cache):
            exe = os.path.join(cache, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
                except ValueError:
                    pass
        same = [e for v, e in cands if v and v[0] == major]
        if same:
            path = max(same)
    d = webdriver.Chrome(options=o, service=Service(path) if path else Service())
    d.set_page_load_timeout(90)
    return d


# ---------- 网络 ----------
def drain(d):
    d.get_log('performance')


def collect(d, needles=('/api/v1/tags', '/api/v1/testcases/batch')):
    out = []
    for e in d.get_log('performance'):
        try:
            msg = json.loads(e['message'])['message']
        except Exception:
            continue
        m = msg.get('method')
        p = msg.get('params', {})
        if m == 'Network.requestWillBeSent':
            req = p['request']
            if any(n in req['url'] for n in needles):
                out.append({'t': 'REQ', 'method': req['method'], 'url': req['url'],
                            'body': req.get('postData')})
        elif m == 'Network.responseReceived':
            r = p['response']
            if any(n in r['url'] for n in needles):
                out.append({'t': 'RESP', 'status': r['status'], 'url': r['url']})
    return out


def show_net(rows):
    for r in rows:
        if r['t'] == 'REQ':
            log(f"  NET {r['method']} {r['url']} body={r['body']}")
        else:
            log(f"  NET <- {r['status']} {r['url']}")
    return rows


# ---------- API 直查（页内 fetch，带 Bearer）----------
def api(d, method, path, body=None):
    script = """
    const [method, path, body] = arguments;
    const cb = arguments[arguments.length - 1];
    const token = localStorage.getItem('iatp:auth:token:v1');
    const opt = {method, headers: {'Accept': 'application/json'}, credentials: 'include'};
    if (token) opt.headers.Authorization = 'Bearer ' + token;
    if (body) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
    fetch('/api/v1' + path, opt).then(async r => {
      const t = await r.text();
      cb({status: r.status, body: t});
    }).catch(e => cb({status: -1, body: String(e)}));
    """
    d.set_script_timeout(40)
    res = d.execute_async_script(script, method, path, body)
    try:
        res['json'] = json.loads(res['body'])
    except Exception:
        res['json'] = None
    return res


def tag_list(d):
    r = api(d, 'GET', '/tags?page=1&per_page=100')
    return (r['json'] or {}).get('data', {}).get('items', [])


def cat_list(d):
    r = api(d, 'GET', '/tags/categories?page=1&per_page=100')
    return (r['json'] or {}).get('data', {}).get('items', [])


# ---------- UI helpers ----------
def js_click(d, el):
    d.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)
    time.sleep(0.3)


def dialogs(d):
    return d.find_elements(By.CSS_SELECTOR, '[role="dialog"],[role="alertdialog"]')


def wait_dialog(d, title, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        for el in dialogs(d):
            h2 = el.find_elements(By.CSS_SELECTOR, 'h2')
            if h2 and title in (h2[0].text or ''):
                return el
        time.sleep(0.3)
    raise AssertionError(f'弹窗未出现: {title}; 现有={[x.text[:30] for x in dialogs(d)]}')


def close_top_dialog(d):
    for el in reversed(dialogs(d)):
        for b in el.find_elements(By.TAG_NAME, 'button'):
            al = b.get_attribute('aria-label')
            if al and al.startswith('Close'):
                js_click(d, b)
                time.sleep(0.8)
                return True
    return False


def shot(d, name):
    p = os.path.join(ART, name + '.png')
    d.save_screenshot(p)
    log('  shot', p)
    return p


def theme(d, mode):
    d.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0])", mode)
    d.get('about:blank')
    d.get(BASE + '/TagManagement')
    time.sleep(8)


def goto_tags(d):
    d.get(BASE + '/TagManagement')
    WebDriverWait(d, 30).until(lambda x: len(x.find_elements(By.CSS_SELECTOR, 'tbody tr')) > 0
                               or len(x.find_elements(By.XPATH, "//*[contains(., '暂无标签')]")) > 0)
    time.sleep(1.5)


def open_tag_dialog(d, title='新建标签'):
    btn = d.find_elements(By.XPATH, f"//button[normalize-space(.)='{title}']")
    if not btn:
        btn = d.find_elements(By.XPATH, f"//button[normalize-space(.)='新建标签']")
    js_click(d, btn[0])
    return wait_dialog(d, title)


def submit_btn(dlg):
    for b in dlg.find_elements(By.TAG_NAME, 'button'):
        t = (b.text or '').strip()
        if t in ('创建', '保存', '保存中...'):
            return b
    raise AssertionError('无提交按钮')


def choose_category(d, dlg, name):
    trig = dlg.find_elements(By.CSS_SELECTOR, '[role="combobox"]')[0]
    js_click(d, trig)
    time.sleep(0.8)
    opts = d.find_elements(By.CSS_SELECTOR, '[role="option"]')
    texts = [(o.text or '').strip() for o in opts]
    log('  select options:', texts)
    for o in opts:
        if (o.text or '').strip() == name:
            js_click(d, o)
            time.sleep(0.8)
            return texts
    raise AssertionError(f'分类选项缺失 {name}; 现有 {texts}')


def palette(dlg, color, d):
    btns = dlg.find_elements(By.CSS_SELECTOR, f'button[aria-label="颜色 {color}"]')
    assert btns, f'色板缺 {color}'
    js_click(d, btns[0])
    time.sleep(0.3)


def input_value(d, el):
    return el.get_attribute('value')


def toast_text(d):
    return [t.text for t in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]


def delete_confirm(d, label_name):
    """点击行/树里的删除钮并返回确认弹窗"""
    btn = d.find_elements(By.CSS_SELECTOR, f'[aria-label="{label_name}"]')
    assert btn, f'删除钮缺失 {label_name}'
    js_click(d, btn[0])
    time.sleep(0.8)
    for el in dialogs(d):
        if '删除' in (el.text or ''):
            return el
    raise AssertionError('确认弹窗未出现')


def confirm_delete(d, dlg):
    for b in dlg.find_elements(By.TAG_NAME, 'button'):
        if (b.text or '').strip() == '删除':
            js_click(d, b)
            time.sleep(2.5)
            return True
    raise AssertionError('确认弹窗无删除钮')


def section(fn):
    try:
        fn()
    except Exception as e:
        import traceback
        traceback.print_exc()
        ERRORS.append(f'{fn.__name__}: {e}')
        log('  !! section error', fn.__name__, e)


# ================= 主流程 =================
d = driver()
try:
    step('S0 环境三次核对 #1')
    with urllib.request.urlopen('http://127.0.0.1:15000/health', timeout=10) as r:
        health = json.loads(r.read().decode())
    ev('health#1', json.dumps(health, ensure_ascii=False))
    assert health.get('database') == 'intelligent_audio_test', '非真实库，停'
    with urllib.request.urlopen(BASE + '/', timeout=10) as r:
        html = r.read().decode('utf-8', 'replace')
    m = re.search(r'lib-react[^"]*', html)
    ev('frontend bundle', m.group(0) if m else 'NOT FOUND')
    assert m, '前端不是 React 构建'

    step('S1 登录')
    d.get(BASE + '/login')
    time.sleep(2)
    d.find_element(By.ID, 'username').send_keys('接线测试_admin')
    d.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    for b in d.find_elements(By.TAG_NAME, 'button'):
        if '登' in b.text and '录' in b.text:
            js_click(d, b)
            break
    WebDriverWait(d, 30).until(lambda x: '/login' not in x.current_url)
    time.sleep(3)
    log('  logged in', d.current_url)

    # ---------- S2 初始态 ----------
    def s2():
        step('S2 /TagManagement 初始态 + 首次请求')
        drain(d)
        goto_tags(d)
        net = show_net(collect(d))
        ev('初次请求', [f"{n['method']} {n['url'].split('15173')[-1]}" for n in net if n['t'] == 'REQ'])
        cats = cat_list(d)
        tags = tag_list(d)
        ev('API 分类条数', len(cats))
        ev('API 标签条数', len(tags))
        body = d.find_element(By.TAG_NAME, 'body').text
        m1 = re.search(r'标签分类\s*共 (\d+) 个', body)
        m2 = re.search(r'共 (\d+) 个标签', body)
        ev('UI 分类计数', m1.group(1) if m1 else 'N/A')
        ev('UI 标签计数', m2.group(1) if m2 else 'N/A')
        ev('UI 标签行数(首屏)', len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')))
        ev('未分类计数 UI', re.search(r'未分类\s*(\d+)', body).group(1) if re.search(r'未分类\s*(\d+)', body) else 'N/A')
        shot(d, '01_page_light_initial')
    section(s2)

    # ---------- S3 分类新建 ----------
    def s3():
        step('S3 分类新建（含必填校验/默认值/请求响应）')
        drain(d)
        btn = d.find_elements(By.XPATH, "//button[normalize-space(.)='新建']")
        assert btn, '分类卡「新建」缺失'
        js_click(d, btn[0])
        dlg = wait_dialog(d, '新建分类')
        ev('分类弹窗标题', dlg.find_elements(By.CSS_SELECTOR, 'h2')[0].text)
        ev('分类弹窗描述', dlg.find_elements(By.CSS_SELECTOR, 'p')[0].text)
        name_i = dlg.find_element(By.ID, 'category-name')
        desc_i = dlg.find_element(By.ID, 'category-desc')
        sort_i = dlg.find_element(By.ID, 'category-sort')
        ev('分类默认排序', sort_i.get_attribute('value'))
        pressed = [b.get_attribute('aria-label') for b in dlg.find_elements(By.CSS_SELECTOR, 'button[aria-pressed="true"]')]
        ev('分类默认色(aria-pressed)', pressed)
        ev('空名称时创建钮 disabled', submit_btn(dlg).get_attribute('disabled'))
        shot(d, '02_category_dialog_light_empty')
        name_i.send_keys(CAT_A)
        desc_i.send_keys('INT-1487 测试分类A')
        sort_i.clear()
        sort_i.send_keys('3')
        palette(dlg, '#8b5cf6', d)
        shot(d, '03_category_dialog_light_filled')
        js_click(d, submit_btn(dlg))
        time.sleep(3)
        net = show_net(collect(d))
        post = [n for n in net if n['t'] == 'REQ' and n['method'] == 'POST']
        resp = [n for n in net if n['t'] == 'RESP' and 'categories' in n['url']]
        ev('POST /tags/categories body', post[0]['body'] if post else 'MISSING')
        ev('POST /tags/categories status', resp[0]['status'] if resp else 'MISSING')
        ev('toast', toast_text(d))
        time.sleep(1)
        cats = cat_list(d)
        ev('回读分类', json.dumps(cats, ensure_ascii=False))
        body = d.find_element(By.TAG_NAME, 'body').text
        ev('UI 分类计数(建后)', re.search(r'标签分类\s*共 (\d+) 个', body).group(1) if re.search(r'标签分类\s*共 (\d+) 个', body) else 'N/A')
        shot(d, '04_page_light_category_created')
    section(s3)

    # ---------- S3b 第二个分类 ----------
    def s3b():
        step('S3b 建第二个分类（分类归属迁移用）')
        drain(d)
        js_click(d, d.find_elements(By.XPATH, "//button[normalize-space(.)='新建']")[0])
        dlg = wait_dialog(d, '新建分类')
        dlg.find_element(By.ID, 'category-name').send_keys(CAT_B)
        ev('第二个分类默认排序', dlg.find_element(By.ID, 'category-sort').get_attribute('value'))
        js_click(d, submit_btn(dlg))
        time.sleep(3)
        net = show_net(collect(d))
        ev('第二个分类 POST 状态', [n['status'] for n in net if n['t'] == 'RESP' and 'categories' in n['url']])
        ev('回读分类(2)', json.dumps([(c['id'], c['name'], c.get('sort_order'), c.get('color'), c.get('tag_count')) for c in cat_list(d)], ensure_ascii=False))
    section(s3b)

    # ---------- S4 标签新建 ----------
    def s4():
        step('S4 标签新建：默认值 / 必填校验 / 分类选项条数 / 提交 / 回读')
        drain(d)
        dlg = open_tag_dialog(d)
        ev('标签弹窗标题', dlg.find_elements(By.CSS_SELECTOR, 'h2')[0].text)
        ev('标签弹窗描述', dlg.find_elements(By.CSS_SELECTOR, 'p')[0].text)
        name_i = dlg.find_element(By.ID, 'tag-name')
        ev('标签名称初值', repr(name_i.get_attribute('value')))
        ev('分类占位', dlg.find_elements(By.CSS_SELECTOR, '[role="combobox"]')[0].text)
        ev('标签默认色(aria-pressed)', [b.get_attribute('aria-label') for b in dlg.find_elements(By.CSS_SELECTOR, 'button[aria-pressed="true"]')])
        ev('初始创建钮 disabled', submit_btn(dlg).get_attribute('disabled'))
        shot(d, '05_tag_dialog_light_empty')
        name_i.send_keys(TAG_A)
        time.sleep(0.5)
        ev('仅填名称(未选分类) disabled', submit_btn(dlg).get_attribute('disabled'))
        ev('未选分类提示', [p.text for p in dlg.find_elements(By.CSS_SELECTOR, 'p') if '请选择所属分类' in p.text])
        opts = choose_category(d, dlg, CAT_A)
        ev('分类下拉选项', opts)
        ev('API 分类条数(对照)', len(cat_list(d)))
        dlg.find_element(By.ID, 'tag-desc').send_keys('INT-1487 测试标签A')
        palette(dlg, '#f97316', d)
        shot(d, '06_tag_dialog_light_filled')
        js_click(d, submit_btn(dlg))
        time.sleep(3)
        net = show_net(collect(d))
        post = [n for n in net if n['t'] == 'REQ' and n['method'] == 'POST']
        resp = [n for n in net if n['t'] == 'RESP' and n['url'].rstrip('/').endswith('/tags')]
        ev('POST /tags body', post[0]['body'] if post else 'MISSING')
        ev('POST /tags status', resp[0]['status'] if resp else 'MISSING')
        ev('toast', toast_text(d))
        time.sleep(1)
        tags = tag_list(d)
        mine = [t for t in tags if t['name'] == TAG_A]
        ev('回读标签', json.dumps(mine, ensure_ascii=False))
        rows = d.find_elements(By.CSS_SELECTOR, 'tbody tr')
        hit = [r.text for r in rows if TAG_A in r.text]
        ev('UI 标签行', hit[0].replace('\n', ' | ') if hit else 'MISSING')
        body = d.find_element(By.TAG_NAME, 'body').text
        ev('UI 标签总数(建后)', re.search(r'共 (\d+) 个标签', body).group(1))
        ev('分类树 tagCount', [s.text for s in d.find_elements(By.CSS_SELECTOR, 'span.bg-muted')][:6])
        shot(d, '07_page_light_tag_created')
    section(s4)

    # ---------- S5 分类删除拦截 ----------
    def s5():
        step('S5 有标签的分类删除拦截（禁用 + tooltip）')
        js_click(d, d.find_elements(By.XPATH, f"//button[.//span[normalize-space(.)='{CAT_A}']]")[0])
        time.sleep(1.5)
        btn = d.find_elements(By.CSS_SELECTOR, f'[aria-label="删除分类 {CAT_A}"]')
        ev('分类删除钮 disabled(有标签)', btn[0].get_attribute('disabled') if btn else 'MISSING')
        if btn:
            ActionChains(d).move_to_element(btn[0]).perform()
            time.sleep(1.2)
            tips = [t.text for t in d.find_elements(By.CSS_SELECTOR, '[role="tooltip"]')]
            ev('分类删除 tooltip', tips)
            shot(d, '08_category_delete_blocked_light')
        # 回未分类视图
        js_click(d, d.find_elements(By.XPATH, "//button[.//span[normalize-space(.)='未分类']]")[0])
        time.sleep(1.5)
    section(s5)

    # ---------- S6 标签编辑 ----------
    def s6():
        step('S6 标签编辑：回显 → 改每字段 → 保存 → 回读')
        drain(d)
        js_click(d, d.find_elements(By.CSS_SELECTOR, f'[aria-label="编辑标签 {TAG_A}"]')[0])
        dlg = wait_dialog(d, '编辑标签')
        ev('编辑标题', dlg.find_elements(By.CSS_SELECTOR, 'h2')[0].text)
        ev('回显名称', dlg.find_element(By.ID, 'tag-name').get_attribute('value'))
        ev('回显分类', dlg.find_elements(By.CSS_SELECTOR, '[role="combobox"]')[0].text)
        ev('回显描述', dlg.find_element(By.ID, 'tag-desc').get_attribute('value'))
        ev('回显颜色(aria-pressed)', [b.get_attribute('aria-label') for b in dlg.find_elements(By.CSS_SELECTOR, 'button[aria-pressed="true"]')])
        shot(d, '09_tag_dialog_light_edit_prefill')
        name_i = dlg.find_element(By.ID, 'tag-name')
        name_i.send_keys(Keys.CONTROL, 'a')
        name_i.send_keys(Keys.DELETE)
        name_i.send_keys(TAG_A2)
        desc_i = dlg.find_element(By.ID, 'tag-desc')
        desc_i.send_keys(Keys.CONTROL, 'a')
        desc_i.send_keys(Keys.DELETE)
        desc_i.send_keys('描述已改 INT1487')
        choose_category(d, dlg, CAT_B)
        palette(dlg, '#06b6d4', d)
        js_click(d, submit_btn(dlg))
        time.sleep(3)
        net = show_net(collect(d))
        put = [n for n in net if n['t'] == 'REQ' and n['method'] == 'PUT']
        resp = [n for n in net if n['t'] == 'RESP' and 'PUT' not in n.get('method', '')]
        ev('PUT body', put[0]['body'] if put else 'MISSING')
        ev('PUT url/status', [(n['url'].split('15173')[-1], n['status']) for n in net if n['t'] == 'RESP' and '/tags/' in n['url']])
        ev('toast', toast_text(d))
        time.sleep(1)
        mine = [t for t in tag_list(d) if t['name'] == TAG_A2]
        ev('回读标签(改后)', json.dumps(mine, ensure_ascii=False))
        hit = [r.text.replace('\n', ' | ') for r in d.find_elements(By.CSS_SELECTOR, 'tbody tr') if TAG_A2 in r.text]
        ev('UI 行(改后)', hit)
        cats = cat_list(d)
        ev('分类 tagCount(改后)', [(c['name'], c.get('tag_count')) for c in cats])
        body = d.find_element(By.TAG_NAME, 'body').text
        ev('分类树计数文本', [s.text for s in d.find_elements(By.CSS_SELECTOR, 'span.bg-muted')][:8])
        shot(d, '10_page_light_tag_edited')
        # 切到分类B视图核对过滤
        js_click(d, d.find_elements(By.XPATH, f"//button[.//span[normalize-space(.)='{CAT_B}']]")[0])
        time.sleep(2)
        body = d.find_element(By.TAG_NAME, 'body').text
        ev('分类B视图标题/计数', re.search(rf'{CAT_B}\s*共 (\d+) 个标签', body).group(0) if re.search(rf'{CAT_B}\s*共 (\d+) 个标签', body) else 'N/A')
        ev('分类B视图行数', len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')))
        shot(d, '11_page_light_categoryB_view')
    section(s6)

    # ---------- S7 同名校验 ----------
    def s7():
        step('S7 同名标签校验（同分类重复名）')
        drain(d)
        dlg = open_tag_dialog(d)
        dlg.find_element(By.ID, 'tag-name').send_keys(TAG_A2)
        choose_category(d, dlg, CAT_B)
        js_click(d, submit_btn(dlg))
        time.sleep(3)
        net = show_net(collect(d))
        ev('同名 POST 状态', [n['status'] for n in net if n['t'] == 'RESP' and n['url'].rstrip('/').endswith('/tags')])
        ev('同名 弹窗错误文案', [p.text for p in dlg.find_elements(By.CSS_SELECTOR, 'p.text-destructive')])
        ev('同名 toast', toast_text(d))
        ev('同名 弹窗仍开', len(dialogs(d)) > 0)
        shot(d, '12_tag_dialog_light_duplicate_error')
        close_top_dialog(d)
        time.sleep(0.8)
        ev('同名后分类B标签数(未新增)', len([t for t in tag_list(d) if t['name'] == TAG_A2]))
    section(s7)

    # ---------- S8 取消/重开残留 ----------
    def s8():
        step('S8 取消与重开：Esc / 取消钮 / 遮罩；重开是否残留')
        # Esc
        dlg = open_tag_dialog(d)
        dlg.find_element(By.ID, 'tag-name').send_keys('残留检查')
        choose_category(d, dlg, CAT_A)
        d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(1.2)
        ev('Esc 后弹窗数', len(dialogs(d)))
        # 取消钮
        dlg = open_tag_dialog(d)
        namev = dlg.find_element(By.ID, 'tag-name').get_attribute('value')
        ev('重开后名称残留', repr(namev))
        ev('重开后分类', dlg.find_elements(By.CSS_SELECTOR, '[role="combobox"]')[0].text)
        ev('重开后颜色', [b.get_attribute('aria-label') for b in dlg.find_elements(By.CSS_SELECTOR, 'button[aria-pressed="true"]')])
        shot(d, '13_tag_dialog_light_reopen_empty')
        canc = [b for b in dlg.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() == '取消']
        js_click(d, canc[0])
        time.sleep(1.2)
        ev('取消钮后弹窗数', len(dialogs(d)))
        # 遮罩
        dlg = open_tag_dialog(d)
        backdrop = d.find_elements(By.CSS_SELECTOR, '[data-slot="dialog-backdrop"],[data-base-ui-focus-guard]')
        log('  backdrop candidates', len(backdrop))
        try:
            ActionChains(d).move_by_offset(5, 5).click().perform()
            time.sleep(1.2)
        except Exception as e:
            log('  backdrop click err', e)
        ev('遮罩点击后弹窗数', len(dialogs(d)))
        if dialogs(d):
            close_top_dialog(d)
        time.sleep(0.8)
    section(s8)

    # ---------- S9 空态 ----------
    def s9():
        step('S9 空态：搜索无匹配 / 分类空视图')
        d.get(BASE + '/TagManagement')
        time.sleep(8)
        js_click(d, d.find_elements(By.XPATH, "//button[.//span[normalize-space(.)='未分类']]")[0])
        time.sleep(1.5)
        si = d.find_element(By.CSS_SELECTOR, 'input[aria-label="搜索标签"]')
        si.click()
        si.send_keys('zzz_nomatch_INT1487')
        time.sleep(2.5)
        body = d.find_element(By.TAG_NAME, 'body').text
        ev('空态文案', '没有找到匹配的标签' in body)
        ev('空态副文案', '调整搜索关键词后重试' in body)
        ev('空态行数', len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')))
        shot(d, '14_page_light_empty_search')
        si.send_keys(Keys.CONTROL, 'a')
        si.send_keys(Keys.DELETE)
        time.sleep(2)
        ev('清空后行数', len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')))
    section(s9)

    # ---------- S10 错误态 ----------
    def s10():
        step('S10 错误态：拦截 /api/v1/tags 请求')
        d.execute_cdp_cmd('Network.enable', {})
        d.execute_cdp_cmd('Network.setBlockedURLs', {'urls': ['*/api/v1/tags*']})
        drain(d)
        d.get(BASE + '/TagManagement')
        time.sleep(10)
        body = d.find_element(By.TAG_NAME, 'body').text
        ev('错误态 body(标签区)', [ln for ln in body.split('\n') if '标签' in ln or '失败' in ln or '重试' in ln][:12])
        ev('错误态 toast', toast_text(d))
        ev('错误态 是否显示「暂无标签」', '暂无标签' in body)
        ev('错误态 是否有错误提示', any(k in body for k in ('加载失败', '请求失败', '重试', '出错了')))
        ev('错误态 行数', len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')))
        shot(d, '15_page_light_error_blocked')
        d.execute_cdp_cmd('Network.setBlockedURLs', {'urls': []})
        time.sleep(1)
    section(s10)

    # ---------- S11 深色截图 ----------
    def s11():
        step('S11 深色主题截图（页面 + 各弹窗）')
        theme(d, 'dark')
        goto_tags(d)
        shot(d, '20_page_dark')
        dlg = open_tag_dialog(d)
        shot(d, '21_tag_dialog_dark_empty')
        dlg.find_element(By.ID, 'tag-name').send_keys(TAG_A2)
        choose_category(d, dlg, CAT_B)
        shot(d, '22_tag_dialog_dark_filled')
        close_top_dialog(d)
        time.sleep(1)
        js_click(d, d.find_elements(By.XPATH, "//button[normalize-space(.)='新建']")[0])
        dlg = wait_dialog(d, '新建分类')
        shot(d, '23_category_dialog_dark')
        close_top_dialog(d)
        time.sleep(1)
        js_click(d, d.find_elements(By.CSS_SELECTOR, f'[aria-label="编辑标签 {TAG_A2}"]')[0])
        dlg = wait_dialog(d, '编辑标签')
        shot(d, '24_tag_dialog_dark_edit')
        close_top_dialog(d)
        time.sleep(1)
        dlg = delete_confirm(d, f'删除标签 {TAG_A2}')
        shot(d, '25_confirm_delete_dark')
        canc = [b for b in dlg.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() == '取消']
        if canc:
            js_click(d, canc[0])
        time.sleep(1)
        theme(d, 'light')
        goto_tags(d)
    section(s11)

    # ---------- S12 删除闭环 ----------
    def s12():
        step('S12 标签删除 → 分类删除 → 接口回读')
        drain(d)
        dlg = delete_confirm(d, f'删除标签 {TAG_A2}')
        ev('确认弹窗标题', dlg.find_elements(By.CSS_SELECTOR, 'h2')[0].text if dlg.find_elements(By.CSS_SELECTOR, 'h2') else dlg.text[:40])
        ev('确认弹窗文案', dlg.text.replace('\n', ' | ')[:160])
        shot(d, '26_confirm_delete_light')
        confirm_delete(d, dlg)
        net = show_net(collect(d))
        ev('DELETE 请求', [(n['method'], n['url'].split('15173')[-1]) for n in net if n['t'] == 'REQ'])
        ev('DELETE 响应', [(n['url'].split('15173')[-1], n['status']) for n in net if n['t'] == 'RESP' and '/tags' in n['url']])
        ev('toast(删标签)', toast_text(d))
        time.sleep(1)
        ev('回读标签(删后)', [t['name'] for t in tag_list(d) if t['name'].startswith(P)])
        ev('UI 行(删后)', [r.text.replace('\n', ' | ') for r in d.find_elements(By.CSS_SELECTOR, 'tbody tr') if TAG_A2 in r.text])
        time.sleep(1)
        # 删两个分类
        for name in (CAT_A, CAT_B):
            js_click(d, d.find_elements(By.XPATH, f"//button[.//span[normalize-space(.)='{name}']]")[0])
            time.sleep(1.5)
            drain(d)
            dlg = delete_confirm(d, f'删除分类 {name}')
            confirm_delete(d, dlg)
            net = show_net(collect(d))
            ev(f'DELETE 分类 {name}', [(n['url'].split('15173')[-1], n['status']) for n in net if n['t'] == 'RESP' and '/tags' in n['url']])
            ev('toast(删分类)', toast_text(d))
            time.sleep(1)
        ev('回读分类(删后)', json.dumps([c['name'] for c in cat_list(d)], ensure_ascii=False))
        body = d.find_element(By.TAG_NAME, 'body').text
        ev('UI 分类计数(删后)', re.search(r'标签分类\s*共 (\d+) 个', body).group(1) if re.search(r'标签分类\s*共 (\d+) 个', body) else 'N/A')
        shot(d, '27_page_light_after_cleanup')
    section(s12)

    step('S13 数据卫生')
    left = [t['name'] for t in tag_list(d) if t['name'].startswith(P)]
    leftc = [c['name'] for c in cat_list(d) if c['name'].startswith(P)]
    ev('残留标签', left)
    ev('残留分类', leftc)
    log('\nERRORS:', ERRORS)
finally:
    try:
        d.quit()
    except Exception:
        pass
