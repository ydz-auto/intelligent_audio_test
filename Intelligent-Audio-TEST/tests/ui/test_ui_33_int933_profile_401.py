# -*- coding: utf-8 -*-
"""INT-933 缺陷修复验收（Selenium headless，真实 Chrome + 常驻 5000 后端 AUTH_MODE=off）。

缺陷：AUTH_MODE=off 下访问 /profile 被 /auth/oauth/bindings 的 401 弹回
/login?redirect=%2Fprofile，个人中心不可见。修复：listOAuthBindings 加
skipAuthRedirect:true，bindings 401 仅降级为该子请求空态，不触发全局登出跳转。

验收清单（INT-933 卡内「期望 vs 实际」）：
① 直开 /profile 停留在 /profile（URL 不落 /login）——修复前落 /login?redirect=%2Fprofile
② 身份卡真实数据渲染：@dev_user / 用户 ID 0 / 权限 ['*'] →「1 项权限」+ 通配 Popover
③ 收藏 / 快捷入口真实数据渲染
④ 账号安全卡第三方绑定区空态「当前没有可绑定的第三方登录方式」（bindings 401 优雅降级）
⑤ Network 真实请求：/auth/me /favorites /auth/oauth/providers /home/site；
   /auth/oauth/bindings 401 直证 + 页面仍停留 /profile
⑥ 浅 / 深色截图 + Network 截图

失败落 tests/ui/artifacts/int933_profile/<步骤>/。
"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5314')
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int933_profile')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

FAILED = []


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    options.set_capability('goog:perfLoggingPrefs', {
        'enableNetwork': True,
        'enablePage': False,
    })
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium',
                              'chromedriver', 'win64')
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


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _check(name, cond, extra=''):
    if cond:
        print(f'  PASS  {name}')
    else:
        print(f'  FAIL  {name}  {extra}')
        FAILED.append(name)


def _collect_network(drv, net_log):
    """从 performance 日志收集真实网络请求（请求 URL + 响应状态）。"""
    try:
        logs = drv.get_log('performance')
    except Exception:
        return
    for entry in logs:
        try:
            msg = json.loads(entry['message'])
            params = msg.get('params', {})
            method = msg.get('method')
            if method == 'Network.responseReceived':
                rid = params.get('requestId')
                resp = params.get('response', {})
                net_log.setdefault(rid, {})['status'] = resp.get('status')
                net_log[rid]['mime'] = resp.get('mimeType', '')
            elif method == 'Network.requestWillBeSent':
                rid = params.get('requestId')
                req = params.get('request', {})
                net_log.setdefault(rid, {})['url'] = req.get('url', '')
                net_log[rid]['method'] = req.get('method', '')
        except Exception:
            pass


def main():
    drv = _driver()
    net_log = {}
    os.makedirs(ARTIFACTS, exist_ok=True)

    # ① 直开 /profile（无 token，AUTH_MODE=off → dev_user 自动会话）
    print('STEP 1: 打开 /profile（AUTH_MODE=off 免登录）')
    drv.get(BASE + '/profile')
    WebDriverWait(drv, 20).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(3.5)  # 等 useQuery 全部落定（auth/me→身份卡、favorites、providers/bindings）
    _collect_network(drv, net_log)

    url = drv.current_url
    body = _body_text(drv)
    print('  URL =', url)
    _check('① URL 停留 /profile（不弹 /login）', '/login' not in url, url)
    _check('① 页面标题含 个人中心', '个人中心' in drv.title, drv.title)
    _check('② 身份卡 @dev_user', '@dev_user' in body)
    _check('② 用户 ID 徽章 0', '用户 ID 0' in body)
    _check('② 权限概览 1 项', '1 项权限' in body)
    _check('③ 快捷入口三格', '我的收藏' in body and '我的任务' in body and '我的报告' in body)
    _check('④ 绑定区空态文案', '当前没有可绑定的第三方登录方式' in body,
           '（期望 bindings 401 优雅降级为空态）')

    # ② 通配权限 Popover（触发钮 aria-label=查看权限清单）
    try:
        btn = drv.find_element(By.CSS_SELECTOR, '[aria-label="查看权限清单"]')
        btn.click()
        time.sleep(1.0)
        body2 = _body_text(drv)
        _check('② 通配 Popover 文案', '超级管理员持有全部权限（通配 *）' in body2)
    except Exception as e:
        print('  Popover 点击失败:', e)
        _check('② 通配 Popover 文案', False, str(e))
    drv.save_screenshot(os.path.join(ARTIFACTS, 'profile_light.png'))

    # ⑥ 深色截图（next-themes 切换）
    try:
        drv.execute_script("try{localStorage.setItem('theme','dark')}catch(e){}")
        drv.get(BASE + '/profile')
        time.sleep(3.5)
        body_dark = _body_text(drv)
        _check('深色下仍停留 /profile', '/login' not in drv.current_url, drv.current_url)
        _check('深色下绑定空态仍在', '当前没有可绑定的第三方登录方式' in body_dark)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'profile_dark.png'))
    except Exception as e:
        print('  深色验证失败:', e)
        _check('深色下仍停留 /profile', False, str(e))

    # ⑤ Network 摘要：performance entries 列出真实请求；bindings 状态经同源 fetch 直证
    print('\nSTEP 5: Network 摘要')
    resources = drv.execute_script(
        "return performance.getEntriesByType('resource').map(function(e){return e.name})")
    api_hits = sorted({r.split('?')[0] for r in resources
                       if '/api/v1/' in r and '/sockjs' not in r})
    seen = {}
    for url in api_hits:
        seen[url.replace(BASE + '/api/v1', '')] = 'hit'
    for url in sorted(seen):
        print(f'  请求 {url}')
    _check('⑤ 真实请求 /auth/me', any(k.endswith('/auth/me') for k in seen))
    _check('⑤ 真实请求 /favorites', any(k.endswith('/favorites') for k in seen))
    _check('⑤ 真实请求 /auth/oauth/providers',
           any(k.endswith('/auth/oauth/providers') for k in seen))
    _check('⑤ 真实请求 /home/site', any(k.endswith('/home/site') for k in seen))

    # bindings 状态直证：同源 fetch（dev proxy → 常驻 5000），并确认页面仍未弹登录
    before_url = drv.current_url
    bindings_status = drv.execute_script(
        "return fetch('/api/v1/auth/oauth/bindings', {headers:{Accept:'application/json'}})"
        ".then(function(r){return r.status})")
    _check('bindings 同源 fetch 有状态码', isinstance(bindings_status, int), str(bindings_status))
    print(f'  bindings 直证 HTTP 状态 = {bindings_status}'
          f'（401 = off 模式后端按 user_id=0 判未登录）')
    _check('bindings 返回 401（off 模式后端判定）', bindings_status == 401, str(bindings_status))
    time.sleep(1.0)
    after_url = drv.current_url
    _check('⑤ bindings 401 后页面仍停留 /profile', '/login' not in after_url, after_url)

    with open(os.path.join(ARTIFACTS, 'network.json'), 'w', encoding='utf-8') as f:
        json.dump({'api_hits': api_hits, 'bindings_status': bindings_status},
                  f, ensure_ascii=False, indent=2)

    # console：bindings 401 的资源加载报错属预期证据（不弹页），其余 JS 异常才算 severe
    all_console = []
    try:
        all_console = [e.get('message', '') for e in drv.get_log('browser')
                       if e.get('level') == 'SEVERE']
    except Exception:
        pass
    expected_401 = [m for m in all_console
                    if '/auth/oauth/bindings' in m and 'status of 401' in m]
    js_errors = [m for m in all_console if m not in expected_401]
    print(f'\nconsole SEVERE 共 {len(all_console)} 条；'
          f'bindings 401 资源报错（预期证据）{len(expected_401)} 条；'
          f'其余 JS 异常 {len(js_errors)} 条')
    _check('bindings 401 资源报错已被浏览器记录（证据）', len(expected_401) >= 1)
    _check('无其余 JS 异常', not js_errors, '; '.join(s[:120] for s in js_errors[:3]))

    drv.quit()
    print('\nRESULT:', 'FAILED=' + str(len(FAILED)) if FAILED else 'ALL PASS')
    return 1 if FAILED else 0


if __name__ == '__main__':
    raise SystemExit(main())
