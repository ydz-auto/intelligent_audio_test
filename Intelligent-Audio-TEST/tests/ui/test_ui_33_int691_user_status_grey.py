# -*- coding: utf-8 -*-
"""INT-691 新建用户状态选择不落库（前端方案）浏览器验收（真实 Chrome headless）。

验收标准（总控派发 2026-10-18 07:20 CST）：
  新建用户抽屉「状态」字段置灰固定「正常」并注明「创建后可在列表中启用/停用」；
  不改后端契约、不写兼容层；编辑态状态保持可选并随 PUT 落库。

覆盖点：
  1. 新建态状态下拉 disabled，固定显示「正常」（USER_STATUS_META 中文标签兜底）；
  2. 新建态注明「创建后可在列表中启用/停用」；
  3. 新建态点击状态下拉不展开（disabled 下拉无 popup）；
  4. 真实创建用户 → 捕获 POST /auth/users 请求体不含 status 字段（修复目标：交互不再静默丢失）；
  5. 编辑态状态下拉可用（非 disabled），点击可展开正常/停用/锁定，且无新建态说明文案；
  6. 创建成功后新用户按缺省 active 落库，列表中状态显示「正常」。

环境：dev server :5273（本 worktree 代码，rsbuild proxy /api → 常驻后端 :5000，
AUTH_MODE=off dev_user '*' 全放行）。测试创建的用户在 finally 中经 DELETE /auth/users/{id} 清理。
"""
import json
import os
import time
import urllib.parse
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5273')
GATEWAY = os.environ.get('GATEWAY_BASE', 'http://127.0.0.1:5000')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ARTIFACTS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         'artifacts', 'int691_user_status')
os.makedirs(ARTIFACTS, exist_ok=True)

CREATE_NOTE = '创建后可在列表中启用/停用'
results = []


def check(name, condition, detail=''):
    status = 'PASS' if condition else 'FAIL'
    print(f'[{status}] {name} {detail}')
    results.append((status, name, detail))
    return condition


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
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r'SOFTWARE\Google\Chrome\BLBeacon') as k:
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
                    cands.append(
                        (tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
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
    time.sleep(1.2)


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _wait_text(drv, text, timeout=20):
    WebDriverWait(drv, timeout).until(lambda d: text in _body_text(drv))


def _wait_text_gone(drv, text, timeout=15):
    WebDriverWait(drv, timeout).until(lambda d: text not in _body_text(drv))


def _screenshot(drv, name):
    d = os.path.join(ARTIFACTS, name)
    drv.save_screenshot(d)
    print(f'[shot] {d}')


def _set_theme_class(drv, cls):
    drv.execute_script(
        f'document.documentElement.classList.remove("light","dark");'
        f'document.documentElement.classList.add("{cls}");')
    time.sleep(0.6)


def _enter_workbench(drv):
    drv.execute_script('try { window.localStorage.clear() } catch (e) {}')
    _goto(drv, '/login')
    _wait_text(drv, '进入工作台')
    drv.find_element(By.XPATH, "//button[contains(., '进入工作台')]").click()
    WebDriverWait(drv, 20).until(lambda d: '/dashboard' in d.current_url)
    _wait_text(drv, '工作台', timeout=20)


def _click_button_containing(drv, text):
    """按文本找 <button> 并 JS 点击（规避浮层/虚元素遮挡）。"""
    from selenium.webdriver.support import expected_conditions as EC
    btn = WebDriverWait(drv, 15).until(
        EC.presence_of_element_located(
            (By.XPATH,
             f"//button[contains(normalize-space(.), {json.dumps(text, ensure_ascii=False)})]"))
    )
    drv.execute_script('arguments[0].scrollIntoView({block:"center"});', btn)
    drv.execute_script('arguments[0].click();', btn)
    return btn


def _click_menuitem(drv, text):
    """base-ui Menu 项渲染为 [role=menuitem] 的 div（非 button），按文本 JS 点击。"""
    from selenium.webdriver.support import expected_conditions as EC
    item = WebDriverWait(drv, 15).until(
        EC.presence_of_element_located(
            (By.XPATH,
             f"//*[@role='menuitem' and contains(normalize-space(.), {json.dumps(text, ensure_ascii=False)})]")))
    drv.execute_script('arguments[0].scrollIntoView({block:"center"});', item)
    drv.execute_script('arguments[0].click();', item)
    return item


def _status_trigger(drv):
    return drv.find_element(By.CSS_SELECTOR, '#user-status')


def _select_content_present(drv):
    """base-ui Select popup 经 portal 渲染；返回 select-content 是否存在。"""
    els = drv.execute_script(
        "return Array.from(document.querySelectorAll('[data-slot=select-content]'))"
        ".filter(e => { const r=e.getBoundingClientRect(); return r.width>0 && r.height>0; }).length")
    return els > 0


def _network_json(drv, label):
    entries = drv.execute_script(
        'return performance.getEntriesByType("resource")'
        '.map(e => ({name: e.name, duration: Math.round(e.duration)}))')
    apis = [e for e in entries
            if any(x in e['name'] for x in
                   ['/auth/users', '/auth/roles', '/auth/mode', '/auth/me'])]
    with open(os.path.join(ARTIFACTS, f'network_{label}.json'), 'w',
              encoding='utf-8') as f:
        json.dump(apis, f, ensure_ascii=False, indent=2)
    print(f'[network] {label}: {len(apis)} api entries')
    return apis


def _inject_fetch_hook(drv):
    drv.execute_script("""
      window.__reqLog = [];
      const _f = window.fetch;
      window.fetch = function(...args) {
        try {
          const url = typeof args[0] === 'string' ? args[0]
                    : (args[0] && args[0].url) || '';
          if (String(url).includes('/auth/users')) {
            let body = null;
            if (args[1] && args[1].body) {
              body = typeof args[1].body === 'string'
                     ? args[1].body : JSON.stringify(args[1].body);
            }
            window.__reqLog.push({ url: String(url),
                                  method: (args[1] && args[1].method) || 'GET',
                                  body });
          }
        } catch (e) {}
        return _f.apply(this, args);
      };
    """)


def _backend_delete_user(username):
    """teardown：按用户名找用户并 DELETE。返回 (ok, detail)。"""
    try:
        url = f'{GATEWAY}/api/v1/auth/users?keyword={urllib.parse.quote(username)}'
        with urllib.request.urlopen(url, timeout=8) as r:
            data = json.loads(r.read().decode('utf-8'))
        for u in data.get('data', {}).get('items', []):
            if u.get('username') == username:
                req = urllib.request.Request(
                    f'{GATEWAY}/api/v1/auth/users/{u["id"]}', method='DELETE')
                with urllib.request.urlopen(req, timeout=8) as r2:
                    body = json.loads(r2.read().decode('utf-8'))
                return True, f'deleted id={u["id"]} resp={json.dumps(body, ensure_ascii=False)[:120]}'
        return False, f'user {username} not found in list'
    except Exception as e:
        return False, f'exc: {e}'


def main():
    created_username = ''
    drv = _driver()
    ok_all = True
    try:
        _enter_workbench(drv)
        _network_json(drv, 'workbench')

        # ===== 用户管理页 =====
        _goto(drv, '/system-settings/iam/users')
        _wait_text(drv, '用户管理')
        _wait_text(drv, '用户名')
        _wait_text(drv, 'dev_user')
        time.sleep(1.0)
        _network_json(drv, 'users')
        ok_all &= check('前置-用户管理真实列表（dev_user）',
                        'dev_user' in _body_text(drv))

        _inject_fetch_hook(drv)

        # ===== 新建抽屉：状态字段置灰固定「正常」 =====
        _click_button_containing(drv, '+ 新建用户')
        _wait_text(drv, '新建用户')
        _wait_text(drv, CREATE_NOTE)
        time.sleep(0.8)

        t = _status_trigger(drv)
        disabled = drv.execute_script('return arguments[0].disabled === true || '
                                      'arguments[0].getAttribute("data-disabled") != null', t)
        ok_all &= check('新建态-状态下拉 disabled', disabled,
                        f'disabled={disabled}')
        ok_all &= check('新建态-固定显示「正常」', '正常' in t.text.strip(),
                        f'trigger text="{t.text.strip()}"')
        ok_all &= check('新建态-注明创建后可在列表中启用/停用',
                        CREATE_NOTE in _body_text(drv))

        # 点击状态下拉不应展开
        drv.execute_script('arguments[0].click();', t)
        time.sleep(0.8)
        popup_open = _select_content_present(drv)
        ok_all &= check('新建态-点击不展开下拉', not popup_open,
                        f'select-content visible={popup_open}')

        _screenshot(drv, 'create_light.png')
        _network_json(drv, 'create_drawer')
        _set_theme_class(drv, 'dark')
        _screenshot(drv, 'create_dark.png')
        _set_theme_class(drv, 'light')

        # ===== 真实创建用户 + POST 请求体断言 =====
        created_username = f'int691t{int(time.time())}'
        email = f'{created_username}@example.test'
        pwd = 'Int691@test123'

        drv.find_element(By.CSS_SELECTOR, '#user-username').send_keys(created_username)
        drv.find_element(By.CSS_SELECTOR, '#user-email').send_keys(email)
        drv.find_element(By.CSS_SELECTOR, '#user-password').send_keys(pwd)
        time.sleep(0.3)
        _click_button_containing(drv, '创建')
        _wait_text_gone(drv, '创建平台账号并分配初始角色')  # 抽屉关闭（标题文案在工具行按钮中始终存在，改用抽屉描述）
        time.sleep(1.5)

        posts = drv.execute_script(
            "return (window.__reqLog || []).filter(r => (r.method||'GET')==='POST')")
        ok_all &= check('真实创建-POST /auth/users 已发出', len(posts) >= 1,
                        f'count={len(posts)}')
        body_has_status = any(
            ('status' in json.loads(p['body'] or '{}')) for p in posts)
        ok_all &= check('真实创建-POST 请求体不含 status 字段', not body_has_status,
                        f'posts={json.dumps(posts, ensure_ascii=False)}')

        # 列表里出现新用户，状态显示「正常」
        search = drv.find_element(By.CSS_SELECTOR, "input[placeholder*='搜索用户名']")
        search.clear()
        search.send_keys(created_username)
        time.sleep(1.5)
        _wait_text(drv, created_username, timeout=15)
        time.sleep(0.5)
        ok_all &= check('真实创建-新用户落库且状态「正常」',
                        created_username in _body_text(drv) and '正常' in _body_text(drv),
                        f'body has user={created_username in _body_text(drv)}, 正常={"正常" in _body_text(drv)}')

        # ===== 编辑抽屉：状态下拉可用 + 无新建态说明 =====
        drv.find_element(By.CSS_SELECTOR, "input[placeholder*='搜索用户名']").clear()
        _goto(drv, '/system-settings/iam/users')
        _wait_text(drv, created_username, timeout=20)
        time.sleep(1.0)
        drv.find_element(By.XPATH,
                         f"//button[contains(@aria-label, '用户操作：{created_username}')]").click()
        time.sleep(0.6)
        _click_menuitem(drv, '编辑')
        _wait_text(drv, '编辑用户')
        time.sleep(0.8)

        t2 = _status_trigger(drv)
        disabled2 = drv.execute_script(
            'return arguments[0].disabled === true || '
            'arguments[0].getAttribute("data-disabled") != null', t2)
        ok_all &= check('编辑态-状态下拉可用（非 disabled）', not disabled2,
                        f'disabled={disabled2}')
        ok_all &= check('编辑态-无新建态说明文案', CREATE_NOTE not in _body_text(drv))

        drv.execute_script('arguments[0].click();', t2)
        time.sleep(0.8)
        popup_open2 = _select_content_present(drv)
        items_text = drv.execute_script(
            "return Array.from(document.querySelectorAll('[data-slot=select-item]'))"
            ".map(e => e.textContent.trim()).filter(Boolean)")
        ok_all &= check('编辑态-点击展开下拉（正常/停用/锁定）',
                        popup_open2 and '停用' in items_text and '锁定' in items_text,
                        f'visible={popup_open2} items={items_text}')
        _screenshot(drv, 'edit_status_popup_light.png')
        _set_theme_class(drv, 'dark')
        time.sleep(0.5)
        _screenshot(drv, 'edit_status_popup_dark.png')
        _set_theme_class(drv, 'light')

        _network_json(drv, 'final')

        fails = [r for r in results if r[0] == 'FAIL']
        print(f'[SUMMARY] total={len(results)} fail={len(fails)}')
        for f in fails:
            print(f'  FAIL {f[1]}: {f[2]}')
        ok_all = len(fails) == 0
        print('[PASS] INT-691 browser walkthrough complete' if ok_all
              else '[FAIL] INT-691 browser walkthrough FAILED')
    finally:
        # 测试数据卫生：清理创建的用户
        if created_username:
            ok, detail = _backend_delete_user(created_username)
            print(f'[cleanup] {created_username} -> ok={ok} {detail}')
        try:
            drv.quit()
        except Exception:
            pass
    return 0 if ok_all else 1


if __name__ == '__main__':
    raise SystemExit(main())
