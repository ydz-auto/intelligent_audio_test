# -*- coding: utf-8 -*-
"""INT-893 补验探针：3 项 happy path（常驻栈 auth gRPC 缺口修复后）。

覆盖（代码审计 INT-893 补验清单）：
1. 登录成功链路 —— POST /auth/login 200 → 跳转 /dashboard（Network 留证）
2. OAuth 提供方真实渲染 —— GET /auth/oauth/providers 200（空列表 → 整区正确隐藏，无按钮残留）
3. 显示名编辑 happy path 单独跑 test_ui_31_int698_display_name.py（复用 INT-698 全链路用例）

AUTH_MODE=off + auth 健康下：fresh driver 首次 /login 渲染表单（hydrate 异步）；
hydrate 把 dev_user 持久化到 localStorage 后，再刷新 /login 会 beforeLoad 重定向 /dashboard。
因此浅/深色登录页截图用两个 fresh driver，各自首次直达 /login。

环境：dev server http://127.0.0.1:5312（/api → 常驻 :5000，AUTH_MODE=off）。
"""
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:5312')
ART = os.path.join('tests', 'ui', 'artifacts', 'int893_happy')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
THEME_KEY = 'iatp:theme:v1:mode'

results = []


def check(name, cond, detail=''):
    results.append((name, bool(cond), detail))
    print(f'[{"PASS" if cond else "FAIL"}] {name}' + (f' — {detail}' if detail else ''))


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
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
    drv.set_page_load_timeout(45)
    return drv


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 15).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)


def _body(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _shot(drv, name):
    os.makedirs(ART, exist_ok=True)
    p = os.path.join(ART, name + '.png')
    drv.save_screenshot(p)
    print(f'SHOT {name}: {os.path.getsize(p)} bytes')


def _net_statuses(drv, needle):
    """performance log → Network.responseReceived 中 url 含 needle 的 status 列表。"""
    out = []
    try:
        for entry in drv.get_log('performance'):
            msg = json.loads(entry['message'])
            inner = msg.get('message', {})
            if inner.get('method') == 'Network.responseReceived':
                resp = inner.get('params', {}).get('response', {})
                url = resp.get('url', '')
                if needle in url:
                    out.append({'url': url, 'status': resp.get('status')})
    except Exception:
        pass
    return out


def _reload_with_theme(drv, mode):
    """首次 /login 渲染后清掉持久会话、只保留主题 → 重载（无会话则 beforeLoad 不重定向）。"""
    drv.execute_script(
        "localStorage.clear(); localStorage.setItem('%s', arguments[0])" % THEME_KEY, mode)
    drv.refresh()
    WebDriverWait(drv, 15).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)


def main():
    # ---------- Phase 1（driver A）：登录成功链路 ----------
    drv = _driver()
    try:
        _goto(drv, '/login')
        body = _body(drv)
        check('登录页渲染（fresh session 显示表单）',
              '登录' in body and '用户名' in body and '密码' in body)
        check('AUTH_MODE=off 开放模式 Alert + 进入工作台',
              '当前为开放模式' in body and '进入工作台' in body)
        prov = _net_statuses(drv, '/auth/oauth/providers')
        check('GET /auth/oauth/providers 发出且 200',
              any(r['status'] == 200 for r in prov), json.dumps(prov, ensure_ascii=False)[:200])
        check('空列表 → OAuth 整区隐藏（无分隔线「或使用账号登录」）',
              '或使用账号登录' not in body)
        check('空列表 → 无「使用 … 登录」按钮残留',
              '使用 ' not in body and (' 登录' not in body.split('登 录')[0]) if '登 录' in body else True)
        _shot(drv, 'login-light')

        # 真实表单登录
        drv.find_element(By.ID, 'username').send_keys('admin')
        drv.find_element(By.ID, 'password').send_keys('admin123')
        drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()
        try:
            WebDriverWait(drv, 15).until(
                lambda d: d.current_url.rstrip('/').endswith('/dashboard'))
        except Exception:
            pass
        time.sleep(1.5)
        url = drv.current_url
        check('登录成功 → 跳转工作台 /dashboard', url.rstrip('/').endswith('/dashboard'), url)
        login_net = _net_statuses(drv, '/auth/login')
        check('POST /auth/login 返回 200（Network 留证）',
              any(r['status'] == 200 and r['url'].endswith('/auth/login') for r in login_net),
              json.dumps(login_net, ensure_ascii=False)[:250])
        check('GET /auth/login/encryption-key 200（加密握手，同次抓包）',
              any(r['status'] == 200 and r['url'].endswith('/auth/login/encryption-key') for r in login_net),
              json.dumps(login_net, ensure_ascii=False)[:250])
        toasts = [e.text for e in drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
        check('登录后无错误 toast', not any('失败' in (t or '') for t in toasts),
              json.dumps(toasts, ensure_ascii=False))
        b2 = _body(drv)
        check('工作台页渲染（侧栏/报告/排行榜等真实内容）',
              '工作台' in b2 and '报告' in b2 and '排行榜' in b2)
        _shot(drv, 'dashboard-after-login-light')
    finally:
        try:
            drv.quit()
        except Exception:
            pass

    # ---------- Phase 2（driver B）：深色登录页截图 ----------
    drv = _driver()
    try:
        _goto(drv, '/login')
        _reload_with_theme(drv, 'dark')
        b = _body(drv)
        check('深色登录页仍渲染表单（非重定向）',
              '用户名' in b and '密码' in b, drv.current_url)
        _shot(drv, 'login-dark')
    finally:
        try:
            drv.quit()
        except Exception:
            pass

    print('=' * 50)
    failed = [r for r in results if not r[1]]
    print(f'TOTAL {len(results)} checks, {len(failed)} failed')
    for name, cond, detail in results:
        print(f'[{"PASS" if cond else "FAIL"}] {name}')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
