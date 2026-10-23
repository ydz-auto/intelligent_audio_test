# -*- coding: utf-8 -*-
"""INT-1487 用例页标签入口深走查（docker 15173 + 15000 真实库栈；后端慢，长等待版）。
幂等造数：分类/标签/分组/用例已存在则复用；结束前清理。
覆盖：标签 facet 选项与过滤、用例编辑抽屉打标签、批量管理标签（加/移/改名）、深浅色截图。
"""
import json
import os
import re
import sys
import time
import winreg

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from selenium import webdriver
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
CAT = P + '分类'
TAG_X = P + '标签X'
TAG_Y = P + '标签Y'
TAG_X2 = P + '标签X改'
GRP = P + '分组'
CASE1 = P + '用例1'
CASE2 = P + '用例2'
ERRORS = []


def log(*a):
    print(*a, flush=True)


def step(s):
    log('\n' + '=' * 20, s)


def driver():
    o = Options()
    o.binary_location = CHROME
    for a in ('--headless=new', '--window-size=1680,1050', '--disable-gpu', '--no-sandbox',
              '--lang=zh-CN', '--disable-dev-shm-usage', '--disable-extensions', '--no-proxy-server'):
        o.add_argument(a)
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
        c = []
        for v in os.listdir(cache):
            e = os.path.join(cache, v, 'chromedriver.exe')
            if os.path.isfile(e):
                try:
                    c.append((tuple(int(x) for x in v.split('.') if x.isdigit()), e))
                except ValueError:
                    pass
        same = [e for vv, e in c if vv and vv[0] == major]
        if same:
            path = max(same)
    d = webdriver.Chrome(options=o, service=Service(path) if path else Service())
    d.set_page_load_timeout(120)
    return d


def drain(d):
    d.get_log('performance')


def collect(d, needles=('/api/v1/tags', '/api/v1/testcases', '/api/v1/groups')):
    out = []
    for e in d.get_log('performance'):
        try:
            msg = json.loads(e['message'])['message']
        except Exception:
            continue
        m = msg.get('method')
        p = msg.get('params', {})
        if m == 'Network.requestWillBeSent':
            r = p['request']
            if any(n in r['url'] for n in needles):
                out.append(('REQ', r['method'], r['url'], r.get('postData')))
        elif m == 'Network.responseReceived':
            r = p['response']
            if any(n in r['url'] for n in needles):
                out.append(('RESP', r['status'], r['url'], None))
    return out


def show_net(rows):
    for t, a, u, b in rows:
        if t == 'REQ':
            log(f'  NET {a} {u.split("15173")[-1]} body={b}')
        else:
            log(f'  NET <- {a} {u.split("15173")[-1]}')


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
    d.set_script_timeout(150)
    res = d.execute_async_script(script, method, path, body)
    try:
        res['json'] = json.loads(res['body'])
    except Exception:
        res['json'] = None
    return res


def dat(res):
    return (res.get('json') or {}).get('data')


def js_click(d, el):
    d.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)
    time.sleep(0.35)


def shot(d, name):
    p = os.path.join(ART, name + '.png')
    d.save_screenshot(p)
    log('  shot', p)


def dialogs(d):
    return d.find_elements(By.CSS_SELECTOR, '[role="dialog"],[role="alertdialog"]')


def wait_dialog(d, title, timeout=25):
    end = time.time() + timeout
    while time.time() < end:
        for el in dialogs(d):
            if title in (el.text or ''):
                return el
        time.sleep(0.4)
    raise AssertionError(f'弹窗未出现 {title}; 现有 {[x.text[:40] for x in dialogs(d)]}')


def close_top(d):
    for el in reversed(dialogs(d)):
        for b in el.find_elements(By.TAG_NAME, 'button'):
            al = b.get_attribute('aria-label') or ''
            if al.startswith('Close'):
                js_click(d, b)
                time.sleep(0.8)
                return True
    return False


def load_cases_page(d, wait=40):
    d.get(BASE + '/testcases/by-group')
    end = time.time() + wait
    while time.time() < end:
        if d.find_elements(By.XPATH, "//button[.//span[normalize-space(.)='标签']]"):
            break
        time.sleep(1)
    time.sleep(3)


def theme(d, mode):
    d.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0])", mode)
    d.get('about:blank')
    load_cases_page(d)


def expand_group(d, name):
    end = time.time() + 25
    while time.time() < end:
        for sp in d.find_elements(By.XPATH, f"//span[normalize-space(.)='{name}']"):
            try:
                js_click(d, sp)
                time.sleep(3)
                return True
            except Exception:
                pass
        time.sleep(1)
    return False


def edit_button_for(d, case_name):
    for b in d.find_elements(By.CSS_SELECTOR, '[aria-label="编辑用例"]'):
        try:
            card = b.find_element(By.XPATH, './ancestor::div[contains(@class,"rounded-xl")][1]')
            if case_name in card.text:
                return b
        except Exception:
            continue
    return None


def section(fn):
    try:
        fn()
    except Exception as e:
        import traceback
        traceback.print_exc()
        ERRORS.append(f'{fn.__name__}: {e}')
        log('  !! section error', fn.__name__, e)


d = driver()
try:
    step('T0 环境核对 #2')
    import urllib.request
    with urllib.request.urlopen('http://127.0.0.1:15000/health', timeout=15) as r:
        h = json.loads(r.read().decode())
    log('  health', h)
    with urllib.request.urlopen(BASE + '/', timeout=15) as r:
        html = r.read().decode('utf-8', 'replace')
    log('  lib-react', (re.search(r'lib-react[^"]*', html) or ['?'])[0])

    step('T1 登录 + 幂等造数')
    d.get(BASE + '/login')
    end = time.time() + 60
    while time.time() < end and not d.find_elements(By.ID, 'username'):
        if '/login' not in d.current_url:
            break
        time.sleep(1)
    if d.find_elements(By.ID, 'username'):
        d.find_element(By.ID, 'username').send_keys('接线测试_admin')
        d.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
        for b in d.find_elements(By.TAG_NAME, 'button'):
            if '登' in b.text and '录' in b.text:
                js_click(d, b)
                break
    WebDriverWait(d, 60).until(lambda x: '/login' not in x.current_url)
    time.sleep(3)
    log('  登录后', d.current_url)

    def call(method, path, body=None, tries=3):
        last = None
        for i in range(tries):
            r = api(d, method, path, body)
            if r['status'] and 200 <= r['status'] < 300 and dat(r) is not None:
                return dat(r)
            last = r
            log(f'  !! {method} {path} -> {r["status"]} {r["body"][:120]} (retry {i+1})')
            time.sleep(3)
        raise AssertionError(f'{method} {path} 失败 {last["status"]}')

    cats = call('GET', '/tags/categories?page=1&per_page=100').get('items', [])
    cat = next((c for c in cats if c['name'] == CAT), None)
    if not cat:
        cat = call('POST', '/tags/categories',
                   {'name': CAT, 'description': 'INT1487 用例页测试分类', 'color': '#8b5cf6', 'sort_order': 9})
    cat_id = cat['id']
    tags = call('GET', '/tags?page=1&per_page=100').get('items', [])
    by_name = {t['name']: t for t in tags}
    for nm, col, desc in ((TAG_X, '#f97316', 'INT1487 标签X'), (TAG_Y, '#06b6d4', 'INT1487 标签Y')):
        if nm not in by_name:
            call('POST', '/tags', {'name': nm, 'description': desc, 'color': col, 'category_id': cat_id})
    tags = call('GET', '/tags?page=1&per_page=100').get('items', [])
    by_name = {t['name']: t for t in tags}
    log('  标签', {k: by_name[k]['id'] for k in (TAG_X, TAG_Y) if k in by_name}, '共', len(tags))
    gs = call('GET', '/groups?page=1&per_page=200').get('items', [])
    grp = next((g for g in gs if g['name'] == GRP), None)
    if not grp:
        grp = call('POST', '/groups', {'name': GRP, 'description': 'INT1487 测试分组', 'algorithm_type': ''})
    gid = grp['id']
    cases = call('GET', f'/testcases?page=1&per_page=100&group_id={gid}').get('items', [])
    have = {c['name']: c for c in cases}
    for nm in (CASE1, CASE2):
        if nm not in have:
            call('POST', '/testcases', {'name': nm, 'description': '', 'group_id': gid, 'tags': []})
    cases = call('GET', f'/testcases?page=1&per_page=100&group_id={gid}').get('items', [])
    log('  组内用例', [(c['name'], c['tags']) for c in cases])
    id_by_name = {c['name']: c['id'] for c in cases}
    id1, id2 = str(id_by_name.get(CASE1, '')), str(id_by_name.get(CASE2, ''))
    assert id1 and id2, '造数失败'

    # ---------- facet ----------
    def t2():
        step('T2 标签 facet：选项条数 / 分类分组 / 选中过滤')
        load_cases_page(d)
        trig = d.find_elements(By.XPATH, "//button[.//span[normalize-space(.)='标签']]")[0]
        js_click(d, trig)
        time.sleep(2)
        pop = d.find_elements(By.CSS_SELECTOR, '[data-slot="popover-content"]')
        assert pop, 'facet popover 未打开'
        pop = pop[0]
        btns = [b for b in pop.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip()]
        texts = [(b.text or '').strip() for b in btns]
        log('  facet 选项按钮数', len(texts))
        log('  popover 首行(组头)', pop.text.splitlines()[0] if pop.text else '')
        log('  popover 含测试分类组头', CAT in pop.text)
        tags_api = call('GET', '/tags?page=1&per_page=100').get('items', [])
        log('  API 标签条数', len(tags_api))
        shot(d, '30_facet_light_open')
        target = [b for b in btns if (b.text or '').strip() == TAG_X]
        assert target, 'facet 无标签 X'
        js_click(d, target[0])
        time.sleep(5)
        body = d.find_element(By.TAG_NAME, 'body').text
        log('  选中标签X 后列表为空态', '没有找到符合条件的测试用例' in body)
        shot(d, '31_facet_light_filtered_empty')
        load_cases_page(d)
    section(t2)

    # ---------- 抽屉打标签 ----------
    def t3():
        step('T3 用例编辑抽屉打标签 → 保存 → 回读')
        drain(d)
        si = d.find_element(By.CSS_SELECTOR, 'input[aria-label="搜索用例"]')
        si.click()
        si.send_keys(P)
        time.sleep(8)
        if CASE1 not in d.find_element(By.TAG_NAME, 'body').text:
            expand_group(d, GRP)
            time.sleep(3)
        log('  用例1 可见', CASE1 in d.find_element(By.TAG_NAME, 'body').text)
        btn = edit_button_for(d, CASE1)
        assert btn is not None, '未找到用例1 编辑钮'
        js_click(d, btn)
        dlg = wait_dialog(d, '编辑用例')
        time.sleep(1.5)
        tag_in = None
        for i in dlg.find_elements(By.TAG_NAME, 'input'):
            if '标签' in (i.get_attribute('placeholder') or ''):
                tag_in = i
                break
        assert tag_in is not None, '抽屉标签输入框缺失'
        shot(d, '32_drawer_light_tag_section')
        tag_in.send_keys(TAG_X)
        time.sleep(1)
        tag_in.send_keys(Keys.ENTER)
        time.sleep(1.2)
        log('  抽屉 chips', [b.text for b in dlg.find_elements(By.CSS_SELECTOR, '[data-slot="badge"]')][:6])
        save = None
        for b in dlg.find_elements(By.TAG_NAME, 'button'):
            if (b.text or '').strip() in ('保存', '确定', '保存修改'):
                save = b
                break
        assert save is not None, '抽屉保存钮缺失'
        log('  保存钮', save.text)
        js_click(d, save)
        time.sleep(6)
        net = collect(d)
        show_net([n for n in net if n[0] == 'REQ' and n[1] in ('PUT', 'POST')])
        rec = call('GET', f'/testcases?page=1&per_page=100&group_id={gid}').get('items', [])
        log('  回读用例', [(c['name'], c['tags']) for c in rec])
        shot(d, '33_case_tagged_light')
    section(t3)

    # ---------- 批量 ----------
    def t4():
        step('T4 批量管理标签：加 Y / 移 Y / 改名')
        boxes = d.find_elements(By.CSS_SELECTOR, '[aria-label^="选择 接线测试_INT1487"]')
        if len(boxes) < 2:
            load_cases_page(d)
            si = d.find_element(By.CSS_SELECTOR, 'input[aria-label="搜索用例"]')
            si.click()
            si.send_keys(P)
            time.sleep(8)
            if CASE1 not in d.find_element(By.TAG_NAME, 'body').text:
                expand_group(d, GRP)
                time.sleep(3)
            boxes = d.find_elements(By.CSS_SELECTOR, '[aria-label^="选择 接线测试_INT1487"]')
        log('  勾选框', [b.get_attribute('aria-label') for b in boxes])
        for b in boxes:
            js_click(d, b)
            time.sleep(0.8)
        bar = d.find_elements(By.XPATH, "//button[contains(., '批量管理标签')]")
        assert bar, '批量管理标签入口缺失'
        log('  批量浮条出现，按钮数', len(bar))
        drain(d)
        js_click(d, bar[0])
        dlg = wait_dialog(d, '批量管理标签')
        time.sleep(1.5)
        log('  弹窗说明', [ln for ln in dlg.text.splitlines() if '勾选' in ln])
        radios = dlg.find_elements(By.CSS_SELECTOR, 'input[name="batch-tag-mode"]')
        log('  模式', len(radios), [r.is_selected() for r in radios])
        log('  默认模式 add 选中', radios[0].is_selected())
        shot(d, '34_batch_tags_light_add')
        tin = [i for i in dlg.find_elements(By.TAG_NAME, 'input') if '回车' in (i.get_attribute('placeholder') or '')]
        assert tin, '批量标签输入框缺失'
        tin[0].send_keys(TAG_Y)
        tin[0].send_keys(Keys.ENTER)
        time.sleep(1)
        ok = [b for b in dlg.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() == '确定'][0]
        shot(d, '35_batch_tags_light_chip')
        js_click(d, ok)
        time.sleep(6)
        net = collect(d)
        show_net([n for n in net if n[0] == 'REQ' and '/testcases/batch' in n[2]])
        rec = call('GET', f'/testcases?page=1&per_page=100&group_id={gid}').get('items', [])
        log('  回读(加Y)', [(c['name'], c['tags']) for c in rec])
        shot(d, '36_batch_tags_after_add_light')

        # 移除 Y
        drain(d)
        boxes = d.find_elements(By.CSS_SELECTOR, '[aria-label^="选择 接线测试_INT1487"][aria-checked="true"]')
        if not boxes:
            boxes = d.find_elements(By.CSS_SELECTOR, '[aria-label^="选择 接线测试_INT1487"]')
            for b in boxes:
                js_click(d, b)
                time.sleep(0.6)
        bar = d.find_elements(By.XPATH, "//button[contains(., '批量管理标签')]")
        js_click(d, bar[0])
        dlg = wait_dialog(d, '批量管理标签')
        time.sleep(1.2)
        radios = dlg.find_elements(By.CSS_SELECTOR, 'input[name="batch-tag-mode"]')
        js_click(d, radios[1])
        time.sleep(0.8)
        tin = [i for i in dlg.find_elements(By.TAG_NAME, 'input') if '回车' in (i.get_attribute('placeholder') or '')]
        tin[0].send_keys(TAG_Y)
        tin[0].send_keys(Keys.ENTER)
        time.sleep(0.6)
        ok = [b for b in dlg.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() == '确定'][0]
        js_click(d, ok)
        time.sleep(6)
        net = collect(d)
        show_net([n for n in net if n[0] == 'REQ' and '/testcases/batch' in n[2]])
        rec = call('GET', f'/testcases?page=1&per_page=100&group_id={gid}').get('items', [])
        log('  回读(移Y)', [(c['name'], c['tags']) for c in rec])

        # 改名 X → X改
        bar = d.find_elements(By.XPATH, "//button[contains(., '批量管理标签')]")
        if not bar:
            boxes = d.find_elements(By.CSS_SELECTOR, '[aria-label^="选择 接线测试_INT1487"]')
            js_click(d, boxes[0])
            time.sleep(1)
            bar = d.find_elements(By.XPATH, "//button[contains(., '批量管理标签')]")
        drain(d)
        js_click(d, bar[0])
        dlg = wait_dialog(d, '批量管理标签')
        time.sleep(1.2)
        radios = dlg.find_elements(By.CSS_SELECTOR, 'input[name="batch-tag-mode"]')
        js_click(d, radios[2])
        time.sleep(1)
        shot(d, '37_batch_tags_light_rename')
        trig = dlg.find_elements(By.CSS_SELECTOR, '[role="combobox"]')
        log('  rename Select 数', len(trig))
        js_click(d, trig[0])
        time.sleep(1.5)
        opts = d.find_elements(By.CSS_SELECTOR, '[role="option"]')
        log('  rename 选项数', len(opts), '含X', any((o.text or '').strip() == TAG_X for o in opts))
        for o in opts:
            if (o.text or '').strip() == TAG_X:
                js_click(d, o)
                break
        time.sleep(1)
        rin = [i for i in dlg.find_elements(By.TAG_NAME, 'input') if '新标签名' in (i.get_attribute('placeholder') or '')]
        assert rin, '新标签名输入框缺失'
        rin[0].send_keys(TAG_X2)
        time.sleep(0.6)
        ok = [b for b in dlg.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() == '确定'][0]
        log('  改名 确定 disabled', ok.get_attribute('disabled'))
        js_click(d, ok)
        time.sleep(6)
        net = collect(d)
        show_net([n for n in net if n[0] == 'REQ' and '/testcases/batch' in n[2]])
        rec = call('GET', f'/testcases?page=1&per_page=100&group_id={gid}').get('items', [])
        log('  回读(改名后)', [(c['name'], c['tags']) for c in rec])
        tags = call('GET', '/tags?page=1&per_page=100').get('items', [])
        log('  标签注册表测试项', [t['name'] for t in tags if t['name'].startswith(P)])

        # 同名改名可用性（V9.7.10 有「新旧同名」禁用校验）
        bar = d.find_elements(By.XPATH, "//button[contains(., '批量管理标签')]")
        if bar:
            js_click(d, bar[0])
            dlg = wait_dialog(d, '批量管理标签')
            time.sleep(1.2)
            radios = dlg.find_elements(By.CSS_SELECTOR, 'input[name="batch-tag-mode"]')
            js_click(d, radios[2])
            time.sleep(0.8)
            trig = dlg.find_elements(By.CSS_SELECTOR, '[role="combobox"]')
            js_click(d, trig[0])
            time.sleep(1.2)
            for o in d.find_elements(By.CSS_SELECTOR, '[role="option"]'):
                if (o.text or '').strip() == TAG_X2:
                    js_click(d, o)
                    break
            rin = [i for i in dlg.find_elements(By.TAG_NAME, 'input') if '新标签名' in (i.get_attribute('placeholder') or '')]
            rin[0].send_keys(TAG_X2)
            time.sleep(0.8)
            ok = [b for b in dlg.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() == '确定'][0]
            log('  同名改名 确定 disabled（V9.7.10 期望 disabled=True）', ok.get_attribute('disabled'))
            shot(d, '38_batch_tags_same_name_light')
            close_top(d)
            time.sleep(1)
    section(t4)

    # ---------- 过滤计数 ----------
    def t5():
        step('T5 改名后 facet 过滤')
        load_cases_page(d)
        trig = d.find_elements(By.XPATH, "//button[.//span[normalize-space(.)='标签']]")[0]
        js_click(d, trig)
        time.sleep(2)
        pop = d.find_elements(By.CSS_SELECTOR, '[data-slot="popover-content"]')
        assert pop, 'facet popover 未打开'
        btns = [b for b in pop[0].find_elements(By.TAG_NAME, 'button') if (b.text or '').strip()]
        texts = [(b.text or '').strip() for b in btns]
        log('  facet 测试项', [t for t in texts if P in t], '总选项', len(texts))
        tgt = [b for b in btns if (b.text or '').strip() == TAG_X2]
        assert tgt, 'facet 无 X改'
        js_click(d, tgt[0])
        time.sleep(6)
        body = d.find_element(By.TAG_NAME, 'body').text
        log('  过滤后可见用例1', CASE1 in body, '可见用例2', CASE2 in body)
        shot(d, '39_facet_filtered_light')
    section(t5)

    # ---------- 深色 ----------
    def t6():
        step('T6 深色截图（facet / 抽屉 / 批量弹窗）')
        theme(d, 'dark')
        trig = d.find_elements(By.XPATH, "//button[.//span[normalize-space(.)='标签']]")[0]
        js_click(d, trig)
        time.sleep(2)
        shot(d, '41_facet_dark')
        d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(1.5)
        si = d.find_element(By.CSS_SELECTOR, 'input[aria-label="搜索用例"]')
        si.click()
        si.send_keys(P)
        time.sleep(8)
        if CASE1 not in d.find_element(By.TAG_NAME, 'body').text:
            expand_group(d, GRP)
            time.sleep(3)
        btn = edit_button_for(d, CASE1)
        if btn:
            js_click(d, btn)
            wait_dialog(d, '编辑用例')
            time.sleep(1.5)
            shot(d, '42_drawer_dark')
            close_top(d)
            time.sleep(1)
        else:
            log('  深色：未找到编辑钮')
        boxes = d.find_elements(By.CSS_SELECTOR, '[aria-label^="选择 接线测试_INT1487"]')
        if boxes:
            js_click(d, boxes[0])
            time.sleep(1.5)
            bar = d.find_elements(By.XPATH, "//button[contains(., '批量管理标签')]")
            if bar:
                js_click(d, bar[0])
                wait_dialog(d, '批量管理标签')
                time.sleep(1.5)
                shot(d, '43_batch_tags_dark')
                close_top(d)
                time.sleep(1)
        theme(d, 'light')
    section(t6)

    # ---------- 清理 ----------
    def t7():
        step('T7 清理与校验')
        cur = call('GET', f'/testcases?page=1&per_page=100&group_id={gid}').get('items', [])
        ids = [str(c['id']) for c in cur]
        for cid in ids:
            r = api(d, 'DELETE', f'/testcases/{cid}')
            log('  软删', cid, r['status'])
            time.sleep(1)
        if ids:
            r = api(d, 'POST', '/testcases/purge', {'ids': ids})
            log('  purge', r['status'], r['body'][:100])
        r = api(d, 'DELETE', f'/groups/{gid}?cascade=true')
        log('  删分组', r['status'], r['body'][:100])
        tags = call('GET', '/tags?page=1&per_page=100').get('items', [])
        for t in tags:
            if t['name'].startswith(P):
                rr = api(d, 'DELETE', f"/tags/{t['id']}?cascade=false")
                log('  删标签', t['name'], rr['status'])
                time.sleep(1)
        cats = call('GET', '/tags/categories?page=1&per_page=100').get('items', [])
        for c in cats:
            if c['name'].startswith(P):
                rr = api(d, 'DELETE', f"/tags/categories/{c['id']}")
                log('  删分类', c['name'], rr['status'])
                time.sleep(1)
        left_t = [t['name'] for t in call('GET', '/tags?page=1&per_page=100').get('items', []) if t['name'].startswith(P)]
        left_c = [c['name'] for c in call('GET', '/tags/categories?page=1&per_page=100').get('items', []) if c['name'].startswith(P)]
        left_g = [g['name'] for g in call('GET', '/groups?page=1&per_page=200').get('items', []) if g['name'].startswith(P)]
        log('  残留标签/分类/分组', left_t, left_c, left_g)
    section(t7)

    log('\nERRORS:', ERRORS)
finally:
    try:
        d.quit()
    except Exception:
        pass
