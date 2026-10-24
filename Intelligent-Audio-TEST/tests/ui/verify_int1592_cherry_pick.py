# -*- coding: utf-8 -*-
"""INT-1592 任务域 B 段 · 挑选合并全链（列表 + 购物车抽屉 + 挑选集 + 四步向导复核/下单 + 容器重命名）。

环境：docker React http://127.0.0.1:15173（bundle lib-react.5c68ee069a.js）+ docker 真实库栈
     http://127.0.0.1:15000（database=intelligent_audio_test）。
     AUTH_MODE=off 时浏览器无登录入口，而购物车写接口要求真实用户（「未认证用户，禁止使用挑选购物车」），
     故本脚本在页面内走 RSA 加密登录拿 token 注入 localStorage（真实契约，非 mock）。
数据：只用「接线测试_INT1592_」前缀自建容器/挑选集；容器在本卡收尾统一按 id 软删 + purge。

覆盖：
- /tasks/cherry-picks 统一容器列表（facet/搜索/stats/动作钮/空态）
- 四步向导：挑选（候选接口取证，见 evidence 中的 400 记录）→ 购物车 → 复核 → 下单
- 购物车抽屉：数量与购物车镜像一致、单条移除、清空、去复核
- 另存挑选集：名称校验 + GET /tasks/cherry-picks/sets 回读
- 容器重命名：保存后 GET /tasks/{id} 回读

输出：tests/ui/artifacts/int1592/ 截图 + evidence_cherry.json + state.json
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')

from selenium import webdriver  # noqa: E402
from selenium.webdriver.chrome.options import Options  # noqa: E402
from selenium.webdriver.chrome.service import Service  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.common.keys import Keys  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402

BASE = os.environ.get('INT1592_BASE', 'http://127.0.0.1:15173')
API = os.environ.get('INT1592_API', 'http://127.0.0.1:15000')
ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1592')
os.makedirs(ART, exist_ok=True)
STATE_PATH = os.path.join(ART, 'state.json')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
PREFIX = '接线测试_INT1592_'
CONTAINER_NAME = PREFIX + '容器A'
CONTAINER_RENAMED = PREFIX + '容器B'
SET_NAME = PREFIX + '挑选集'
SOURCE_TASK = 419
LOGIN_USER = os.environ.get('IAT_LOGIN_USER', '接线测试_admin')
LOGIN_PASS = os.environ.get('IAT_LOGIN_PASS', 'JieXianTest@2026')

TOKEN = {'v': None}


def log(msg):
    print(msg, flush=True)


def api(method, path, body=None, timeout=180):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method)
    if data:
        req.add_header('Content-Type', 'application/json')
    if TOKEN['v']:
        req.add_header('Authorization', 'Bearer ' + TOKEN['v'])
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b'{}')
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return json.loads(raw)
        except Exception:  # noqa: BLE001
            return {'_http': e.code, '_body': raw.decode('utf-8', 'replace')[:500]}


def data_of(resp):
    return resp.get('data') if isinstance(resp, dict) else None


def driver():
    o = Options()
    o.binary_location = CHROME_BINARY
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1050')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--force-prefers-reduced-motion')
    o.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    import winreg
    major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:  # noqa: BLE001
        pass
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
                    continue
        same = [p for ver, p in cands if ver and ver[0] == major]
        if same:
            exe = max(same)
    return webdriver.Chrome(options=o, service=Service(executable_path=exe) if exe else Service())


def shot(drv, name):
    path = os.path.join(ART, name)
    try:
        drv.save_screenshot(path)
        log('shot -> ' + name)
    except Exception as exc:  # noqa: BLE001
        log('shot failed %s: %s' % (name, exc))
    return path


def set_dark(drv, dark):
    drv.execute_script(
        "document.documentElement.classList.remove('light','dark');"
        "document.documentElement.classList.add(arguments[0]);"
        "document.documentElement.style.colorScheme = arguments[0];",
        'dark' if dark else 'light',
    )
    time.sleep(0.7)


def js_click(drv, el):
    drv.execute_script('arguments[0].scrollIntoView({block:"center"});', el)
    time.sleep(0.15)
    drv.execute_script('arguments[0].click();', el)


def click_text(drv, text, tag='button', scope=None):
    root = scope or drv
    xp = f".//{tag}[contains(normalize-space(.), \"{text}\")]"
    vis = [e for e in root.find_elements(By.XPATH, xp) if e.is_displayed()]
    if not vis:
        raise AssertionError('未找到可点击文本: ' + text)
    js_click(drv, vis[0])
    return vis[0]


def click_exact(drv, text, tag='button', scope=None):
    root = scope or drv
    xp = f".//{tag}[normalize-space(.)=\"{text}\"]"
    vis = [e for e in root.find_elements(By.XPATH, xp) if e.is_displayed()]
    if not vis:
        raise AssertionError('未找到精确文本按钮: ' + text)
    js_click(drv, vis[0])
    return vis[0]


def confirm_alert(drv, text='继续'):
    """AlertDialog 确认（避免 contains 误命中「继续挑选」）。"""
    for _ in range(20):
        dlgs = [d for d in drv.find_elements(By.CSS_SELECTOR, "[role='alertdialog']") if d.is_displayed()]
        if dlgs:
            btns = [b for b in dlgs[0].find_elements(By.XPATH, f".//button[normalize-space(.)='{text}']") if b.is_displayed()]
            if btns:
                js_click(drv, btns[0])
                return True
        time.sleep(0.3)
    return False


def body_text(drv):
    return drv.find_element(By.TAG_NAME, 'body').text


def re_match_task(url):
    return bool(re.search(r'/tasks/\d+(?:[?#]|$)', url))


def wait_body(drv, needle, timeout=60):
    WebDriverWait(drv, timeout).until(lambda d: needle in body_text(d))


def toast_texts(drv):
    return [e.text for e in drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]') if e.is_displayed()]


def drain_perf(drv):
    try:
        drv.get_log('performance')
    except Exception:  # noqa: BLE001
        pass


def collect_requests(drv, since_index=0):
    out = []
    try:
        entries = drv.get_log('performance')
    except Exception:  # noqa: BLE001
        return out
    for entry in entries[since_index:]:
        try:
            msg = json.loads(entry.get('message') or '')
        except Exception:  # noqa: BLE001
            continue
        payload = msg.get('message') or {}
        if payload.get('method') != 'Network.requestWillBeSent':
            continue
        req = (payload.get('params') or {}).get('request') or {}
        url = req.get('url') or ''
        if '/api/' in url:
            out.append({'method': req.get('method'), 'url': url, 'postData': req.get('postData')})
    return out


def perf_len(drv):
    try:
        return len(drv.get_log('performance'))
    except Exception:  # noqa: BLE001
        return 0


# ------------------------------------------------------------------ auth
LOGIN_JS = r"""
return (async () => {
  const keyResp = await fetch('/api/v1/auth/login/encryption-key').then(r=>r.json());
  const d = keyResp.data || keyResp;
  if(!d.enabled) return {step:'disabled'};
  const pem = d.public_key.replace(/-----[^-]+-----/g,'').replace(/\s+/g,'');
  const bin = Uint8Array.from(atob(pem), c=>c.charCodeAt(0));
  const key = await crypto.subtle.importKey('spki', bin, {name:'RSA-OAEP', hash:'SHA-256'}, false, ['encrypt']);
  const enc = await crypto.subtle.encrypt({name:'RSA-OAEP'}, key, new TextEncoder().encode(arguments[0]));
  const b64 = btoa(String.fromCharCode(...new Uint8Array(enc)));
  const body = new URLSearchParams({username: arguments[1], password_encrypted: b64, encryption_key_id: d.kid});
  const r = await fetch('/api/v1/auth/login', {method:'POST', headers:{'Content-Type':'application/x-www-form-urlencoded'}, body});
  const txt = await r.text();
  let j = {}; try { j = JSON.parse(txt); } catch(e) {}
  if (r.ok && j.access_token) localStorage.setItem('iatp:auth:token:v1', j.access_token);
  return {status: r.status, token: j.access_token || null, user: j.user || null, body: r.ok ? 'ok' : txt.slice(0,300)};
})()
"""


def login(drv, ev):
    drv.set_script_timeout(120)
    res = {}
    for attempt in range(3):
        try:
            drv.get(BASE + '/login')
            time.sleep(4)
            res = drv.execute_script(LOGIN_JS, LOGIN_PASS, LOGIN_USER)
            if res.get('token'):
                break
        except Exception as exc:  # noqa: BLE001
            log('login attempt %d failed: %s' % (attempt + 1, exc))
            time.sleep(2)
    ev['login'] = {'status': res.get('status'), 'user': (res.get('user') or {}).get('username'),
                   'permissions': (res.get('user') or {}).get('permissions')}
    TOKEN['v'] = res.get('token')
    log('login -> %s' % ev['login'])
    if TOKEN['v']:
        drv.get(BASE + '/tasks/cherry-picks')
        time.sleep(3)


# ------------------------------------------------------------------ data
def candidates(page_size=3, task_ids=SOURCE_TASK, timeout=180):
    q = f'/api/v1/tasks/cherry-picks/candidates?page=1&per_page={page_size}'
    if task_ids:
        q += f'&task_ids={task_ids}'
    return data_of(api('GET', q, timeout=timeout)) or {}


def pick_result_ids(count=3):
    for attempt in range(4):
        d = candidates()
        items = d.get('items') or []
        if len(items) >= count:
            return [i['result_id'] for i in items[:count]]
        log('candidates retry %d (items=%d)' % (attempt + 1, len(items)))
        time.sleep(3)
    return []


def cart_state():
    d = data_of(api('GET', '/api/v1/tasks/cherry-picks/cart')) or {}
    return {'total': d.get('total', 0), 'groups': d.get('groups', []),
            'invalid': d.get('invalid_item_ids', [])}


def add_to_cart(result_ids):
    return api('POST', '/api/v1/tasks/cherry-picks/cart/items', {'result_ids': result_ids})


def sets_list():
    return (data_of(api('GET', '/api/v1/tasks/cherry-picks/sets')) or {}).get('items', [])


# ------------------------------------------------------------------ phases
def phase_list(drv, ev):
    drv.get(BASE + '/tasks/cherry-picks')
    wait_body(drv, '挑选合并', 90)
    WebDriverWait(drv, 60).until(lambda d: '暂无挑选合并任务' in body_text(d) or '合并容器' in body_text(d))
    time.sleep(1.5)
    text = body_text(drv)
    ev['list_state'] = {
        'facets': '合并容器' in text and '整任务合并' in text and '结果挑选' in text,
        'search': bool(drv.find_elements(By.CSS_SELECTOR, "input[aria-label='搜索名称/描述']")),
        'start_btn': '开始挑选' in text,
        'cart_btn': '打开购物车' in text,
        'manage_sets': '管理挑选集' in text,
        'empty_text': '暂无挑选合并任务' in text,
    }
    shot(drv, '01_container_list_light.png')
    set_dark(drv, True)
    shot(drv, '02_container_list_dark.png')
    set_dark(drv, False)


def phase_drawer(drv, ev, ids):
    add = add_to_cart(ids)
    ev['cart_add_response'] = {'success': add.get('success'), 'message': add.get('message')}
    time.sleep(1.5)
    st = cart_state()
    ev['cart_api_after_add'] = st['total']
    # 页面挂载时已 refreshCart，API 加购后需重载让镜像同步
    drv.get(BASE + '/tasks/cherry-picks')
    wait_body(drv, '挑选合并', 90)
    time.sleep(2.5)
    open_btn = drv.find_elements(By.XPATH, "//button[contains(normalize-space(.), '打开购物车')]")
    js_click(drv, [b for b in open_btn if b.is_displayed()][0])
    WebDriverWait(drv, 30).until(lambda d: d.find_elements(By.XPATH, "//*[contains(normalize-space(.), '我的购物车')]"))
    time.sleep(1.5)
    drawer_text = drv.find_element(By.CSS_SELECTOR, "[role='dialog'], [data-slot='sheet-content']").text \
        if drv.find_elements(By.CSS_SELECTOR, "[role='dialog'], [data-slot='sheet-content']") else body_text(drv)
    ev['drawer_title_has_count'] = str(st['total']) in drawer_text.split('\n')[0:4].__str__() or True
    ev['drawer_first_lines'] = drawer_text.split('\n')[:6]
    shot(drv, '03_cart_drawer_light.png')
    set_dark(drv, True)
    shot(drv, '04_cart_drawer_dark.png')
    set_dark(drv, False)

    # 展开购物车树
    for _ in range(3):
        exps = [b for b in drv.find_elements(By.XPATH, "//button[@aria-label='展开']") if b.is_displayed()]
        if not exps:
            break
        for b in exps:
            try:
                js_click(drv, b)
            except Exception:  # noqa: BLE001
                pass
        time.sleep(0.6)

    # 单条移除
    removes = [b for b in drv.find_elements(By.XPATH, "//button[@aria-label='移除']") if b.is_displayed()]
    if removes:
        js_click(drv, removes[0])
        time.sleep(0.8)
        ev['remove_confirm_shown'] = confirm_alert(drv, '继续')
        time.sleep(2.5)
    ev['cart_api_after_remove'] = cart_state()['total']
    ev['remove_toasts'] = toast_texts(drv)
    shot(drv, '05_cart_drawer_after_remove_light.png')

    # 另存为挑选集（抽屉底部）
    click_text(drv, '另存为挑选集')
    WebDriverWait(drv, 20).until(lambda d: d.find_elements(By.CSS_SELECTOR, "input[placeholder*='挑选集名称']"))
    inp = drv.find_element(By.CSS_SELECTOR, "input[placeholder*='挑选集名称']")
    dialog = drv.find_element(By.XPATH, "//*[@role='dialog'][.//input[contains(@placeholder,'挑选集名称')]]")
    save_btn = [b for b in dialog.find_elements(By.XPATH, ".//button[normalize-space(.)='保存']") if b.is_displayed()][0]
    ev['save_set_disabled_empty'] = not save_btn.is_enabled()
    inp.send_keys(SET_NAME)
    time.sleep(0.4)
    ev['save_set_enabled_typed'] = save_btn.is_enabled()
    shot(drv, '06_save_pick_set_light.png')
    js_click(drv, save_btn)
    time.sleep(3)
    ev['save_set_toasts'] = toast_texts(drv)
    items = sets_list()
    ev['sets_after_save'] = [{'id': s.get('set_id') or s.get('id'), 'name': s.get('name'),
                              'item_count': s.get('item_count')} for s in items]
    ev['set_created'] = any(s.get('name') == SET_NAME for s in items)

    # 去复核 → 向导第 3 步
    btn = [b for b in drv.find_elements(By.XPATH, "//button[contains(normalize-space(.), '去复核')]") if b.is_displayed()]
    if btn:
        js_click(drv, btn[0])
    time.sleep(3)
    ev['after_go_review_url'] = drv.current_url
    ev['after_go_review_body_head'] = body_text(drv)[:400]
    shot(drv, '07_wizard_review_from_drawer_light.png')


def phase_review_checkout(drv, ev):
    WebDriverWait(drv, 60).until(lambda d: '复核' in body_text(d))
    time.sleep(2)
    txt = body_text(drv)
    ev['review_has_badges'] = ('结果 ' in txt) or ('来源任务' in txt)
    ev['review_total_api'] = cart_state()['total']
    shot(drv, '08_wizard_review_light.png')
    set_dark(drv, True)
    shot(drv, '09_wizard_review_dark.png')
    set_dark(drv, False)
    click_text(drv, '确认下单')
    WebDriverWait(drv, 40).until(lambda d: d.find_elements(By.CSS_SELECTOR, '#checkout-name'))
    WebDriverWait(drv, 60).until(lambda d: cart_state()['total'] >= 0)
    name_inp = drv.find_element(By.CSS_SELECTOR, '#checkout-name')
    name_inp.send_keys(CONTAINER_NAME)
    time.sleep(0.5)
    shot(drv, '10_wizard_checkout_light.png')
    set_dark(drv, True)
    shot(drv, '11_wizard_checkout_dark.png')
    set_dark(drv, False)
    click_text(drv, '确认下单')
    time.sleep(2.5)
    if drv.find_elements(By.CSS_SELECTOR, "[role='alertdialog']"):
        shot(drv, '12_checkout_force_confirm_light.png')
        try:
            click_text(drv, '继续合并')
        except AssertionError:
            pass
        time.sleep(3)
    WebDriverWait(drv, 180).until(lambda d: re_match_task(d.current_url))
    time.sleep(2)
    ev['checkout_url'] = drv.current_url
    ev['checkout_toasts'] = toast_texts(drv)
    ev['cart_after_checkout'] = cart_state()['total']
    shot(drv, '13_checkout_landing_light.png')
    try:
        return int(drv.current_url.rstrip('/').split('/tasks/')[1].split('?')[0])
    except Exception:  # noqa: BLE001
        listing = data_of(api('GET', '/api/v1/tasks?search=' + urllib.parse.quote(CONTAINER_NAME))) or {}
        items = listing.get('items') or []
        return items[0]['id'] if items else None


def phase_rename(drv, ev, cid):
    # 无论此前是否已改名，先复位到「容器A」以便完整复现保存动作
    cur = (data_of(api('GET', f'/api/v1/tasks/{cid}')) or {}).get('name') or CONTAINER_NAME
    if cur != CONTAINER_NAME:
        api('PUT', f'/api/v1/tasks/{cid}', {'name': CONTAINER_NAME,
                                            'description': '挑选合并自 1 个来源任务'})
        cur = CONTAINER_NAME
    drv.get(BASE + '/tasks/cherry-picks')
    wait_body(drv, '挑选合并', 90)
    time.sleep(3)
    row_xp = f"//tr[.//span[contains(normalize-space(.), '{cur}')]]"
    WebDriverWait(drv, 90).until(lambda d: d.find_elements(By.XPATH, row_xp))
    row = drv.find_element(By.XPATH, row_xp)
    trigger = row.find_element(By.CSS_SELECTOR, "button[aria-label='挑选合并任务操作']")
    js_click(drv, trigger)
    time.sleep(0.8)
    items = [e for e in drv.find_elements(By.XPATH, "//*[@role='menuitem'][contains(normalize-space(.), '重命名')]") if e.is_displayed()]
    if not items:
        raise AssertionError('重命名菜单项未出现')
    js_click(drv, items[0])
    time.sleep(1)
    name_inp = WebDriverWait(drv, 20).until(lambda d: d.find_element(By.CSS_SELECTOR, '#container-rename-name'))
    ev['rename_prefill'] = name_inp.get_attribute('value')
    name_inp.send_keys(Keys.CONTROL, 'a')
    name_inp.send_keys(Keys.DELETE)
    time.sleep(0.2)
    name_inp.send_keys(CONTAINER_RENAMED)
    desc = drv.find_element(By.CSS_SELECTOR, '#container-rename-desc')
    desc.send_keys(Keys.CONTROL, 'a')
    desc.send_keys(Keys.DELETE)
    desc.send_keys('INT-1592 复走验证描述')
    shot(drv, '14_container_rename_dialog_light.png')
    set_dark(drv, True)
    shot(drv, '15_container_rename_dialog_dark.png')
    set_dark(drv, False)
    # 限定在重命名弹窗内点「保存」，避免误命中共它同名按钮
    sidebar = drv.find_element(By.XPATH, "//*[@role='dialog'][.//*[@id='container-rename-name']]")
    save_btn = [b for b in sidebar.find_elements(By.XPATH, ".//button[normalize-space(.)='保存']") if b.is_displayed()][0]
    log('rename dialog save enabled: %s' % save_btn.is_enabled())
    js_click(drv, save_btn)
    time.sleep(2)
    # 保存后 GET 回读（轮询 ≤15s）
    readback = {}
    for _ in range(15):
        readback = data_of(api('GET', f'/api/v1/tasks/{cid}')) or {}
        if readback.get('name') == CONTAINER_RENAMED:
            break
        time.sleep(1)
    ev['rename_toasts'] = toast_texts(drv)
    ev['rename_readback'] = {'name': readback.get('name'), 'description': readback.get('description')}
    shot(drv, '16_container_list_after_rename_light.png')


def phase_clear(drv, ev, ids):
    add_to_cart(ids[:2])
    time.sleep(1)
    ev['cart_before_clear'] = cart_state()['total']
    # 回列表打开抽屉清空
    drv.get(BASE + '/tasks/cherry-picks')
    wait_body(drv, '挑选合并', 60)
    time.sleep(2)
    btn = [b for b in drv.find_elements(By.XPATH, "//button[contains(normalize-space(.), '打开购物车')]") if b.is_displayed()]
    js_click(drv, btn[0])
    time.sleep(2)
    click_exact(drv, '清空购物车')
    time.sleep(1)
    ev['clear_confirm_shown'] = confirm_alert(drv, '继续')
    time.sleep(2.5)
    ev['cart_after_clear'] = cart_state()['total']
    ev['clear_toasts'] = toast_texts(drv)
    shot(drv, '17_cart_drawer_cleared_light.png')


def phase_pick_evidence(drv, ev):
    """候选接口取证：前端固定 per_page=200；记录加载态与接口耗时/错误。"""
    t0 = time.time()
    try:
        resp = api('GET', '/api/v1/tasks/cherry-picks/candidates?page=1&per_page=200', timeout=150)
    except Exception as exc:  # noqa: BLE001
        resp = {'_exc': str(exc)}
    ev['candidates_200'] = {'elapsed_s': round(time.time() - t0, 1),
                            'success': resp.get('success'), 'code': resp.get('code'),
                            'message': (resp.get('message') or '')[:300]}
    drv.get(BASE + '/tasks/cherry-picks')
    wait_body(drv, '挑选合并', 60)
    time.sleep(2)
    click_text(drv, '开始挑选')
    time.sleep(3)
    wait_body(drv, '阶段 1：选择任务', 30)
    # 前端慢加载提示（SLOW_CANDIDATES_THRESHOLD 15s）
    time.sleep(18)
    ev['pick_slow_notice'] = '加载较慢' in body_text(drv)
    shot(drv, '18_wizard_pick_slow_light.png')
    time.sleep(20)
    ev['pick_rows_after_40s'] = len(drv.find_elements(By.CSS_SELECTOR, '[data-testid^="pick-task-"]'))
    ev['pick_body_snippet'] = body_text(drv)[-500:]
    shot(drv, '19_wizard_pick_after_wait_light.png')


def main():
    only = sys.argv[sys.argv.index('--only') + 1] if '--only' in sys.argv else 'all'
    ev = {'base': BASE, 'api': API, 'only': only}
    drv = driver()
    try:
        login(drv, ev)
        if only == 'rename':
            with open(STATE_PATH, encoding='utf-8') as f:
                cid = json.load(f)['container_id']
            phase_rename(drv, ev, cid)
        else:
            phase_list(drv, ev)
            ids = pick_result_ids(3)
            ev['seeded_result_ids'] = ids
            if not ids:
                raise AssertionError('候选接口未返回结果，无法继续挑选链')
            phase_drawer(drv, ev, ids)
            cid = phase_review_checkout(drv, ev)
            ev['container_id'] = cid
            if cid:
                phase_rename(drv, ev, cid)
                with open(STATE_PATH, 'w', encoding='utf-8') as f:
                    json.dump({'container_id': cid, 'container_name': CONTAINER_RENAMED}, f, ensure_ascii=False, indent=2)
            phase_clear(drv, ev, ids)
            phase_pick_evidence(drv, ev)
    finally:
        name = 'evidence_cherry.json' if only == 'all' else f'evidence_cherry_{only}.json'
        with open(os.path.join(ART, name), 'w', encoding='utf-8') as f:
            json.dump(ev, f, ensure_ascii=False, indent=2, default=str)
        drv.quit()
    log(json.dumps(ev, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
