# -*- coding: utf-8 -*-
"""INT-1153 P1-2 探针：创建对话框提交的 expires_at 载荷形态（0=永不过期 / ISO 字符串）。

环境：dev 5345（/api 代理 → 常驻 :5000，AUTH_MODE=off）。
后端 access-token 端点当前 404 → 提交必然失败，但请求体仍真实发出；
本探针用 window.fetch 打点捕获 POST /auth/access-tokens 的 body，断言
expires_at 为「YYYY-MM-DDTHH:mm」ISO 形态（而非旧版 Unix 秒整数，后者后端 400）。
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

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5345')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ARTIFACTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         'ui', 'artifacts', 'int1153_agent_connect', 'p1_2_expiry_wire')

FETCH_PATCH = r"""
(() => {
  if (window.__fetchPatched) return;
  window.__fetchPatched = true;
  window.__capturedFetches = window.__capturedFetches || [];
  const orig = window.fetch.bind(window);
  window.fetch = (input, init) => {
    try {
      const url = typeof input === 'string' ? input : (input && input.url) || '';
      const body = (init && init.body) ? String(init.body) : null;
      const method = (init && init.method) || 'GET';
      if (url.indexOf('/api/') !== -1) {
        window.__capturedFetches.push({ method, url, body });
      }
    } catch (e) {}
    return orig(input, init);
  };
})();
"""


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
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


def run():
    drv = _driver()
    try:
        os.makedirs(ARTIFACTS, exist_ok=True)
        # 用 CDP 在文档加载前注入 fetch 打点，确保应用模块的 fetch 全部被捕获
        drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
        drv.get(BASE + '/profile')
        WebDriverWait(drv, 25).until(
            lambda d: 'Access Token' in (d.execute_script('return document.body.textContent || ""')))
        time.sleep(1.5)

        # 打开创建对话框
        drv.find_element(By.XPATH, "//button[.//text()[normalize-space()='创建 Access Token']]").click()
        WebDriverWait(drv, 12).until(
            lambda d: 'Token 明文只显示一次' in (d.execute_script('return document.body.textContent || ""')))
        # 填名称；有效时间保持默认预设 30d；勾选一个权限点（task:read）以满足必选
        name = drv.find_element(By.ID, 'access-token-name')
        name.send_keys('接线测试-expiry-ISO')
        time.sleep(0.3)
        scope = WebDriverWait(drv, 8).until(
            lambda d: d.find_element(By.CSS_SELECTOR, "[id='perm-task:read']"))
        drv.execute_script('arguments[0].click()', scope)   # JS click 绕过动画/遮盖
        time.sleep(0.8)
        body_now = drv.execute_script('return document.body.textContent || ""')
        print('scopes selected indicator:', '已选 1 项' in body_now, '| 已选' , [x for x in ['已选 1 项','已选 2 项','已选 0 项'] if x in body_now])
        # 提交（表单内 type=submit；JS click 防动画吞点击）
        submit = WebDriverWait(drv, 8).until(
            lambda d: d.find_element(By.XPATH, "//form[.//*[@id='access-token-name']]//button[@type='submit']"))
        drv.execute_script('arguments[0].click()', submit)
        time.sleep(3.0)

        captured = drv.execute_script('return window.__capturedFetches || []')
        posts = [c for c in captured if c.get('method') == 'POST' and 'access-tokens' in c.get('url', '')]
        print('captured POST /auth/access-tokens:', json.dumps(posts, ensure_ascii=False, indent=2))

        ok = False
        detail = ''
        for p in posts:
            try:
                body = json.loads(p['body'] or '{}')
            except Exception as e:
                detail = f'body parse error: {e}'; continue
            val = body.get('expires_at')
            if isinstance(val, str) and val and val[0].isdigit() and 'T' in val:
                ok = True
                detail = f'expires_at={val!r} (ISO string, P1-2 OK)'
            else:
                detail = f'expires_at={val!r} (NOT ISO string — P1-2 FAIL)'
        print('RESULT:', 'PASS' if ok else 'FAIL')
        print(detail)
        with open(os.path.join(ARTIFACTS, 'fetch_captures.json'), 'w', encoding='utf-8') as f:
            json.dump(captured, f, ensure_ascii=False, indent=2)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'screenshot.png'))
        with open(os.path.join(ARTIFACTS, 'console.log'), 'w', encoding='utf-8') as f:
            for entry in drv.get_log('browser'):
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        return 0 if ok else 1
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    sys.exit(run())
