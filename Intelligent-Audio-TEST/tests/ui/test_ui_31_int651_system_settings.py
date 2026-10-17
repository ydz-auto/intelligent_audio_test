# -*- coding: utf-8 -*-
"""INT-651 系统设置域 infra mock→api 接线浏览器验收（真实 Chrome headless）。

覆盖验收标准：系统设置域（RBAC 角色管理/用户管理、系统选项、OAuth 管理、
LLM Provider 配置）经 client.ts 切真实接口后核心链路浏览器实测。

前置：dev server :5391 已在跑（服务 INT-651 代码，rsbuild proxy /api →
隔离 INT-620 栈 :6000，AUTH_MODE=off，隔离库 intelligent_audio_test_test）。
:6000 由主项目 parallel_stack.py（UI_STACK_SHIFT=1000）提供（INT-620 已合入主项目）。
"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5391')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ARTIFACTS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         'artifacts', 'int651_system_settings')
os.makedirs(ARTIFACTS, exist_ok=True)


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
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


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 20).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _wait_text(drv, text, timeout=20):
    WebDriverWait(drv, timeout).until(lambda d: text in _body_text(drv))


def _clear_storage(drv):
    drv.execute_script('try { window.localStorage.clear() } catch (e) {}')


def _screenshot(drv, name):
    d = os.path.join(ARTIFACTS, name)
    drv.save_screenshot(d)
    print(f'[shot] {d}')


def _enter_workbench(drv):
    """AUTH_MODE=off：登录页「进入工作台」直达 /dashboard。"""
    _clear_storage(drv)
    _goto(drv, '/login')
    _wait_text(drv, '进入工作台')
    drv.find_element(By.XPATH, "//button[contains(., '进入工作台')]").click()
    WebDriverWait(drv, 20).until(lambda d: '/dashboard' in d.current_url)
    _wait_text(drv, '工作台', timeout=20)


def _network_json(drv, label):
    """经 Performance API 收集资源请求，抽出关键 API 条目存 JSON。"""
    entries = drv.execute_script(
        'return performance.getEntriesByType("resource")'
        '.map(e => ({name: e.name, duration: Math.round(e.duration)}))')
    apis = [e for e in entries
            if any(x in e['name'] for x in
                   ['/auth/roles', '/auth/permissions', '/auth/users',
                    '/auth/oauth-providers', '/api/option/', '/auth/me',
                    '/auth/mode', '/oauth/admin/discovery'])]
    with open(os.path.join(ARTIFACTS, f'network_{label}.json'), 'w', encoding='utf-8') as f:
        json.dump(apis, f, ensure_ascii=False, indent=2)
    print(f'[network] {label}: {len(apis)} api entries')
    return apis


def main():
    drv = _driver()
    try:
        _enter_workbench(drv)
        _network_json(drv, 'workbench')

        # 1) 角色管理（roleApi: GET /auth/roles + /auth/permissions）
        _goto(drv, '/system-settings/iam/roles')
        _wait_text(drv, '角色权限管理')
        _wait_text(drv, '角色名称')
        _wait_text(drv, '超级管理员')
        time.sleep(1.0)
        _screenshot(drv, 'roles_light.png')
        _network_json(drv, 'roles')
        # 深色
        drv.execute_script("document.documentElement.classList.add('dark'); "
                           "document.body.classList.add('dark');")
        time.sleep(0.6)
        _screenshot(drv, 'roles_dark.png')
        drv.execute_script("document.documentElement.classList.remove('dark'); "
                           "document.body.classList.remove('dark');")

        # 2) 用户管理（userApi: GET /auth/users）
        _goto(drv, '/system-settings/iam/users')
        _wait_text(drv, '用户管理')
        _wait_text(drv, '用户名')
        _wait_text(drv, 'admin')
        time.sleep(1.0)
        _screenshot(drv, 'users_light.png')
        _network_json(drv, 'users')
        drv.execute_script("document.documentElement.classList.add('dark'); "
                           "document.body.classList.add('dark');")
        time.sleep(0.6)
        _screenshot(drv, 'users_dark.png')
        drv.execute_script("document.documentElement.classList.remove('dark'); "
                           "document.body.classList.remove('dark');")

        # 3) 系统选项·站点信息（optionApi: GET /api/option/）
        _goto(drv, '/system-settings/site/info')
        _wait_text(drv, '站点信息')
        _wait_text(drv, '站点名称')
        _wait_text(drv, '智能语音测试平台')
        time.sleep(1.0)
        _screenshot(drv, 'options_site_info_light.png')
        _network_json(drv, 'site_info')
        drv.execute_script("document.documentElement.classList.add('dark'); "
                           "document.body.classList.add('dark');")
        time.sleep(0.6)
        _screenshot(drv, 'options_site_info_dark.png')
        drv.execute_script("document.documentElement.classList.remove('dark'); "
                           "document.body.classList.remove('dark');")

        # 4) 系统选项·站点公告（optionApi: GET /api/option/ 同一端点）
        _goto(drv, '/system-settings/site/notice')
        _wait_text(drv, '站点公告')
        time.sleep(1.0)
        _screenshot(drv, 'options_site_notice_light.png')
        drv.execute_script("document.documentElement.classList.add('dark'); "
                           "document.body.classList.add('dark');")
        time.sleep(0.6)
        _screenshot(drv, 'options_site_notice_dark.png')
        drv.execute_script("document.documentElement.classList.remove('dark'); "
                           "document.body.classList.remove('dark');")

        # 5) OAuth 提供方（oauthProviderApi: GET /auth/oauth-providers）
        _goto(drv, '/system-settings/auth/oauth-providers')
        _wait_text(drv, 'OAuth 提供方')
        _wait_text(drv, '添加提供方')
        time.sleep(1.0)
        _screenshot(drv, 'oauth_light.png')
        _network_json(drv, 'oauth')
        drv.execute_script("document.documentElement.classList.add('dark'); "
                           "document.body.classList.add('dark');")
        time.sleep(0.6)
        _screenshot(drv, 'oauth_dark.png')
        drv.execute_script("document.documentElement.classList.remove('dark'); "
                           "document.body.classList.remove('dark');")

        # 6) LLM Provider 配置（ai-chat Agent 工作台 ProviderManager，llmProviderApi 直连）
        _goto(drv, '/ai-chat')
        _wait_text(drv, '灵犀Agent')
        time.sleep(1.0)
        _screenshot(drv, 'llm_provider_light.png')
        drv.execute_script("document.documentElement.classList.add('dark'); "
                           "document.body.classList.add('dark');")
        time.sleep(0.6)
        _screenshot(drv, 'llm_provider_dark.png')
        drv.execute_script("document.documentElement.classList.remove('dark'); "
                           "document.body.classList.remove('dark');")

        # 汇总 Network 证据
        _network_json(drv, 'final')
        print('[PASS] INT-651 browser walkthrough complete')
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
