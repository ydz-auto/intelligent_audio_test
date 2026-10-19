# -*- coding: utf-8 -*-
"""INT-893 error pages + login screenshots + IAM users graceful error state."""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:5312')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.path.join('tests', 'ui', 'artifacts', 'int893_general')
THEME_KEY = 'iatp:theme:v1:mode'


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
    time.sleep(1.0)


def _set_theme(drv, mode):
    drv.execute_script("window.localStorage.setItem('%s', arguments[0])" % THEME_KEY, mode)


def _body(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _shot(drv, name):
    os.makedirs(ART, exist_ok=True)
    p = os.path.join(ART, name + '.png')
    drv.save_screenshot(p)
    print(f'SHOT {name}: {os.path.getsize(p)} bytes')


def _net(drv, needle):
    out = []
    try:
        for entry in drv.get_log('performance'):
            msg = json.loads(entry['message'])
            inner = msg.get('message', {})
            if inner.get('method') == 'Network.responseReceived':
                url = inner.get('params', {}).get('response', {}).get('url', '')
                if needle in url:
                    out.append({'url': url, 'status': inner.get('params', {}).get('response', {}).get('status')})
    except Exception:
        pass
    return out


results = []


def check(name, cond, detail=''):
    results.append((name, cond, detail))
    print(f'[{"PASS" if cond else "FAIL"}] {name}' + (f' — {detail}' if detail else ''))


def main():
    drv = _driver()
    try:
        # ---- 登录页：AUTH_MODE=off alert + 浅色/深色截图 + OAuth 区网络证据 ----
        _goto(drv, '/login')
        b = _body(drv)
        check('登录页渲染', '登录' in b and '注册' in b)
        check('AUTH_MODE=off 开放模式 Alert', '当前为开放模式' in b and '进入工作台' in b)
        _set_theme(drv, 'light')
        _goto(drv, '/login')
        _shot(drv, 'login-light')
        _set_theme(drv, 'dark')
        _goto(drv, '/login')
        _shot(drv, 'login-dark')
        oauth_req = _net(drv, '/auth/oauth/providers')
        check('登录页请求 GET /auth/oauth/providers（真实接口）', len(oauth_req) > 0,
              json.dumps(oauth_req, ensure_ascii=False)[:300])
        oauth_500 = any(r.get('status') == 500 for r in oauth_req)
        check('OAuth providers 500 时整区优雅隐藏（无按钮残留）', '使用' not in _body(drv) and oauth_500,
              f'providers_500={oauth_500}')

        # ---- 注册页（先清会话再直达，避免 AUTH_MODE=off 已登录重定向 /dashboard） ----
        _set_theme(drv, 'light')
        drv.execute_script('try { window.localStorage.clear() } catch (e) {}')
        _goto(drv, '/register')
        b = _body(drv)
        check('注册页渲染（清会话后直达 /register）', '创建账号' in b and '登录' in b, b[:150].replace('\n', ' '))
        _shot(drv, 'register-light')

        # ---- 错误页五页（_errors 为 pathless 组，实际路径 /401 /403 /404 /500 /503） ----
        for path, key in (('/401', '请先登录'), ('/403', '禁止访问'),
                          ('/404', '页面未找到'), ('/500', '出错了'),
                          ('/503', '系统维护')):
            _goto(drv, path)
            b = _body(drv)
            found = key in b
            check(f'{path} 渲染（含「{key}」）', found, b[:120].replace('\n', ' ')[:120])
            _set_theme(drv, 'light')
            _goto(drv, path)
            _shot(drv, f'error-{path.split("/")[-1]}-light')
            _set_theme(drv, 'dark')
            _goto(drv, path)
            _shot(drv, f'error-{path.split("/")[-1]}-dark')

        # ---- 未知路径 → 404 notFoundComponent ----
        _set_theme(drv, 'light')
        _goto(drv, '/definitely-not-a-route-xyz')
        b = _body(drv)
        check('未知路径落 404 页', '页面不存在' in b or '不存在' in b, b[:100])
        _shot(drv, 'unknown-404-light')

        # ---- IAM 用户页（显示名编辑所在页）：/auth/users 500 → 优雅空态/错误态 ----
        _goto(drv, '/system-settings/iam/users')
        WebDriverWait(drv, 15).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(3)
        b = _body(drv)
        users_net = _net(drv, '/auth/users')
        check('IAM 用户页请求 GET /auth/users（真实接口）', len(users_net) > 0,
              json.dumps(users_net, ensure_ascii=False)[:300])
        users_500 = any(r.get('status') == 500 for r in users_net)
        check('IAM 用户页 /auth/users 500 时优雅降级（不白屏不崩溃）', users_500 and ('暂无用户' in b or '加载失败' in b or '系统设置' in b),
              b[:200].replace('\n', ' ')[:200])
        _set_theme(drv, 'light')
        _goto(drv, '/system-settings/iam/users')
        time.sleep(2)
        _shot(drv, 'iam-users-error-light')
        _set_theme(drv, 'dark')
        _goto(drv, '/system-settings/iam/users')
        time.sleep(2)
        _shot(drv, 'iam-users-error-dark')
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
    import sys
    sys.exit(main())
