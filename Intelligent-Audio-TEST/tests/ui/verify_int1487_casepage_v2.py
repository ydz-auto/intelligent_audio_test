# -*- coding: utf-8 -*-
"""INT-1487 用例页标签入口深走查 v2（docker 15173 + 15000 真实库栈）。
覆盖：facet 选项/分类分组/计数/过滤/取消、编辑抽屉打标签（回车+建议+逗号+移除+保存回读）、
批量管理标签（加/移/改名/同名校验）、深浅色截图；结束清理全部「接线测试_INT1487」数据。
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
TAG_X2 = P + '标签X改2'
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


def show_net(rows, only_writes=False):
    for t, a, u, b in rows:
        if only_writes and not (t == 'REQ' and a in ('PUT', 'POST', 'DELETE')):
            continue
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


def call(d, method, path, body=None, tries=3):
    last = None
    for i in range(tries):
        r = api(d, method, path, body)
        if r['status'] and 200 <= r['status'] < 300 and dat(r) is not None:
            return dat(r)
        last = r
        log(f'  !! {method} {path} -> {r["status"]} {r["body"][:150]} (retry {i+1})')
        time.sleep(2)
    raise AssertionError(f'{method} {path} 失败 {last["status"]}')


def js_click(d, el):
    d.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)
    time.sleep(0.3)


def shot(d, name):
    p = os.path.join(ART, name + '.png')
    d.save_screenshot(p)
    log('  shot', os.path.basename(p))


def dialogs(d):
    return d.find_elements(By.CSS_SELECTOR, '[role="dialog"],[role="alertdialog"]')


def wait_dialog(d, title, timeout=30):
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
                time.sleep(0.6)
                return True
    return False


def load_cases_page(d, wait=90):
    t0 = time.time()
    d.get(BASE + '/testcases/by-group')
    end = time.time() + wait
    while time.time() < end:
        if d.find_elements(By.XPATH, "//button[.//span[normalize-space(.)='标签']]"):
            break
        time.sleep(1)
    # 列表数据（分组卡）就绪：出现分组卡勾选框（或明确空态）
    while time.time() < end:
        if d.find_elements(By.CSS_SELECTOR, '[aria-label^="全选分组"]'):
            break
        body = d.find_element(By.TAG_NAME, 'body').text
        if '没有找到符合条件的测试用例' in body and '已显示' not in body:
            time.sleep(1)
            continue
        time.sleep(1)
    log(f'  用例页就绪 {time.time()-t0:.1f}s')


def theme(d, mode):
    d.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0])", mode)
    d.get('about:blank')
    load_cases_page(d)


def visible(d, text):
    return text in d.find_element(By.TAG_NAME, 'body').text


def toasts(d):
    out = []
    for t in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]'):
        tx = (t.text or '').strip().replace('\n', ' / ')
        if tx:
            out.append(tx)
    return out


def load_more(d):
    more = [b for b in d.find_elements(By.TAG_NAME, 'button') if '加载更多' in (b.text or '')]
    if more:
        js_click(d, more[0])
        time.sleep(1.5)
        return True
    return False


def ensure_group_visible(d, name, timeout=100):
    end = time.time() + timeout
    last_click = 0
    while time.time() < end:
        if d.find_elements(By.XPATH, f"//span[normalize-space(.)='{name}']"):
            return True
        if time.time() - last_click > 1.5:
            load_more(d)
            last_click = time.time()
        time.sleep(0.8)
    return False


def expand_group(d, name, timeout=75):
    """展开分组卡并等用例卡渲染；多次尝试（搜索后列表重渲染会让点击失效）。"""
    end = time.time() + timeout
    while time.time() < end:
        if d.find_elements(By.CSS_SELECTOR, f'[aria-label="选择 {P}用例1"]'):
            return True
        if ensure_group_visible(d, name, timeout=12):
            for sp in d.find_elements(By.XPATH, f"//span[normalize-space(.)='{name}']"):
                try:
                    js_click(d, sp)
                    break
                except Exception:
                    pass
        time.sleep(6)
    return False


def collect_until(d, url_substr, timeout=100):
    """点击后轮询 performance log，返回 (目标响应状态, 期间全部事件)。"""
    rows = []
    status = None
    end = time.time() + timeout
    while time.time() < end:
        for e in d.get_log('performance'):
            try:
                msg = json.loads(e['message'])['message']
            except Exception:
                continue
            m = msg.get('method')
            p = msg.get('params', {})
            if m == 'Network.requestWillBeSent':
                r = p['request']
                rows.append(('REQ', r['method'], r['url'], r.get('postData')))
            elif m == 'Network.responseReceived':
                r = p['response']
                rows.append(('RESP', r['status'], r['url'], None))
                if url_substr in r['url']:
                    status = r['status']
        if status is not None:
            break
        time.sleep(0.5)
    return status, rows


def wait_response(d, url_substr, timeout=100, method=None):
    """轮询 performance log，等某 URL 子串的响应；返回状态码或 None。"""
    end = time.time() + timeout
    while time.time() < end:
        for e in d.get_log('performance'):
            try:
                msg = json.loads(e['message'])['message']
            except Exception:
                continue
            if msg.get('method') != 'Network.responseReceived':
                continue
            r = msg['params']['response']
            if url_substr in r['url'] and (method is None or msg['params'].get('type') == method):
                return r['status']
        time.sleep(0.8)
    return None


def search_cases(d, kw, wait=1):
    si = d.find_element(By.CSS_SELECTOR, 'input[aria-label="搜索用例"]')
    si.click()
    si.send_keys(Keys.CONTROL, 'a')
    si.send_keys(Keys.DELETE)
    time.sleep(0.5)
    si.send_keys(kw)
    st = wait_response(d, 'keyword=')
    log('  搜索请求响应', st)
    time.sleep(wait)
    return si


def edit_button_for(d, case_name):
    for b in d.find_elements(By.CSS_SELECTOR, '[aria-label="编辑用例"]'):
        try:
            card = b.find_element(By.XPATH, './ancestor::div[contains(@class,"rounded-xl")][1]')
            if case_name in card.text:
                return b
        except Exception:
            continue
    return None


def case_checkbox(d, case_name):
    for cb in d.find_elements(By.CSS_SELECTOR, '[role="checkbox"]'):
        al = cb.get_attribute('aria-label') or ''
        if case_name in al and al.startswith('选择'):
            return cb
    return None


def facet_open(d):
    trig = d.find_elements(By.XPATH, "//button[.//span[normalize-space(.)='标签']]")[0]
    js_click(d, trig)
    time.sleep(2)
    pops = d.find_elements(By.CSS_SELECTOR, '[data-slot="popover-content"]')
    assert pops, 'facet popover 未打开'
    return pops[0]


def facet_items(d, pop):
    btns = [b for b in pop.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip()]
    items = []
    for b in btns:
        t = (b.text or '').strip()
        if t == '清空选择':
            continue
        items.append(b)
    headers = [p.text.strip() for p in pop.find_elements(By.TAG_NAME, 'p') if (p.text or '').strip()]
    return items, headers


def select_option(d, name, max_scroll=30):
    """在已打开的 base-ui Select 中选中指定文本选项（必要时滚动 listbox）。"""
    for _ in range(max_scroll):
        opts = d.find_elements(By.CSS_SELECTOR, '[role="option"]')
        for o in opts:
            if (o.text or '').strip() == name:
                js_click(d, o)
                return True
        boxes = d.find_elements(By.CSS_SELECTOR, '[role="listbox"]')
        if not boxes:
            break
        d.execute_script(
            'const el=arguments[0]; el.scrollTop = Math.min(el.scrollTop + el.clientHeight, el.scrollHeight);',
            boxes[0])
        time.sleep(0.4)
    return False


def section(fn):
    try:
        fn()
    except Exception as e:
        import traceback
        traceback.print_exc()
        ERRORS.append(f'{fn.__name__}: {e}')
        log('  !! section error', fn.__name__, e)


def login(d):
    """清残留 OAuth/会话后登录；防其它并发任务的 OAuth 重定向留在外域。"""
    d.get(BASE + '/dashboard')
    time.sleep(1)
    try:
        d.delete_all_cookies()
        d.execute_script('localStorage.clear(); sessionStorage.clear();')
    except Exception:
        pass
    d.get(BASE + '/login')
    end = time.time() + 90
    while time.time() < end and not d.find_elements(By.ID, 'username'):
        if '/login' not in d.current_url:
            log('  !! 登录页被重定向', d.current_url[:120])
            d.get(BASE + '/login')
        time.sleep(1)
    if d.find_elements(By.ID, 'username'):
        d.find_element(By.ID, 'username').send_keys('接线测试_admin')
        d.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
        for b in d.find_elements(By.TAG_NAME, 'button'):
            if '登' in b.text and '录' in b.text:
                js_click(d, b)
                break
    end = time.time() + 90
    while time.time() < end and '/login' in d.current_url:
        time.sleep(1)
    if 'localhost:15173' not in d.current_url:
        log('  !! 登录后仍在外部域，回站内', d.current_url[:120])
        d.get(BASE + '/dashboard')
        time.sleep(3)
    log('  登录后', d.current_url[:120])


d = driver()
try:
    step('T0 环境核对')
    import urllib.request
    with urllib.request.urlopen('http://127.0.0.1:15000/health', timeout=15) as r:
        h = json.loads(r.read().decode())
    log('  health', h)
    with urllib.request.urlopen(BASE + '/', timeout=15) as r:
        html = r.read().decode('utf-8', 'replace')
    log('  lib-react', (re.search(r'lib-react[^"]*', html) or ['?'])[0])

    step('T1 登录 + 幂等造数')
    login(d)

    cats = call(d, 'GET', '/tags/categories?page=1&per_page=100').get('items', [])
    cat = next((c for c in cats if c['name'] == CAT), None)
    if not cat:
        cat = call(d, 'POST', '/tags/categories',
                   {'name': CAT, 'description': 'INT1487 用例页测试分类', 'color': '#8b5cf6', 'sort_order': 9})
    cat_id = cat['id']
    tags = call(d, 'GET', '/tags?page=1&per_page=100').get('items', [])
    by_name = {t['name']: t for t in tags}
    for nm, col, desc in ((TAG_X, '#f97316', 'INT1487 标签X'), (TAG_Y, '#06b6d4', 'INT1487 标签Y')):
        if nm not in by_name:
            call(d, 'POST', '/tags', {'name': nm, 'description': desc, 'color': col, 'category_id': cat_id})
    tags = call(d, 'GET', '/tags?page=1&per_page=100').get('items', [])
    log('  标签注册表共', len(tags), {k: next((t['id'] for t in tags if t['name'] == k), None) for k in (TAG_X, TAG_Y)})
    gs = call(d, 'GET', '/groups?page=1&per_page=200').get('items', [])
    grp = next((g for g in gs if g['name'] == GRP), None)
    if not grp:
        grp = call(d, 'POST', '/groups', {'name': GRP, 'description': 'INT1487 测试分组', 'algorithm_type': ''})
    gid = grp['id']
    cases = call(d, 'GET', f'/testcases?page=1&per_page=100&group_id={gid}').get('items', [])
    have = {c['name']: c for c in cases}
    for nm in (CASE1, CASE2):
        if nm not in have:
            call(d, 'POST', '/testcases', {'name': nm, 'description': 'INT1487 描述', 'group_id': gid, 'tags': []})
    cases = call(d, 'GET', f'/testcases?page=1&per_page=100&group_id={gid}').get('items', [])
    id_by_name = {c['name']: str(c['id']) for c in cases}
    id1, id2 = id_by_name.get(CASE1), id_by_name.get(CASE2)
    assert id1 and id2, '造数失败'
    log('  用例', id_by_name)

    def group_cases():
        return call(d, 'GET', f'/testcases?page=1&per_page=100&group_id={gid}').get('items', [])

    # ---------- T2 facet ----------
    def t2():
        step('T2 facet：选项条数 / 分类分组 / facet 搜索 / 选项计数')
        load_cases_page(d)
        pop = facet_open(d)
        items, headers = facet_items(d, pop)
        log('  facet 选项数', len(items), 'API 标签数', len(tags))
        log('  分类组头含测试分类', any(CAT in x for x in headers), '组头样例', headers[:4])
        shot(d, '30_facet_light_open')
        # facet 内搜索
        q = pop.find_element(By.CSS_SELECTOR, 'input[aria-label="搜索标签"]')
        q.click()
        q.send_keys(P)
        time.sleep(1.2)
        items2, headers2 = facet_items(d, pop)
        log('  facet 搜索后选项', [(b.text or '').strip() for b in items2], '组头', headers2)
        shot(d, '31_facet_light_search')
        q.send_keys(Keys.CONTROL, 'a')
        q.send_keys(Keys.DELETE)
        time.sleep(1)
        d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(1)
    section(t2)

    # ---------- T3 抽屉打标签 ----------
    def t3():
        step('T3 编辑抽屉打标签（回车 / 建议点击 / 逗号 / 移除）→ 保存 → 回读')
        load_cases_page(d)
        ok_expand = expand_group(d, GRP)
        log('  分组展开/用例卡就绪', ok_expand, '用例1可见', visible(d, CASE1), '用例2可见', visible(d, CASE2))
        shot(d, '32a_case_list_light')
        assert ok_expand and visible(d, CASE1), '用例1 用例卡不可见'
        btn = edit_button_for(d, CASE1)
        assert btn is not None, '未找到用例1 编辑钮'
        js_click(d, btn)
        dlg = wait_dialog(d, '编辑测试用例')
        time.sleep(1.2)
        shot(d, '32_drawer_light_empty_tags')
        tag_in = None
        for i in dlg.find_elements(By.TAG_NAME, 'input'):
            if '回车或逗号' in (i.get_attribute('placeholder') or ''):
                tag_in = i
                break
        assert tag_in is not None, '抽屉标签输入框缺失'
        # 空草稿时建议区（已有标签）出现
        sugg = [b.text.strip() for b in dlg.find_elements(By.TAG_NAME, 'button')
                if '分类' in (b.text or '')]
        log('  空草稿建议区按钮(截8)条数', len(sugg), sugg[:8])
        # 回车添加 X
        tag_in.send_keys(TAG_X)
        tag_in.send_keys(Keys.ENTER)
        time.sleep(0.8)
        log('  回车后 chips', [b.text.replace('✕', '').strip() for b in dlg.find_elements(By.CSS_SELECTOR, '[data-slot="badge"]')])
        # 建议点击添加 Y：输入前缀，点建议按钮
        tag_in.send_keys(P + '标签Y')
        time.sleep(1)
        cand = [b for b in dlg.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip().startswith(TAG_Y)]
        log('  前缀建议命中', [b.text.strip() for b in cand])
        if cand:
            js_click(d, cand[0])
            time.sleep(0.8)
        log('  建议点击后 chips', [b.text.replace('✕', '').strip() for b in dlg.find_elements(By.CSS_SELECTOR, '[data-slot="badge"]')])
        # chip ✕ 移除 Y
        rm = dlg.find_elements(By.CSS_SELECTOR, f'[aria-label="移除标签 {TAG_Y}"]')
        if rm:
            js_click(d, rm[0])
            time.sleep(0.8)
        log('  移除Y后 chips', [b.text.replace('✕', '').strip() for b in dlg.find_elements(By.CSS_SELECTOR, '[data-slot="badge"]')])
        # 逗号添加 Y 再移除，最终只留 X
        tag_in.send_keys(TAG_Y)
        tag_in.send_keys(',')
        time.sleep(0.8)
        log('  逗号添加Y后 chips', [b.text.replace('✕', '').strip() for b in dlg.find_elements(By.CSS_SELECTOR, '[data-slot="badge"]')])
        rm = dlg.find_elements(By.CSS_SELECTOR, f'[aria-label="移除标签 {TAG_Y}"]')
        if rm:
            js_click(d, rm[0])
            time.sleep(0.8)
        log('  最终 chips', [b.text.replace('✕', '').strip() for b in dlg.find_elements(By.CSS_SELECTOR, '[data-slot="badge"]')])
        shot(d, '33_drawer_light_tag_chip')
        save = None
        for b in dlg.find_elements(By.TAG_NAME, 'button'):
            if (b.text or '').strip() in ('保存', '确定', '保存修改'):
                save = b
                break
        assert save is not None, '抽屉保存钮缺失'
        log('  保存钮', save.text)
        drain(d)
        js_click(d, save)
        st, rows = collect_until(d, '/testcases/')
        log('  保存响应状态', st, 'toast', toasts(d))
        show_net([n for n in rows if n[0] == 'REQ' and n[1] in ('PUT', 'POST', 'PATCH')], only_writes=True)
        rec = group_cases()
        log('  回读用例', [(c['name'], c['tags']) for c in rec])
        assert any(c['name'] == CASE1 and c['tags'] == [TAG_X] for c in rec), '抽屉保存回读不符'
        shot(d, '34_case_card_tag_light')
    section(t3)

    # ---------- T4 facet 过滤与取消 ----------
    def t4():
        step('T4 facet 选中过滤（计数/请求/列表）→ 再点取消')
        load_cases_page(d)
        pop = facet_open(d)
        items, _ = facet_items(d, pop)
        xb = [b for b in items if (b.text or '').strip().startswith(TAG_X)]
        assert xb, 'facet 无标签X'
        log('  facet 标签X项文本(含计数)', (xb[0].text or '').strip())
        drain(d)
        js_click(d, xb[0])
        st, rows = collect_until(d, 'tag=')
        log('  过滤请求响应', st)
        show_net([n for n in rows if n[0] == 'REQ' and '/testcases' in n[2]])
        trig_txt = d.find_elements(By.XPATH, "//button[.//span[normalize-space(.)='标签']]")[0].text
        log('  触发器回显', trig_txt.replace('\n', ' '))
        if not visible(d, CASE1):
            expand_group(d, GRP)
        body = d.find_element(By.TAG_NAME, 'body').text
        log('  过滤后 用例1可见', CASE1 in body, '用例2可见', CASE2 in body)
        shot(d, '35_facet_filtered_light')
        # 再点同标签取消
        pop = facet_open(d)
        items, _ = facet_items(d, pop)
        xb = [b for b in items if (b.text or '').strip().startswith(TAG_X)]
        drain(d)
        js_click(d, xb[0])
        st2, _ = collect_until(d, 'algorithm_type')
        log('  取消筛选响应', st2)
        trig_txt = d.find_elements(By.XPATH, "//button[.//span[normalize-space(.)='标签']]")[0].text
        log('  取消后触发器回显', trig_txt.replace('\n', ' '))
        if not visible(d, CASE1):
            expand_group(d, GRP)
        body = d.find_element(By.TAG_NAME, 'body').text
        log('  取消后 用例1可见', CASE1 in body, '用例2可见', CASE2 in body)
    section(t4)

    # ---------- T5 批量管理标签 ----------
    def t5():
        step('T5 批量管理标签：加 Y / 移 Y / 改名 X→X改 / 同名校验')
        load_cases_page(d)
        search_cases(d, P, 8)
        if not visible(d, CASE1):
            expand_group(d, GRP)
        # 勾选两个用例
        for nm in (CASE1, CASE2):
            cb = case_checkbox(d, nm)
            assert cb is not None, f'无 {nm} 勾选框'
            js_click(d, cb)
            time.sleep(0.6)
        bar = d.find_elements(By.XPATH, "//button[contains(., '批量管理标签')]")
        assert bar, '批量管理标签入口缺失'
        log('  批量浮条可见，选中数', [x for x in d.find_element(By.TAG_NAME, 'body').text.splitlines() if '个用例已选择' in x])
        drain(d)
        js_click(d, bar[0])
        dlg = wait_dialog(d, '批量管理标签')
        time.sleep(1)
        radios = dlg.find_elements(By.CSS_SELECTOR, 'input[name="batch-tag-mode"]')
        log('  模式数', len(radios), '默认add选中', radios[0].is_selected())
        log('  说明', [ln for ln in dlg.text.splitlines() if '勾选' in ln])
        shot(d, '36_batch_tags_light_add')
        tin = [i for i in dlg.find_elements(By.TAG_NAME, 'input') if '回车或逗号' in (i.get_attribute('placeholder') or '')][0]
        tin.send_keys(TAG_Y)
        tin.send_keys(Keys.ENTER)
        time.sleep(0.6)
        log('  chips', [b.text.replace('✕', '').strip() for b in dlg.find_elements(By.CSS_SELECTOR, '[data-slot="badge"]')])
        ok = [b for b in dlg.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() == '确定'][0]
        drain(d)
        js_click(d, ok)
        st, rows = collect_until(d, '/testcases/batch')
        log('  批量加标签响应', st, 'toast', toasts(d))
        show_net([n for n in rows if n[0] == 'REQ' and '/testcases/batch' in n[2]], only_writes=True)
        rec = group_cases()
        log('  回读(加Y)', [(c['name'], c['tags']) for c in rec])
        shot(d, '37_batch_tags_after_add_light')

        # 移除 Y
        load_cases_page(d)
        search_cases(d, P, 8)
        if not visible(d, CASE1):
            expand_group(d, GRP)
        for nm in (CASE1, CASE2):
            cb = case_checkbox(d, nm)
            if cb:
                js_click(d, cb)
                time.sleep(0.6)
        bar = d.find_elements(By.XPATH, "//button[contains(., '批量管理标签')]")
        drain(d)
        js_click(d, bar[0])
        dlg = wait_dialog(d, '批量管理标签')
        time.sleep(1)
        radios = dlg.find_elements(By.CSS_SELECTOR, 'input[name="batch-tag-mode"]')
        js_click(d, radios[1])
        time.sleep(0.6)
        tin = [i for i in dlg.find_elements(By.TAG_NAME, 'input') if '回车或逗号' in (i.get_attribute('placeholder') or '')][0]
        tin.send_keys(TAG_Y)
        tin.send_keys(Keys.ENTER)
        time.sleep(0.6)
        ok = [b for b in dlg.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() == '确定'][0]
        drain(d)
        js_click(d, ok)
        st, rows = collect_until(d, '/testcases/batch')
        log('  批量移除标签响应', st, 'toast', toasts(d))
        show_net([n for n in rows if n[0] == 'REQ' and '/testcases/batch' in n[2]], only_writes=True)
        rec = group_cases()
        log('  回读(移Y)', [(c['name'], c['tags']) for c in rec])

        # 改名 X → X改
        load_cases_page(d)
        search_cases(d, P, 8)
        if not visible(d, CASE1):
            expand_group(d, GRP)
        cb = case_checkbox(d, CASE1)
        if cb:
            js_click(d, cb)
            time.sleep(0.8)
        bar = d.find_elements(By.XPATH, "//button[contains(., '批量管理标签')]")
        js_click(d, bar[0])
        dlg = wait_dialog(d, '批量管理标签')
        time.sleep(1)
        radios = dlg.find_elements(By.CSS_SELECTOR, 'input[name="batch-tag-mode"]')
        js_click(d, radios[2])
        time.sleep(0.8)
        log('  rename 模式说明', [ln for ln in dlg.text.splitlines() if '修改' in ln or '原标签' in ln or '新标签' in ln])
        shot(d, '38_batch_tags_light_rename')
        trig = dlg.find_elements(By.CSS_SELECTOR, '[role="combobox"]')
        log('  rename Select 数', len(trig))
        js_click(d, trig[0])
        time.sleep(1)
        opts = d.find_elements(By.CSS_SELECTOR, '[role="option"]')
        log('  rename 选项数', len(opts))
        if not select_option(d, TAG_X):
            raise AssertionError('rename 下拉未找到标签X')
        time.sleep(0.8)
        rin = [i for i in dlg.find_elements(By.TAG_NAME, 'input') if '新标签名称' in (i.get_attribute('placeholder') or '')][0]
        rin.send_keys(TAG_X2)
        time.sleep(0.6)
        ok = [b for b in dlg.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() == '确定'][0]
        log('  改名 确定 disabled', ok.get_attribute('disabled'))
        drain(d)
        js_click(d, ok)
        st, rows = collect_until(d, '/testcases/batch')
        log('  改名响应', st, 'toast', toasts(d))
        show_net([n for n in rows if n[0] == 'REQ' and '/testcases/batch' in n[2]], only_writes=True)
        rec = group_cases()
        log('  回读(改名后)', [(c['name'], c['tags']) for c in rec])
        names = []
        for _ in range(15):
            names = [t['name'] for t in call(d, 'GET', '/tags?page=1&per_page=100').get('items', [])
                     if t['name'].startswith(P)]
            if TAG_X2 in names:
                break
            time.sleep(1.5)
        log('  改名后注册表轮询', names, '| 改名生效', TAG_X2 in names)
        same_name_old = TAG_X2 if TAG_X2 in names else TAG_X

        # 同名改名（V9.7.10 isValid 要求 old !== new）
        load_cases_page(d)
        search_cases(d, P, 8)
        if not visible(d, CASE1):
            expand_group(d, GRP)
        cb = case_checkbox(d, CASE1)
        if cb:
            js_click(d, cb)
            time.sleep(0.8)
        bar = d.find_elements(By.XPATH, "//button[contains(., '批量管理标签')]")
        js_click(d, bar[0])
        dlg = wait_dialog(d, '批量管理标签')
        time.sleep(1)
        radios = dlg.find_elements(By.CSS_SELECTOR, 'input[name="batch-tag-mode"]')
        js_click(d, radios[2])
        time.sleep(0.6)
        trig = dlg.find_elements(By.CSS_SELECTOR, '[role="combobox"]')
        js_click(d, trig[0])
        time.sleep(1)
        if not select_option(d, same_name_old):
            raise AssertionError(f'同名用例：下拉未找到 {same_name_old}')
        rin = [i for i in dlg.find_elements(By.TAG_NAME, 'input') if '新标签名称' in (i.get_attribute('placeholder') or '')][0]
        rin.send_keys(same_name_old)
        time.sleep(0.8)
        ok = [b for b in dlg.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() == '确定'][0]
        log('  同名改名 确定 disabled（V9.7.10 期望 True）', ok.get_attribute('disabled'))
        shot(d, '39_batch_tags_same_name_light')
        drain(d)
        js_click(d, ok)
        st, rows = collect_until(d, '/testcases/batch')
        log('  同名改名响应', st, 'toast', toasts(d))
        show_net([n for n in rows if n[0] == 'REQ' and '/testcases/batch' in n[2]], only_writes=True)
        log('  同名提交后弹窗仍开', bool([x for x in dialogs(d) if '批量管理标签' in (x.text or '')]))
        tags_now = call(d, 'GET', '/tags?page=1&per_page=100').get('items', [])
        log('  同名提交后注册表', [t['name'] for t in tags_now if t['name'].startswith(P)])
        close_top(d)
        time.sleep(1)
    section(t5)

    # ---------- T6 深色 ----------
    def t6():
        step('T6 深色截图：facet / 抽屉 / 批量弹窗')
        theme(d, 'dark')
        pop = facet_open(d)
        time.sleep(1)
        shot(d, '41_facet_dark')
        d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(1)
        expand_group(d, GRP)
        btn = edit_button_for(d, CASE1)
        if btn:
            js_click(d, btn)
            wait_dialog(d, '编辑测试用例')
            time.sleep(1.2)
            shot(d, '42_drawer_dark')
            close_top(d)
            time.sleep(1)
        else:
            log('  !! 深色：未找到编辑钮')
        cb = case_checkbox(d, CASE1)
        if cb:
            js_click(d, cb)
            time.sleep(1)
            bar = d.find_elements(By.XPATH, "//button[contains(., '批量管理标签')]")
            if bar:
                js_click(d, bar[0])
                wait_dialog(d, '批量管理标签')
                time.sleep(1)
                tin = [i for i in dialogs(d)[-1].find_elements(By.TAG_NAME, 'input')
                       if '回车或逗号' in (i.get_attribute('placeholder') or '')]
                if tin:
                    tin[0].send_keys(TAG_Y)
                    tin[0].send_keys(Keys.ENTER)
                    time.sleep(0.6)
                shot(d, '43_batch_tags_dark')
                close_top(d)
                time.sleep(1)
        else:
            log('  !! 深色：未找到用例勾选框')
        theme(d, 'light')
    section(t6)
    errs_before = len(ERRORS)

    # ---------- T7 清理 ----------
    def t7():
        step('T7 清理与残留校验')
        cur = group_cases()
        ids = [str(c['id']) for c in cur]
        for cid in ids:
            r = api(d, 'DELETE', f'/testcases/{cid}')
            log('  软删', cid, r['status'])
            time.sleep(0.5)
        if ids:
            r = api(d, 'POST', '/testcases/purge', {'ids': ids})
            log('  purge', r['status'], r['body'][:100])
        r = api(d, 'DELETE', f'/groups/{gid}?cascade=true')
        log('  删分组', r['status'], r['body'][:80])
        for t in call(d, 'GET', '/tags?page=1&per_page=100').get('items', []):
            if t['name'].startswith(P):
                rr = api(d, 'DELETE', f"/tags/{t['id']}?cascade=false")
                log('  删标签', t['name'], rr['status'])
                time.sleep(0.5)
        for c in call(d, 'GET', '/tags/categories?page=1&per_page=100').get('items', []):
            if c['name'].startswith(P):
                rr = api(d, 'DELETE', f"/tags/categories/{c['id']}")
                log('  删分类', c['name'], rr['status'])
                time.sleep(0.5)
        left_t = [t['name'] for t in call(d, 'GET', '/tags?page=1&per_page=100').get('items', []) if t['name'].startswith(P)]
        left_c = [c['name'] for c in call(d, 'GET', '/tags/categories?page=1&per_page=100').get('items', []) if c['name'].startswith(P)]
        left_g = [g['name'] for g in call(d, 'GET', '/groups?page=1&per_page=200').get('items', []) if g['name'].startswith(P)]
        log('  残留标签/分类/分组', left_t, left_c, left_g)
        assert not left_t and not left_c and not left_g, '清理不彻底'
    section(t7)

    log('\nERRORS:', ERRORS)
finally:
    try:
        d.quit()
    except Exception:
        pass
