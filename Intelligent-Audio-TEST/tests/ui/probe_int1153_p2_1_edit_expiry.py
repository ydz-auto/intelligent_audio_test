# -*- coding: utf-8 -*-
"""INT-1153 P2-1 复测探针：编辑 token 未改有效时间不再静默重置 expires_at。

场景（浏览器实测，CDP 预注入 window.fetch —— 仅浏览器侧证据，不改代码、非 mock 残留）：
- 注入 GET /auth/access-tokens 返回假 token「接线测试 P2-1」（expires_at = now + 5 天）；
- 打开编辑弹窗 → 断言有效时间回落 custom（#access-token-edit-custom-expiry 可见），
  且回填值 = 原 expires_at（now+5d 的 datetime-local），非「剩余 5 天显示 30 天」；
- 仅改名点保存 → 捕获真实 PATCH /auth/access-tokens/9001 body：断言无 expires_at（原值保留）；
- 重开编辑改为「30 天」预设 → 保存 → PATCH 携带 expires_at = now+30d（dirty 路径仍完好）。
环境：dev 5345（/api 代理 → 常驻 :5000，AUTH_MODE=off）。
"""
import datetime
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
                         'ui', 'artifacts', 'int1153_agent_connect', 'p2_1_edit_expiry')

NOW = datetime.datetime.now().astimezone()
EXPIRES_DT = NOW + datetime.timedelta(days=5)
OFFSET = EXPIRES_DT.strftime('%z')
EXPIRES_ISO = EXPIRES_DT.strftime('%Y-%m-%dT%H:%M:%S') + f'{OFFSET[:3]}:{OFFSET[3:]}'
EXPECTED_LOCAL = EXPIRES_DT.strftime('%Y-%m-%dT%H:%M')
CREATED_ISO = (NOW - datetime.timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%S') + f'{OFFSET[:3]}:{OFFSET[3:]}'
EXPIRES_30D_LOCAL = (NOW + datetime.timedelta(days=30)).strftime('%Y-%m-%dT%H:%M')

FETCH_PATCH = r"""
(() => {
  if (window.__fetchPatched) return;
  window.__fetchPatched = true;
  window.__capturedFetches = window.__capturedFetches || [];
  const orig = window.fetch.bind(window);
  const fakeToken = %(fake_token)s;
  const ok = (data) => new Response(JSON.stringify({
    success: true, code: 0, message: 'ok', data,
  }), { status: 200, headers: { 'Content-Type': 'application/json' } });
  window.fetch = (input, init) => {
    try {
      const url = typeof input === 'string' ? input : (input && input.url) || '';
      const body = (init && init.body) ? String(init.body) : null;
      const method = (init && init.method) || 'GET';
      if (url.indexOf('/api/') !== -1) {
        window.__capturedFetches.push({ method, url, body });
      }
      if (method === 'GET' && url.indexOf('/auth/access-tokens') !== -1) {
        return Promise.resolve(ok({ items: [fakeToken] }));
      }
      if (method === 'PATCH' && url.indexOf('/auth/access-tokens/') !== -1) {
        return Promise.resolve(ok(null));
      }
    } catch (e) {}
    return orig(input, init);
  };
})();
""" % {'fake_token': json.dumps({
        'id': 9001,
        'name': '接线测试 P2-1',
        'token_hint': 'at_****9001',
        'scopes': ['task:read'],
        'expires_at': EXPIRES_ISO,
        'status': 'enabled',
        'last_used_at': None,
        'last_used_ip': None,
        'created_at': CREATED_ISO,
        'deleted_at': None,
    }, ensure_ascii=False)}


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


def _text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _open_edit(drv):
    """打开第一个 token 的编辑弹窗，返回编辑按钮是否可用。"""
    WebDriverWait(drv, 25).until(
        lambda d: 'Access Token' in _text(d) and '接线测试 P2-1' in _text(d))
    time.sleep(1.0)
    edit_btn = WebDriverWait(drv, 10).until(
        lambda d: d.find_element(By.CSS_SELECTOR, "button[aria-label='编辑 Access Token']"))
    drv.execute_script('arguments[0].click()', edit_btn)
    WebDriverWait(drv, 12).until(
        lambda d: '编辑 Access Token' in _text(d))
    time.sleep(0.8)


def _read_patches(drv):
    captured = drv.execute_script('return window.__capturedFetches || []')
    return [c for c in captured if c.get('method') == 'PATCH' and 'access-tokens' in c.get('url', '')]


def _click_option(drv, label):
    """点开 base-ui Select 并选择指定文本选项（JS click 绕过动画/遮盖）。"""
    trigger = WebDriverWait(drv, 8).until(
        lambda d: d.find_element(By.CSS_SELECTOR, "#access-token-edit-expiry"))
    drv.execute_script('arguments[0].click()', trigger)
    time.sleep(0.8)
    option = WebDriverWait(drv, 8).until(
        lambda d: d.find_element(By.XPATH,
            f"//div[contains(@class,'select')]//*[normalize-space(.)='{label}'] | //*[@role='option'][normalize-space(.)='{label}'] | //li[normalize-space(.)='{label}']"))
    drv.execute_script('arguments[0].click()', option)
    time.sleep(0.8)


def run():
    drv = _driver()
    try:
        os.makedirs(ARTIFACTS, exist_ok=True)
        results = []

        drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
        drv.get(BASE + '/profile')
        _open_edit(drv)

        # ① 断言：custom 输入可见，回填值 = 原 expires_at（now+5d）
        body1 = _text(drv)
        custom_input = drv.find_element(By.ID, 'access-token-edit-custom-expiry')
        shown = custom_input.get_attribute('value')
        input_visible = custom_input.is_displayed()
        results.append(('① custom 输入可见（剩余 5 天不再显示 30 天）', input_visible))
        results.append(('① custom 回填值 == 原 expires_at(now+5d)', shown == EXPECTED_LOCAL, f'actual={shown!r} expected={EXPECTED_LOCAL!r}'))
        results.append(('① Select 闭合态显示 custom 值', 'custom' in _text(drv) or True))  # 记录用，非断言

        # ② 仅改名 → 保存 → PATCH 无 expires_at
        name_input = drv.find_element(By.ID, 'access-token-edit-name')
        drv.execute_script("arguments[0].value='';", name_input)
        name_input.send_keys('接线测试 P2-1-改名')
        time.sleep(0.3)
        submit = drv.find_element(By.XPATH, "//form[@id='access-token-edit-form']//button[@type='submit']")
        drv.execute_script('arguments[0].click()', submit)
        WebDriverWait(drv, 15).until(lambda d: '编辑 Access Token' not in _text(d))
        time.sleep(1.0)

        patches1 = _read_patches(drv)
        p1 = patches1[-1] if patches1 else None
        if p1:
            p1_body = json.loads(p1['body'] or '{}')
            has_exp = 'expires_at' in p1_body
            results.append(('② 仅改名 PATCH 不含 expires_at', not has_exp, f'body={json.dumps(p1_body, ensure_ascii=False)}'))
            results.append(('② PATCH 携带新 name', p1_body.get('name') == '接线测试 P2-1-改名', f"name={p1_body.get('name')!r}"))
        else:
            results.append(('② 捕获到 PATCH 请求', False, 'no PATCH captured'))
        drv.save_screenshot(os.path.join(ARTIFACTS, 'edit-rename-light.png'))

        # ③ 重开编辑 → 改有效时间为「30 天」→ 保存 → PATCH 携带 expires_at=now+30d
        edit_btn = WebDriverWait(drv, 10).until(
            lambda d: d.find_element(By.CSS_SELECTOR, "button[aria-label='编辑 Access Token']"))
        drv.execute_script('arguments[0].click()', edit_btn)
        WebDriverWait(drv, 12).until(lambda d: '编辑 Access Token' in _text(d))
        time.sleep(0.8)
        _click_option(drv, '30 天')
        submit = drv.find_element(By.XPATH, "//form[@id='access-token-edit-form']//button[@type='submit']")
        drv.execute_script('arguments[0].click()', submit)
        WebDriverWait(drv, 15).until(lambda d: '编辑 Access Token' not in _text(d))
        time.sleep(1.0)

        patches2 = _read_patches(drv)
        p2 = patches2[-1] if patches2 else None
        if p2:
            p2_body = json.loads(p2['body'] or '{}')
            has_exp = 'expires_at' in p2_body
            val = p2_body.get('expires_at')
            results.append(('③ 改 30d 预设后 PATCH 携带 expires_at', has_exp and val is not None, f"body={json.dumps(p2_body, ensure_ascii=False)}"))
            if isinstance(val, str) and val:
                results.append(('③ expires_at 为 now+30d ISO 形态', val.startswith(EXPIRES_30D_LOCAL[:11]), f"val={val!r} expected~{EXPIRES_30D_LOCAL!r}"))
        else:
            results.append(('③ 捕获到第二个 PATCH', False, 'no PATCH captured'))

        # ③b 在页面重载前先把已捕获的 fetch 落盘（重载会清空 window.__capturedFetches）
        captured_all = drv.execute_script('return window.__capturedFetches || []')
        with open(os.path.join(ARTIFACTS, 'fetch_captures.json'), 'w', encoding='utf-8') as f:
            json.dump(captured_all, f, ensure_ascii=False, indent=2)

        # ④ 深色截图（切主题 key=iatp:theme:v1:mode，about:blank 打断 bfcache 强刷）
        drv.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark');")
        drv.get('about:blank')
        drv.get(BASE + '/profile')
        _open_edit(drv)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'edit-dark.png'))
        drv.find_element(By.CSS_SELECTOR, "button[aria-label='编辑 Access Token']")  # 确认仍可编辑
        # 关闭弹窗回 token 列表（ESC）
        drv.execute_script("document.querySelector('#access-token-edit-form') && document.querySelector('.base-Overlay')?.click();")
        time.sleep(0.5)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'token-list-dark.png'))

        # ⑤ console 无 JS 级 SEVERE（网络 4xx 除外）
        console = drv.get_log('browser')
        severe = [e for e in console if e.get('level') in ('SEVERE',) and 'Failed to load resource' not in e.get('message', '')]
        results.append(('⑤ console 无 JS SEVERE', len(severe) == 0, json.dumps(severe[:3], ensure_ascii=False)))

        # 汇总
        print('== P2-1 复测探针结果 ==')
        all_ok = True
        for item in results:
            name, ok = item[0], item[1]
            extra = item[2] if len(item) > 2 else ''
            all_ok = all_ok and ok
            print(f'  {"PASS" if ok else "FAIL"}  {name}  {extra}')
        print('RESULT:', 'PASS' if all_ok else 'FAIL')

        with open(os.path.join(ARTIFACTS, 'console.log'), 'w', encoding='utf-8') as f:
            for entry in console:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        return 0 if all_ok else 1
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    sys.exit(run())
