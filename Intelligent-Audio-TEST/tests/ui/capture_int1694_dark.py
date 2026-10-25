# -*- coding: utf-8 -*-
"""INT-1694 返工取证：补齐深色批次缺的 6 个视图 + 收尾清空购物车。

代码审计打回（01a16bdd-0773-79de-afa1-14824876d925）只缺证据，不动代码：
- 复核步骤（CartPanel 复用）：用例视图 / 设备视图 / 结果类型视图（深色）
- 购物车：设备视图 / 结果类型视图 / 任务视图-结果类型子模式（深色）

环境：本 run dev server 5331（/api 临时反代 docker 真实栈 15000，库 intelligent_audio_test）。
AUTH_MODE=off：购物车写接口需真实登录 token，故在 /login 页内走 RSA-OAEP 加密登录后写
localStorage['iatp:auth:token:v1']（账号 接线测试_admin，与 verify_int1592 同口径）。
真实数据：任务 311（100 条）+ 312（94 条），共 194 条候选、16 个用例跨两任务。
收尾：DELETE /tasks/cherry-picks/cart/items 清空购物车并回读 total=0。

输出：tests/ui/artifacts/int1694_dark/*.png + evidence.json
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')

from selenium import webdriver  # noqa: E402
from selenium.webdriver.chrome.options import Options  # noqa: E402
from selenium.webdriver.chrome.service import Service  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.common.keys import Keys  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402

BASE = os.environ.get('INT1694_BASE', 'http://127.0.0.1:5331')
API = os.environ.get('INT1694_API', 'http://127.0.0.1:15000')
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1694_dark')
os.makedirs(ART, exist_ok=True)
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
LOGIN_USER = os.environ.get('IAT_LOGIN_USER', '接线测试_admin')
LOGIN_PASS = os.environ.get('IAT_LOGIN_PASS', 'JieXianTest@2026')
TASK_A = os.environ.get('INT1694_TASK_A', '2026/8/27 11:51:07')  # 任务 311，100 条
TASK_B = os.environ.get('INT1694_TASK_B', '2026/8/27 16:06:11')  # 任务 312，94 条

TOKEN = {'v': None}
EV = {'base': BASE, 'started_at': time.strftime('%Y-%m-%d %H:%M:%S'), 'shots': [],
      'tree_counts': {}}


def log(msg):
    print(msg, flush=True)


# ------------------------------------------------------------------ http
def api(method, path, body=None, token=None, timeout=180):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method)
    if data:
        req.add_header('Content-Type', 'application/json')
    tok = token or TOKEN['v']
    if tok:
        req.add_header('Authorization', 'Bearer ' + tok)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b'{}')
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return json.loads(raw)
        except Exception:  # noqa: BLE001
            return {'_http': e.code, '_body': raw.decode('utf-8', 'replace')[:400]}


def data_of(resp):
    return resp.get('data') if isinstance(resp, dict) else None


def health():
    try:
        with urllib.request.urlopen(API + '/health', timeout=30) as r:
            return json.loads(r.read() or b'{}')
    except Exception as exc:  # noqa: BLE001
        return {'_error': str(exc)}


def cart_total():
    d = data_of(api('GET', '/api/v1/tasks/cherry-picks/cart')) or {}
    return d.get('total', 0)


# ------------------------------------------------------------------ driver
def make_driver(w=1600, h=1600):
    o = Options()
    o.binary_location = CHROME
    o.add_argument('--headless=new')
    o.add_argument('--window-size=%d,%d' % (w, h))
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--force-prefers-reduced-motion')
    o.add_argument('--disable-dev-shm-usage')
    o.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
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
    d = webdriver.Chrome(options=o, service=Service(executable_path=exe) if exe else Service())
    d.set_page_load_timeout(120)
    d.set_script_timeout(180)
    return d


def text_of(drv, el):
    return (drv.execute_script('return arguments[0].textContent || "";', el) or '').strip()


def js_click(drv, el):
    drv.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)


def shot(drv, name):
    # 树是内层滚动容器：展开时 scrollIntoView 会把容器滚走，截图前把所有滚动容器归零，
    # 这样图里能从上到下看到顶层分支 → 逐层 → 叶。
    drv.execute_script(
        "window.scrollTo(0,0);"
        "document.querySelectorAll('*').forEach(function(e){"
        "  if (e.scrollTop > 0 && e.scrollHeight > e.clientHeight + 20) e.scrollTop = 0;"
        "});")
    time.sleep(0.5)
    p = os.path.join(ART, name + '.png')
    drv.save_screenshot(p)
    EV['shots'].append(name)
    log('SHOT ' + name)


def click_exact(drv, label, css='button', limit=False):
    """文本完全相等的按钮（避免「用例」误中「用例视图」）。"""
    for el in drv.find_elements(By.CSS_SELECTOR, css):
        try:
            if text_of(drv, el) == label:
                js_click(drv, el)
                return el
        except Exception:  # noqa: BLE001
            pass
    if limit:
        return None
    raise RuntimeError('找不到按钮: %s' % label)


def click_contains(drv, needle, css='button', limit=False):
    for el in drv.find_elements(By.CSS_SELECTOR, css):
        try:
            if needle in text_of(drv, el):
                js_click(drv, el)
                return el
        except Exception:  # noqa: BLE001
            pass
    if limit:
        return None
    raise RuntimeError('找不到按钮: %s' % needle)


# ------------------------------------------------------------------ login / theme
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


def login(drv):
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
    EV['login'] = {'status': res.get('status'),
                   'user': (res.get('user') or {}).get('username'),
                   'token': bool(res.get('token')), 'body': res.get('body')}
    TOKEN['v'] = res.get('token')
    log('login -> %s' % EV['login'])
    if not TOKEN['v']:
        raise RuntimeError('登录失败：%s' % res.get('body'))


def set_dark(drv):
    drv.execute_script(
        "localStorage.setItem('iatp:theme:v1:mode','dark');"
        "localStorage.setItem('iatp:theme:v1:preset','lake-view');")
    drv.get(BASE + '/tasks/cherry-pick')
    WebDriverWait(drv, 90).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, "[role='tab']")) > 0)
    time.sleep(2)
    EV['theme'] = drv.execute_script(
        "return {mode: localStorage.getItem('iatp:theme:v1:mode'),"
        " htmlClass: document.documentElement.className};")
    log('theme -> %s' % EV['theme'])


# ------------------------------------------------------------------ flow
def open_pick(drv):
    for t in drv.find_elements(By.CSS_SELECTOR, "[role='tab']"):
        if '挑选合并' in text_of(drv, t):
            js_click(drv, t)
            break
    time.sleep(2)
    click_contains(drv, '开始挑选')
    WebDriverWait(drv, 90).until(
        lambda d: any('下一步' in text_of(d, b)
                      for b in d.find_elements(By.CSS_SELECTOR, 'button')))
    time.sleep(2)


def select_tasks(drv):
    chosen = []
    for needle in (TASK_A, TASK_B):
        hit = None
        for cb in drv.find_elements(By.CSS_SELECTOR, '[role="checkbox"]'):
            label = cb.get_attribute('aria-label') or ''
            if label.startswith('选择任务') and needle in label:
                hit = cb
                break
        if hit is None:
            raise RuntimeError('阶段 1 未找到任务: %s' % needle)
        js_click(drv, hit)
        chosen.append(hit.get_attribute('aria-label'))
        time.sleep(0.5)
    EV['stage1_selected'] = chosen
    log('STAGE1_SELECTED %s' % chosen)
    body = drv.find_element(By.TAG_NAME, 'body').text
    if '已选' not in body:
        raise RuntimeError('阶段 1 勾选后未见已选计数')


def stage2_ready(drv):
    """阶段 2 就绪：树已渲染（分支行或用例卡勾选框）+ 骨架屏消失 + 已选汇总条存在。"""
    if drv.find_elements(By.CSS_SELECTOR, '.animate-pulse'):
        return False
    body = drv.find_element(By.TAG_NAME, 'body').text
    if '无符合条件的执行结果' in body:
        return True
    if '加入购物车（' not in body or '阶段 2' not in body:
        return False
    branches = drv.find_elements(By.CSS_SELECTOR, "button[aria-label$='条）']")
    if branches:
        return True
    # 用例视图顶层是用例卡（无 data-testid），以卡片勾选框「选择 <用例名>」判定
    cards = [c for c in drv.find_elements(By.CSS_SELECTOR, '[role="checkbox"]')
             if (c.get_attribute('aria-label') or '').startswith('选择 ')]
    return len(cards) > 0


def go_stage2(drv):
    click_contains(drv, '下一步')
    # 候选慢：等树出现；若报「候选加载失败」则点重试，最多 3 轮
    for attempt in range(4):
        deadline = time.time() + 150
        while time.time() < deadline:
            body = drv.find_element(By.TAG_NAME, 'body').text
            if '候选加载失败' in body:
                log('candidates failed, retry %d' % (attempt + 1))
                click_contains(drv, '重试', limit=True)
                time.sleep(5)
                break
            if stage2_ready(drv):
                time.sleep(2)
                return
            time.sleep(3)
    raise RuntimeError('阶段 2 候选未加载成功')


def toasts(drv):
    out = []
    for t in drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]'):
        try:
            out.append(text_of(drv, t)[:160])
        except Exception:  # noqa: BLE001
            pass
    return out


def select_all_stage2(drv):
    """全选当前筛选 → 轮询「加入购物车（n>0）」（树渲染慢时按钮 disabled，多点几次）。"""
    n = 0
    for _ in range(10):
        click_contains(drv, '全选当前筛选', limit=True)
        time.sleep(2)
        body = drv.find_element(By.TAG_NAME, 'body').text
        EV['stage2_summary'] = [ln for ln in body.splitlines() if '已选' in ln][:3]
        m = re.search(r'加入购物车（(\d+)）', body)
        n = int(m.group(1)) if m else 0
        if n > 0:
            break
        time.sleep(3)
    EV['stage2_selected'] = n
    log('STAGE2_SELECTED n=%d %s' % (n, EV['stage2_summary']))
    if n <= 0:
        raise RuntimeError('阶段 2 全选后仍为 0 条，无法加购')
    add = click_contains(drv, '加入购物车', limit=True)
    if add is None:
        raise RuntimeError('未找到加入购物车按钮')
    time.sleep(4)
    EV['add_toasts'] = toasts(drv)
    log('ADD_TOASTS %s' % EV['add_toasts'])


def wait_cart_step(drv):
    deadline = time.time() + 90
    total = 0
    while time.time() < deadline:
        total = cart_total()
        if total:
            break
        if len(drv.find_elements(By.CSS_SELECTOR, '[data-testid^="cart-branch-"]')) > 0:
            break
        time.sleep(3)
    time.sleep(2)
    EV['cart_total_api'] = total
    EV['cart_toasts'] = toasts(drv)
    log('CART total(api)=%s toasts=%s' % (total, EV['cart_toasts']))
    if not total:
        raise RuntimeError('购物车仍为空，加购未生效：toasts=%s' % EV['cart_toasts'])


EXPAND_JS = r"""
var bs = Array.prototype.slice.call(document.querySelectorAll('button[aria-label="\u5c55\u5f00"]'));
bs.forEach(function(b){ try { b.scrollIntoView({block:'center'}); b.click(); } catch(e) {} });
return bs.length;
"""


def expand_all(drv):
    """\u9010\u5c42\u5c55\u5f00\uff1a\u4e00\u6b21 JS \u6279\u91cf\u70b9\u6389\u5f53\u524d\u6240\u6709\u300c\u5c55\u5f00\u300d\u94ae\uff0c\u76f4\u5230\u6ca1\u6709\u53ef\u5c55\u5f00\u9879\uff08\u5185\u5c42\u6eda\u52a8\uff0c\u901f\u5ea6\u4f18\u5148\uff09\u3002"""
    for _ in range(10):
        n = drv.execute_script(EXPAND_JS)
        if not n:
            break
        time.sleep(0.9)
    time.sleep(0.8)


def snapshot_tree(drv):
    labels = []
    for b in drv.find_elements(By.CSS_SELECTOR, "button[aria-label$='条）']"):
        try:
            labels.append(b.get_attribute('aria-label'))
        except Exception:  # noqa: BLE001
            pass
        if len(labels) >= 6:
            break
    return {
        'cart_branches': len(drv.find_elements(By.CSS_SELECTOR, '[data-testid^="cart-branch-"]')),
        'cart_leaves': len(drv.find_elements(By.CSS_SELECTOR, '[data-testid^="cart-leaf-"]')),
        'first_branches': labels,
    }


def cart_dark_shots(drv):
    body = drv.find_element(By.TAG_NAME, 'body').text
    if '去复核' not in body:
        raise RuntimeError('当前不在购物车步骤（未见「去复核」），拒绝出图')
    EV['cart_step_body'] = [ln for ln in body.splitlines() if '条' in ln][:4]
    expand_all(drv)
    shot(drv, 'dark_cart_task_case')
    EV.setdefault('tree_counts', {})['cart_task_case'] = snapshot_tree(drv)
    # 任务视图 · 结果类型子模式（缺失项 3/6）
    click_exact(drv, '结果类型')
    time.sleep(1.5)
    expand_all(drv)
    shot(drv, 'dark_cart_task_resulttype')
    EV['tree_counts']['cart_task_resulttype'] = snapshot_tree(drv)
    # A 组 · 设备视图（缺失项 1/6）
    click_exact(drv, '设备视图')
    time.sleep(1.5)
    expand_all(drv)
    shot(drv, 'dark_cart_device')
    EV['tree_counts']['cart_device'] = snapshot_tree(drv)
    # A 组 · 结果类型视图（缺失项 2/6）
    click_exact(drv, '结果类型视图')
    time.sleep(1.5)
    expand_all(drv)
    shot(drv, 'dark_cart_resulttype')
    EV['tree_counts']['cart_resulttype'] = snapshot_tree(drv)


def review_dark_shots(drv):
    # 购物车步骤 → 复核步骤（共用 CartPanel）
    btn = click_contains(drv, '去复核', limit=True)
    if btn is None:
        for b in drv.find_elements(By.CSS_SELECTOR, '[data-testid="wizard-step-review"]'):
            js_click(drv, b)
            break
    WebDriverWait(drv, 180).until(
        lambda d: '确认下单' in d.find_element(By.TAG_NAME, 'body').text)
    # 复核摘要走 POST /tasks/cherry-picks/preview，慢；等它落地（来源任务有数字）再出图，
    # 否则截图落在 Skeleton 加载态。
    deadline = time.time() + 240
    ready = False
    while time.time() < deadline:
        body = drv.find_element(By.TAG_NAME, 'body').text
        if re.search(r'结果 \d+ 条', body) and re.search(r'来源任务 \d+ 个', body):
            ready = True
            break
        time.sleep(4)
    EV['review_summary_ready'] = ready
    log('REVIEW summary ready=%s' % ready)
    time.sleep(2)
    body = drv.find_element(By.TAG_NAME, 'body').text
    EV['review_summary'] = [ln for ln in body.splitlines() if '结果' in ln and '条' in ln][:5]
    # A 组 · 用例视图（缺失项 4/6）
    click_exact(drv, '用例视图')
    time.sleep(1.5)
    expand_all(drv)
    shot(drv, 'dark_review_case')
    EV['tree_counts']['review_case'] = snapshot_tree(drv)
    # A 组 · 设备视图（缺失项 5/6）
    click_exact(drv, '设备视图')
    time.sleep(1.5)
    expand_all(drv)
    shot(drv, 'dark_review_device')
    EV['tree_counts']['review_device'] = snapshot_tree(drv)
    # A 组 · 结果类型视图（缺失项 6/6）
    click_exact(drv, '结果类型视图')
    time.sleep(1.5)
    expand_all(drv)
    shot(drv, 'dark_review_resulttype')
    EV['tree_counts']['review_resulttype'] = snapshot_tree(drv)


def cleanup():
    before = cart_total()
    resp = api('DELETE', '/api/v1/tasks/cherry-picks/cart/items')
    time.sleep(2)
    after = cart_total()
    EV['cart_cleanup'] = {'before': before, 'resp_success': resp.get('success'),
                          'resp_message': resp.get('message'), 'after': after}
    log('CART CLEANUP %s' % EV['cart_cleanup'])


def main():
    phase = sys.argv[1] if len(sys.argv) > 1 else 'all'
    EV['phase'] = phase
    drv = make_driver()
    try:
        EV['health_start'] = health()
        EV['cart_total_start'] = cart_total()
        log('health(start) %s cart=%s' % (EV['health_start'], EV['cart_total_start']))
        login(drv)
        set_dark(drv)
        open_pick(drv)
        select_tasks(drv)
        go_stage2(drv)
        select_all_stage2(drv)
        wait_cart_step(drv)
        if phase in ('cart', 'all'):
            cart_dark_shots(drv)
        if phase in ('review', 'all'):
            review_dark_shots(drv)
        EV['health_end'] = health()
        log('health(after shots) %s' % EV['health_end'])
    finally:
        console = []
        try:
            for entry in drv.get_log('browser'):
                if entry.get('level') in ('SEVERE', 'WARNING'):
                    console.append(entry.get('message')[:200])
        except Exception:  # noqa: BLE001
            pass
        EV['console'] = console[-15:]
        try:
            drv.quit()
        except Exception:  # noqa: BLE001
            pass
        if phase != 'cart':
            try:
                cleanup()
            except Exception as exc:  # noqa: BLE001
                EV['cart_cleanup'] = {'error': str(exc)}
        EV['health_final'] = health()
        EV['finished_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
        with open(os.path.join(ART, 'evidence.json'), 'w', encoding='utf-8') as f:
            json.dump(EV, f, ensure_ascii=False, indent=2)
        log('EVIDENCE %s' % os.path.join(ART, 'evidence.json'))
        log('OK')


if __name__ == '__main__':
    main()
