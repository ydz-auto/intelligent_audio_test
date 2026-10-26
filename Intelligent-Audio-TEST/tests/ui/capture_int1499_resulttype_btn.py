# -*- coding: utf-8 -*-
"""INT-1499 取证：结果类型只有一种时不渲染「结果类型视图」按钮（负责人 2026-10-24）。

真实库栈 15000 + dev server 5321（rsbuild 临时反代 127.0.0.1:15000）。
流程：登录 → 挑选合并 → 阶段 2（抓视图切换器按钮集合 + 截图）
      → 全选 → 加入购物车 → 购物车步骤（抓按钮集合 + 截图）→ 深色重跑 → 清空购物车。
证据：视图切换器按钮文案集合（浅/深）、阶段 2 / 购物车截图、candidates 响应。
用法：python tests/ui/capture_int1499_resulttype_btn.py
"""
import json
import os
import time
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('INT1499_BASE', 'http://127.0.0.1:5321')
API = 'http://127.0.0.1:15000/api/v1'
ART = os.path.join('tests', 'ui', 'artifacts', 'int1499')
DRIVER = os.environ.get(
    'INT1499_DRIVER',
    r'D:\00_user_data\.cache\selenium\chromedriver\win64\155.0.8059.84\chromedriver.exe',
)
VIEW_LABELS = ('用例视图', '设备视图', '结果类型视图', '任务分组', '任务视图')
LOGIN_USER = '接线测试_admin'
LOGIN_PASS = 'JieXianTest@2026'
TOKEN = {'v': None}

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
  return {status: r.status, token: j.access_token || null, body: r.ok ? 'ok' : txt.slice(0,300)};
})()
"""

os.makedirs(ART, exist_ok=True)


def driver():
    os.environ.setdefault('SE_OFFLINE', 'true')
    opts = webdriver.ChromeOptions()
    opts.add_argument('--headless=new')
    opts.add_argument('--window-size=1680,1050')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--lang=zh-CN')
    opts.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    d = webdriver.Chrome(service=Service(DRIVER), options=opts)
    d.set_page_load_timeout(120)
    return d


def shot(d, name):
    time.sleep(0.7)
    p = os.path.join(ART, name + '.png')
    d.save_screenshot(p)
    return p


def js_click(d, el):
    d.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)


def click_button(d, text, contains=False, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        for b in d.find_elements(By.TAG_NAME, 'button'):
            t = (b.text or '').strip()
            if not b.is_displayed():
                continue
            if (contains and text in t) or (not contains and t == text):
                js_click(d, b)
                return t
        time.sleep(0.5)
    raise RuntimeError('button not found: %s' % text)


def view_buttons(d):
    out = []
    for b in d.find_elements(By.TAG_NAME, 'button'):
        t = (b.text or '').strip()
        if b.is_displayed() and t in VIEW_LABELS:
            out.append(t)
    return out


def set_theme(d, mode):
    d.execute_script("window.localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", mode)
    d.refresh()
    time.sleep(2.5)


def login(d):
    """页面内 RSA-OAEP 加密登录（AUTH_MODE=off 下购物车写接口要求真实用户）。"""
    d.set_script_timeout(120)
    res = {}
    for _ in range(3):
        try:
            d.get(BASE + '/login')
            time.sleep(4)
            res = d.execute_script(LOGIN_JS, LOGIN_PASS, LOGIN_USER)
            if res.get('token'):
                break
        except Exception:  # noqa: BLE001
            time.sleep(2)
    TOKEN['v'] = res.get('token')
    print('LOGIN', res.get('status'), bool(res.get('token')))
    if not TOKEN['v']:
        raise RuntimeError('login failed: %s' % res.get('body'))


def clear_cart():
    """收尾：清空本 run 加进购物车的条目（真实主库不留残留）。"""
    req = urllib.request.Request(API + '/api/v1/tasks/cherry-picks/cart/items', method='DELETE')
    if TOKEN['v']:
        req.add_header('Authorization', 'Bearer ' + TOKEN['v'])
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read() or b'{}').get('message')
    except Exception as exc:  # noqa: BLE001
        return 'failed: %s' % exc


def drain(d):
    out = []
    for e in d.get_log('performance'):
        try:
            m = json.loads(e['message']).get('message', {})
        except Exception:
            continue
        meth = m.get('method')
        pr = m.get('params', {})
        if meth == 'Network.responseReceived':
            r = pr.get('response', {})
            u = r.get('url', '')
            if '/api/' in u:
                out.append({'url': u, 'status': r.get('status')})
    return out


def open_stage2(d):
    """进入挑选向导 → 阶段 1 勾一个任务 → 下一步，返回阶段 2 候选行数。"""
    d.get(BASE + '/tasks?tab=cherry-picks')
    click_button(d, '开始挑选', timeout=90)
    WebDriverWait(d, 30).until(lambda x: '挑选 · 阶段 1：选择任务' in (x.page_source or ''))
    WebDriverWait(d, 120).until(
        lambda x: len([r for r in x.find_elements(By.CSS_SELECTOR, "[data-testid^='pick-task-']") if r.is_displayed()]) > 0
    )
    time.sleep(1.0)
    rows = [r for r in d.find_elements(By.CSS_SELECTOR, "[data-testid^='pick-task-']") if r.is_displayed()]
    boxes = rows[0].find_elements(By.CSS_SELECTOR, "[role='checkbox']")
    if boxes:
        js_click(d, boxes[0])
    else:
        js_click(d, rows[0])
    time.sleep(1.0)
    click_button(d, '下一步：选择结果', contains=True, timeout=30)
    WebDriverWait(d, 30).until(lambda x: '挑选 · 阶段 2：选择结果' in (x.page_source or ''))
    # 候选行加载（真实库 candidates 较慢，等出现结果行或空态）
    deadline = time.time() + 150
    while time.time() < deadline:
        body = d.page_source or ''
        if '无符合条件的执行结果' in body or '候选加载失败' in body:
            break
        leaves = [r for r in d.find_elements(By.CSS_SELECTOR, "[data-testid^='pick-leaf-']") if r.is_displayed()]
        if leaves:
            break
        time.sleep(2)
    time.sleep(1.5)
    return {
        'empty': '无符合条件的执行结果' in (d.page_source or ''),
        'error': '候选加载失败' in (d.page_source or ''),
        'leaf_rows': len([r for r in d.find_elements(By.CSS_SELECTOR, "[data-testid^='pick-leaf-']") if r.is_displayed()]),
    }


def open_cart_step(d):
    click_button(d, '加入购物车', contains=True, timeout=30)
    time.sleep(3)
    for b in d.find_elements(By.CSS_SELECTOR, "[data-testid='wizard-step-cart']"):
        js_click(d, b)
    time.sleep(2.5)
    WebDriverWait(d, 40).until(lambda x: '我的购物车' in (x.page_source or '') or '购物车为空' in (x.page_source or ''))
    time.sleep(1.5)


def main():
    d = driver()
    result = {'base': BASE, 'shots': [], 'views': {}, 'network': {}}
    try:
        d.get(BASE + '/')
        login(d)
        set_theme(d, 'light')

        stage2 = open_stage2(d)
        result['stage2'] = stage2
        result['views']['stage2_light'] = view_buttons(d)
        result['network']['stage2_light'] = drain(d)
        result['shots'].append(shot(d, 'p1_stage2_light'))

        click_button(d, '全选当前筛选', timeout=30)
        time.sleep(2)
        clicked = click_button(d, '加入购物车', contains=True, timeout=30)
        result['add_to_cart_button'] = clicked
        time.sleep(4)
        for b in d.find_elements(By.CSS_SELECTOR, "[data-testid='wizard-step-cart']"):
            js_click(d, b)
        time.sleep(3)
        result['views']['cart_light'] = view_buttons(d)
        result['cart_body'] = (d.page_source or '')[:0]
        result['network']['cart_light'] = drain(d)
        result['shots'].append(shot(d, 'p2_cart_light'))

        body = d.page_source or ''
        result['cart_empty'] = '购物车为空' in body

        # 深色：主题切换后重走一遍（购物车镜像来自后端，仍在）
        set_theme(d, 'dark')
        stage2d = open_stage2(d)
        result['stage2_dark'] = stage2d
        result['views']['stage2_dark'] = view_buttons(d)
        result['shots'].append(shot(d, 'p3_stage2_dark'))
        for b in d.find_elements(By.CSS_SELECTOR, "[data-testid='wizard-step-cart']"):
            js_click(d, b)
        time.sleep(3)
        result['views']['cart_dark'] = view_buttons(d)
        result['shots'].append(shot(d, 'p4_cart_dark'))

        # 收尾：清空购物车（本 run 自己加进去的条目，起始购物车为空）
        result['cart_clear'] = clear_cart()
    finally:
        d.quit()
    out = os.path.join(ART, 'result.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=True, indent=2)[:5000])
    print('saved', out)


if __name__ == '__main__':
    main()
