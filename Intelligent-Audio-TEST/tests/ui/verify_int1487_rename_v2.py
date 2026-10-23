# -*- coding: utf-8 -*-
"""INT-1487 补充实测：批量改名成功路径 + 同名校验（唯一名字，避开软删同名复用）。"""
import json
import os
import sys
import time
import winreg

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

BASE = 'http://localhost:15173'
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1487_tags')
os.makedirs(ART, exist_ok=True)
SUF = time.strftime('%H%M%S')
P = '接线测试_INT1487R' + SUF
CAT = P + '分类'
TAG_X = P + '标签X'
TAG_NEW = P + '标签改'
GRP = P + '分组'
CASE1 = P + '用例1'


def log(*a):
    print(*a, flush=True)


def driver():
    o = Options()
    o.binary_location = CHROME
    for a in ('--headless=new', '--window-size=1680,1050', '--disable-gpu', '--no-sandbox',
              '--lang=zh-CN', '--disable-dev-shm-usage', '--disable-extensions', '--no-proxy-server'):
        o.add_argument(a)
    o.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    best, bestv = '', ()
    for v in (os.listdir(cache) if os.path.isdir(cache) else []):
        e = os.path.join(cache, v, 'chromedriver.exe')
        if os.path.isfile(e):
            try:
                vv = tuple(int(x) for x in v.split('.') if x.isdigit())
            except ValueError:
                continue
            if vv > bestv:
                bestv, best = vv, e
    d = webdriver.Chrome(options=o, service=Service(best) if best else Service())
    d.set_page_load_timeout(120)
    return d


def api(d, method, path, body=None):
    script = """
    const [method, path, body] = arguments;
    const cb = arguments[arguments.length - 1];
    const token = localStorage.getItem('iatp:auth:token:v1');
    const opt = {method, headers: {'Accept': 'application/json'}, credentials: 'include'};
    if (token) opt.headers.Authorization = 'Bearer ' + token;
    if (body) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
    fetch('/api/v1' + path, opt).then(async r => { const t = await r.text(); cb({status: r.status, body: t}); })
      .catch(e => cb({status: -1, body: String(e)}));
    """
    d.set_script_timeout(180)
    res = d.execute_async_script(script, method, path, body)
    try:
        res['json'] = json.loads(res['body'])
    except Exception:
        res['json'] = None
    return res


def dat(r):
    return (r.get('json') or {}).get('data')


def call(d, m, p, b=None):
    r = api(d, m, p, b)
    assert r['status'] and 200 <= r['status'] < 300, f'{m} {p} {r["status"]} {r["body"][:200]}'
    return dat(r)


def js_click(d, el):
    d.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)
    time.sleep(0.3)


def shot(d, name):
    d.save_screenshot(os.path.join(ART, name + '.png'))
    log('  shot', name)


def toasts(d):
    return [(t.text or '').strip().replace('\n', ' / ') for t in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]') if (t.text or '').strip()]


def login(d):
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
        d.get(BASE + '/dashboard')
        time.sleep(3)
    log('  登录后', d.current_url[:100])


def load_more(d):
    more = [b for b in d.find_elements(By.TAG_NAME, 'button') if '加载更多' in (b.text or '')]
    if more:
        js_click(d, more[0])
        time.sleep(1.5)
        return True
    return False


def ensure_group(d, name, timeout=100):
    end = time.time() + timeout
    last = 0
    while time.time() < end:
        if d.find_elements(By.XPATH, f"//span[normalize-space(.)='{name}']"):
            return True
        if time.time() - last > 1.5:
            load_more(d)
            last = time.time()
        time.sleep(0.8)
    return False


def expand_group(d, name, timeout=75):
    end = time.time() + timeout
    while time.time() < end:
        if d.find_elements(By.CSS_SELECTOR, f'[aria-label="选择 {CASE1}"]'):
            return True
        if ensure_group(d, name, timeout=12):
            for sp in d.find_elements(By.XPATH, f"//span[normalize-space(.)='{name}']"):
                try:
                    js_click(d, sp)
                    break
                except Exception:
                    pass
        time.sleep(6)
    return False


def select_option(d, name, max_scroll=40):
    for _ in range(max_scroll):
        for o in d.find_elements(By.CSS_SELECTOR, '[role="option"]'):
            if (o.text or '').strip() == name:
                js_click(d, o)
                return True
        boxes = d.find_elements(By.CSS_SELECTOR, '[role="listbox"]')
        if not boxes:
            break
        d.execute_script('const el=arguments[0]; el.scrollTop = Math.min(el.scrollTop + el.clientHeight, el.scrollHeight);', boxes[0])
        time.sleep(0.4)
    return False


def open_batch(d, case_name):
    cb = d.find_elements(By.CSS_SELECTOR, f'[aria-label="选择 {case_name}"]')
    assert cb, '无用例勾选框'
    js_click(d, cb[0])
    time.sleep(0.8)
    bar = d.find_elements(By.XPATH, "//button[contains(., '批量管理标签')]")
    assert bar, '无批量管理标签入口'
    js_click(d, bar[0])
    end = time.time() + 25
    while time.time() < end:
        for el in d.find_elements(By.CSS_SELECTOR, '[role="dialog"]'):
            if '批量管理标签' in (el.text or ''):
                return el
        time.sleep(0.4)
    raise AssertionError('批量管理标签弹窗未出现')


def collect_until(d, url_substr, timeout=100):
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


d = driver()
gid = None
try:
    d.get(BASE + '/login')
    login(d)
    cats = call(d, 'GET', '/tags/categories?page=1&per_page=100').get('items', [])
    cat = next((c for c in cats if c['name'] == CAT), None) or call(
        d, 'POST', '/tags/categories', {'name': CAT, 'description': 'd', 'color': '#8b5cf6', 'sort_order': 9})
    tagx = call(d, 'POST', '/tags', {'name': TAG_X, 'description': 'd', 'color': '#f97316', 'category_id': cat['id']})
    grp = call(d, 'POST', '/groups', {'name': GRP, 'description': 'd', 'algorithm_type': ''})
    gid = grp['id']
    case = call(d, 'POST', '/testcases', {'name': CASE1, 'description': 'd', 'group_id': gid, 'tags': [TAG_X]})
    log('造数', {'tag': tagx['id'], 'group': gid, 'case': case['id']})

    d.get(BASE + '/testcases/by-group')
    end = time.time() + 90
    while time.time() < end and not d.find_elements(By.CSS_SELECTOR, '[aria-label^="全选分组"]'):
        time.sleep(1)
    assert expand_group(d, GRP), '分组/用例卡未就绪'
    log('分组已展开')

    dlg = open_batch(d, CASE1)
    radios = dlg.find_elements(By.CSS_SELECTOR, 'input[name="batch-tag-mode"]')
    js_click(d, radios[2])
    time.sleep(0.8)
    trig = dlg.find_elements(By.CSS_SELECTOR, '[role="combobox"]')
    js_click(d, trig[0])
    time.sleep(1)
    log('rename 选项数', len(d.find_elements(By.CSS_SELECTOR, '[role="option"]')))
    assert select_option(d, TAG_X), '未选中原标签X'
    rin = [i for i in dlg.find_elements(By.TAG_NAME, 'input') if '新标签名称' in (i.get_attribute('placeholder') or '')][0]
    rin.send_keys(TAG_NEW)
    time.sleep(0.5)
    ok = [b for b in dlg.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() == '确定'][0]
    log('改名 确定 disabled', ok.get_attribute('disabled'))
    shot(d, '44_batch_rename_light')
    d.get_log('performance')
    js_click(d, ok)
    st, rows = collect_until(d, '/testcases/batch')
    log('改名响应', st, 'toast', toasts(d))
    for t, a, u, b in rows:
        if t == 'REQ' and '/testcases/batch' in u:
            log('  NET', a, u.split('15173')[-1], 'body=', b)
    names = []
    for _ in range(12):
        names = [t['name'] for t in call(d, 'GET', '/tags?page=1&per_page=100').get('items', []) if t['name'].startswith(P)]
        if TAG_NEW in names:
            break
        time.sleep(1.5)
    log('改名后注册表', names)
    cs = call(d, 'GET', f'/testcases?page=1&per_page=100&group_id={gid}').get('items', [])
    log('改名后用例标签', [(c['name'], c['tags']) for c in cs])

    # facet 回读改名后标签与计数
    if not d.find_elements(By.CSS_SELECTOR, '[aria-label^="全选分组"]'):
        d.get(BASE + '/testcases/by-group')
        end = time.time() + 90
        while time.time() < end and not d.find_elements(By.CSS_SELECTOR, '[aria-label^="全选分组"]'):
            time.sleep(1)
    trig_f = d.find_elements(By.XPATH, "//button[.//span[normalize-space(.)='标签']]")[0]
    js_click(d, trig_f)
    time.sleep(2)
    pops = d.find_elements(By.CSS_SELECTOR, '[data-slot="popover-content"]')
    btns = [b for b in pops[0].find_elements(By.TAG_NAME, 'button') if (b.text or '').strip()]
    hit = [b for b in btns if TAG_NEW in (b.text or '')]
    log('facet 改名后标签项', [(b.text or '').strip().replace('\n', ' ') for b in hit])
    shot(d, '45_facet_after_rename_light')
    d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(1)

    # 同名改名（前后端校验）
    dlg = open_batch(d, CASE1)
    radios = dlg.find_elements(By.CSS_SELECTOR, 'input[name="batch-tag-mode"]')
    js_click(d, radios[2])
    time.sleep(0.8)
    trig = dlg.find_elements(By.CSS_SELECTOR, '[role="combobox"]')
    js_click(d, trig[0])
    time.sleep(1)
    assert select_option(d, TAG_NEW), '未选中改名后标签'
    rin = [i for i in dlg.find_elements(By.TAG_NAME, 'input') if '新标签名称' in (i.get_attribute('placeholder') or '')][0]
    rin.send_keys(TAG_NEW)
    time.sleep(0.8)
    ok = [b for b in dlg.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() == '确定'][0]
    log('同名改名 确定 disabled（V9.7.10 期望 True）', ok.get_attribute('disabled'))
    shot(d, '46_batch_same_name_light')
    d.get_log('performance')
    js_click(d, ok)
    st, rows = collect_until(d, '/testcases/batch')
    log('同名改名响应', st, 'toast', toasts(d))
    log('同名提交后弹窗仍开', bool([el for el in d.find_elements(By.CSS_SELECTOR, '[role="dialog"]') if '批量管理标签' in (el.text or '')]))
finally:
    try:
        if gid:
            cs = call(d, 'GET', f'/testcases?page=1&per_page=100&group_id={gid}').get('items', [])
            ids = [str(c['id']) for c in cs]
            for cid in ids:
                api(d, 'DELETE', f'/testcases/{cid}')
            if ids:
                api(d, 'POST', '/testcases/purge', {'ids': ids})
            api(d, 'DELETE', f'/groups/{gid}?cascade=true')
        for t in call(d, 'GET', '/tags?page=1&per_page=100').get('items', []):
            if t['name'].startswith(P):
                api(d, 'DELETE', f"/tags/{t['id']}?cascade=false")
        for c in call(d, 'GET', '/tags/categories?page=1&per_page=100').get('items', []):
            if c['name'].startswith(P):
                api(d, 'DELETE', f"/tags/categories/{c['id']}")
        left = [t['name'] for t in call(d, 'GET', '/tags?page=1&per_page=100').get('items', []) if t['name'].startswith(P)]
        log('残留', left)
    except Exception as e:
        log('清理异常', e)
    try:
        d.quit()
    except Exception:
        pass
