# -*- coding: utf-8 -*-
"""INT-698 用户「显示名」编辑接线浏览器实测（React wiring，测试工程师验收）。

环境：
- dev server: http://localhost:5313（本 run 起，/api 代理 → 常驻 :5000）
- 常驻后端 :5000 AUTH_MODE=off → 无 token 时 hydrateSession 以 dev_user('*') 放行
- 页面: /system-settings/iam/users

验收标准核对（INT-698 卡内「可测的验收标准」）：
① pnpm build 零错误 / pnpm typecheck 通过 —— 脚本外已验证
② 编辑显示名保存后落库，刷新列表与抽屉显示新值
③ display_name 为空（未设置/清空）时列表显示名兜底 username，无「—」或空白
④ 创建用户填显示名，创建后列表立即显示新显示名
⑤ 回归：角色分配 / 状态切换 / 附加权限编辑不受影响

失败落 tests/ui/artifacts/int698/<步骤>/（截图 + page_source + console + network）。
"""
import json
import os
import time
import urllib.request
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5313')
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int698')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

# 每次 run 唯一探针用户（后端软删除后同名不可复用 → 时间戳后缀保证唯一）
_TS = datetime.now().strftime('%H%M%S')
PROBE = f'jxtest_dn698_{_TS}'
PROBE_EMAIL = f'{PROBE}@test.local'
PROBE_PASSWORD = 'Test1234!'

_STATE = {'driver': None, 'probe_id': None}


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


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 15).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.2)


def _save_evidence(name, drv):
    d = os.path.join(ARTIFACTS, name)
    os.makedirs(d, exist_ok=True)
    try:
        drv.save_screenshot(os.path.join(d, 'screenshot.png'))
        with open(os.path.join(d, 'page_source.html'), 'w', encoding='utf-8') as f:
            f.write(drv.page_source)
        with open(os.path.join(d, 'console.log'), 'w', encoding='utf-8') as f:
            for entry in drv.get_log('browser'):
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except Exception:
        pass


def _set_theme(drv, theme):
    drv.execute_script(
        "window.localStorage.setItem('iatp:theme:v1:mode', arguments[0])", theme)
    drv.refresh()
    WebDriverWait(drv, 15).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)


def _wait_toast(drv, text, timeout=10):
    try:
        WebDriverWait(drv, timeout).until(
            lambda d: any(text in (e.text or '') for e in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')))
    except Exception:
        toasts = [e.text for e in drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
        raise AssertionError(f'toast 未出现: {text!r}; 当前 toasts={toasts}') from None


def _toolbar_create_button(drv):
    return drv.find_element(By.XPATH, "//button[normalize-space(.)='+ 新建用户']")


def _search(drv, keyword):
    box = drv.find_element(By.XPATH, "//input[@placeholder='搜索用户名或邮箱']")
    box.clear()
    box.send_keys(keyword)
    time.sleep(1.2)


def _row_of(drv, username):
    xp = (
        f"//tr[.//div[contains(@class,'font-medium')][normalize-space(.)='{username}']]"
    )
    WebDriverWait(drv, 12).until(lambda d: len(d.find_elements(By.XPATH, xp)) > 0)
    return drv.find_element(By.XPATH, xp)


def _display_line(drv, username):
    """列表「用户名」单元格下的第二行（显示名）。"""
    xp = (
        f"//tr[.//div[contains(@class,'font-medium')][normalize-space(.)='{username}']]"
        f"//td[2]//div[contains(@class,'text-muted-foreground')]"
    )
    WebDriverWait(drv, 8).until(lambda d: len(d.find_elements(By.XPATH, xp)) > 0)
    return drv.find_element(By.XPATH, xp).text


def _status_badge(drv, username):
    xp = (
        f"//tr[.//div[contains(@class,'font-medium')][normalize-space(.)='{username}']]"
        f"//td[5]"
    )
    WebDriverWait(drv, 8).until(lambda d: len(d.find_elements(By.XPATH, xp)) > 0)
    return drv.find_element(By.XPATH, xp).text


def _open_row_menu(drv, username):
    btn = drv.find_element(By.XPATH,
        f"//button[@aria-label='用户操作：{username}']")
    drv.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
    time.sleep(0.3)
    btn.click()
    time.sleep(0.6)
    WebDriverWait(drv, 6).until(
        lambda d: len(d.find_elements(By.XPATH,
            "//*[@data-slot='dropdown-menu-item' or @role='menuitem']")) > 0)


def _click_menu_item(drv, text):
    xp = (
        "//*[(@data-slot='menu-item' or @data-slot='dropdown-menu-item' or @role='menuitem')"
        f" and normalize-space(.)='{text}']"
    )
    WebDriverWait(drv, 6).until(lambda d: len(d.find_elements(By.XPATH, xp)) > 0)
    el = drv.find_element(By.XPATH, xp)
    el.click()
    time.sleep(0.8)


def _drawer(drv):
    xp = "//div[@data-slot='sheet-content']"
    WebDriverWait(drv, 8).until(lambda d: len(d.find_elements(By.XPATH, xp)) > 0)
    return drv.find_element(By.XPATH, xp)


def _fill(drv, el_id, value):
    el = drv.find_element(By.ID, el_id)
    drv.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    el.click()
    el.send_keys(Keys.CONTROL, 'a')
    if value:
        el.send_keys(value)
    else:
        el.send_keys(Keys.BACKSPACE)
    time.sleep(0.3)


def _drawer_save(drv, label):
    btn = drv.find_element(By.XPATH, f"//div[@data-slot='sheet-content']//button[normalize-space(.)='{label}']")
    drv.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
    time.sleep(0.2)
    btn.click()
    time.sleep(1.0)


def _select_option(drv, slot_id, display_text):
    """Base UI Select：item 无 data-value，按可见文本匹配选项。"""
    trigger = drv.find_element(By.ID, slot_id)
    drv.execute_script("arguments[0].scrollIntoView({block:'center'});", trigger)
    trigger.click()
    time.sleep(0.6)
    xp = f"//*[@data-slot='select-item' and normalize-space(.)='{display_text}']"
    WebDriverWait(drv, 6).until(lambda d: len(d.find_elements(By.XPATH, xp)) > 0)
    drv.find_element(By.XPATH, xp).click()
    time.sleep(0.5)


def _network_users(drv):
    out = []
    try:
        for entry in drv.get_log('performance'):
            msg = json.loads(entry['message'])
            inner = msg.get('message', {})
            if inner.get('method') == 'Network.requestWillBeSent':
                p = inner.get('params', {})
                url = p.get('request', {}).get('url', '')
                if '/api/v1/auth/users' in url and '/encryption-key' not in url:
                    req = p.get('request', {})
                    out.append({
                        'url': url,
                        'method': req.get('method'),
                        'postData': req.get('postData'),
                    })
    except Exception as e:
        out.append({'error': str(e)})
    return out


def _backend_get(user_id):
    with urllib.request.urlopen(f'http://127.0.0.1:5000/api/v1/auth/users/{user_id}', timeout=8) as r:
        return json.loads(r.read().decode('utf-8'))['data']


def _backend_delete(user_id):
    req = urllib.request.Request(
        f'http://127.0.0.1:5000/api/v1/auth/users/{user_id}', method='DELETE')
    with urllib.request.urlopen(req, timeout=8) as r:
        return r.status


def run_steps(drv, check):
    # ---------- 会话引导：AUTH_MODE=off → dev_user 放行 ----------
    _goto(drv, '/system-settings/iam/users')
    WebDriverWait(drv, 20).until(
        lambda d: len(d.find_elements(By.XPATH,
            "//table//th[normalize-space(.)='用户名']")) > 0)

    # ============ ④ 创建用户带显示名 → 列表立即显示 ============
    _toolbar_create_button(drv).click()
    time.sleep(0.8)
    _fill(drv, 'user-username', PROBE)
    _fill(drv, 'user-display-name', '接线测试显示名')
    _fill(drv, 'user-email', PROBE_EMAIL)
    _fill(drv, 'user-password', PROBE_PASSWORD)
    _drawer_save(drv, '创建')
    _wait_toast(drv, '用户已创建')
    _search(drv, PROBE)
    row = _row_of(drv, PROBE)
    cells = row.find_elements(By.TAG_NAME, 'td')
    check('④ 创建后列表第二行=显示名「接线测试显示名」',
          len(cells) >= 2 and '接线测试显示名' in cells[1].text)
    with urllib.request.urlopen(
            f'http://127.0.0.1:5000/api/v1/auth/users?keyword={PROBE}', timeout=8) as r:
        items = json.loads(r.read().decode('utf-8'))['data']['items']
    assert items, 'probe 用户未在后端找到'
    _STATE['probe_id'] = items[0]['id']
    print(f'[INFO] probe user id={_STATE["probe_id"]}')
    _save_evidence('01_create_list_light', drv)
    _set_theme(drv, 'dark')
    _search(drv, PROBE)
    _save_evidence('01b_create_list_dark', drv)
    _set_theme(drv, 'light')
    _search(drv, PROBE)

    # ============ ② 编辑显示名 → 保存 → 落库 + 列表/抽屉/刷新回填 ============
    _open_row_menu(drv, PROBE)
    _click_menu_item(drv, '编辑')
    d = _drawer(drv)
    disp = d.find_element(By.ID, 'user-display-name')
    check('② 编辑态显示名输入已解除禁用（disabled=False）',
          not disp.get_attribute('disabled'),
          f'disabled={disp.get_attribute("disabled")}')
    check('② 编辑抽屉回填显示名=创建值',
          disp.get_attribute('value') == '接线测试显示名',
          f'value={disp.get_attribute("value")!r}')
    _save_evidence('02_edit_drawer_prefill', drv)
    _fill(drv, 'user-display-name', '接线测试改名')
    _drawer_save(drv, '保存')
    _wait_toast(drv, '用户已更新')
    _search(drv, PROBE)
    check('② 列表显示名更新为「接线测试改名」',
          '接线测试改名' in _display_line(drv, PROBE))
    b = _backend_get(_STATE['probe_id'])
    check('② 后端 display_name 已落库=接线测试改名',
          b.get('display_name') == '接线测试改名',
          f"display_name={b.get('display_name')!r}")
    _save_evidence('02b_list_after_rename_light', drv)

    # 刷新后列表仍显示新显示名 + 抽屉回填新显示名
    drv.refresh()
    WebDriverWait(drv, 15).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)
    _search(drv, PROBE)
    check('② 刷新后列表显示新显示名',
          '接线测试改名' in _display_line(drv, PROBE))
    _open_row_menu(drv, PROBE)
    _click_menu_item(drv, '编辑')
    d2 = _drawer(drv)
    check('② 刷新后抽屉回填新显示名',
          d2.find_element(By.ID, 'user-display-name').get_attribute('value') == '接线测试改名')
    _save_evidence('02c_drawer_after_refresh', drv)
    drv.find_element(By.XPATH, "//div[@data-slot='sheet-content']").send_keys(Keys.ESCAPE)
    time.sleep(0.8)
    _set_theme(drv, 'dark')
    _search(drv, PROBE)
    _save_evidence('02d_list_after_refresh_dark', drv)
    _set_theme(drv, 'light')
    _search(drv, PROBE)

    # ============ ③ 清空显示名 → 列表兜底 username，无「—」/空白 ============
    _open_row_menu(drv, PROBE)
    _click_menu_item(drv, '编辑')
    _fill(drv, 'user-display-name', '')
    _drawer_save(drv, '保存')
    _wait_toast(drv, '用户已更新')
    _search(drv, PROBE)
    line = _display_line(drv, PROBE)
    check('③ 清空后列表显示名兜底 username（无「—」/空白）',
          line == PROBE, f'display line={line!r}')
    b = _backend_get(_STATE['probe_id'])
    check('③ 后端 display_name 已清空（null）',
          b.get('display_name') in (None, ''), f"display_name={b.get('display_name')!r}")
    _save_evidence('03_cleared_list', drv)

    # ============ ⑤ 回归：状态切换（停用/启用） ============
    _open_row_menu(drv, PROBE)
    _click_menu_item(drv, '停用')
    _wait_toast(drv, '用户已更新')
    _search(drv, PROBE)
    check('⑤ 停用后状态徽标=停用', '停用' in _status_badge(drv, PROBE))
    b = _backend_get(_STATE['probe_id'])
    check('⑤ 后端 status=inactive', b.get('status') == 'inactive',
          f"status={b.get('status')!r}")
    _open_row_menu(drv, PROBE)
    _click_menu_item(drv, '启用')
    _wait_toast(drv, '用户已更新')
    _search(drv, PROBE)
    check('⑤ 启用后状态徽标=正常', '正常' in _status_badge(drv, PROBE))
    b = _backend_get(_STATE['probe_id'])
    check('⑤ 后端 status=active', b.get('status') == 'active',
          f"status={b.get('status')!r}")
    _save_evidence('05_status_toggle', drv)

    # ============ ⑤ 回归：角色分配（编辑抽屉改角色） ============
    _open_row_menu(drv, PROBE)
    _click_menu_item(drv, '编辑')
    _select_option(drv, 'user-role', '超级管理员')
    _drawer_save(drv, '保存')
    _wait_toast(drv, '用户角色已更新')
    _search(drv, PROBE)
    b = _backend_get(_STATE['probe_id'])
    check('⑤ 角色分配后端 role_id=1(admin)',
          b.get('role_id') == 1 and b.get('role_name') == 'admin',
          f"role_id={b.get('role_id')!r} role_name={b.get('role_name')!r}")
    _save_evidence('05_role_assignment', drv)

    # ============ ⑤ 回归：附加权限授予 ============
    _open_row_menu(drv, PROBE)
    _click_menu_item(drv, '编辑')
    _drawer(drv)
    # Base UI Checkbox：native input 视觉隐藏，需点击可见的 Root（data-slot='checkbox'）
    boxes = WebDriverWait(drv, 8).until(
        lambda d: d.find_elements(By.XPATH,
            "//div[@data-slot='sheet-content']//*[@data-slot='checkbox']"))
    before = _backend_get(_STATE['probe_id']).get('overrides') or []
    before_granted = sorted(o['code'] for o in before if o.get('granted'))
    target_box = None
    for bx in boxes:
        checked = bx.get_attribute('data-checked')
        if checked is None:
            target_box = bx
            break
    if target_box is None:
        check('⑤ 附加权限：无可勾选权限（跳过）', True)
    else:
        drv.execute_script("arguments[0].scrollIntoView({block:'center'});", target_box)
        time.sleep(0.3)
        target_box.click()
        time.sleep(0.5)
        _drawer_save(drv, '保存')
        _wait_toast(drv, '附加权限已授予')
        _search(drv, PROBE)
        b = _backend_get(_STATE['probe_id'])
        after_granted = sorted(o['code'] for o in (b.get('overrides') or []) if o.get('granted'))
        check('⑤ 附加权限授予后 overrides 增加',
              len(after_granted) > len(before_granted),
              f'before={before_granted} after={after_granted}')
        _save_evidence('05_permission_granted', drv)

    # ============ Network 证据（真实请求抓包） ============
    net = _network_users(drv)
    puts = [n for n in net if n.get('method') == 'PUT' and f'/auth/users/{_STATE["probe_id"]}' in n.get('url', '')]
    posts = [n for n in net if n.get('method') == 'POST' and n.get('url', '').endswith('/auth/users')]
    os.makedirs(ARTIFACTS, exist_ok=True)
    with open(os.path.join(ARTIFACTS, 'network_users.json'), 'w', encoding='utf-8') as f:
        json.dump({'puts': puts, 'posts': posts, 'all': net}, f, ensure_ascii=False, indent=2)
    rename_put = [p for p in puts if p.get('postData') and '接线测试改名' in p['postData']]
    clear_put = [p for p in puts if p.get('postData') and '"display_name":""' in p['postData']]
    toggle_put = [p for p in puts if p.get('postData') and 'inactive' in p['postData']]
    check('Network: 改名 PUT 携带 display_name',
          any('display_name' in p['postData'] for p in rename_put),
          json.dumps([p['postData'] for p in rename_put], ensure_ascii=False))
    check('Network: 清空 PUT 携带 display_name=""',
          any('display_name' in p['postData'] for p in clear_put),
          json.dumps([p['postData'] for p in clear_put], ensure_ascii=False))
    check('Network: 停用 PUT 仅 status 不含 display_name（缺省键不发送）',
          toggle_put and all('display_name' not in p['postData'] for p in toggle_put),
          json.dumps([p['postData'] for p in toggle_put], ensure_ascii=False))
    print(f'[INFO] network: {len(puts)} PUT, {len(posts)} POST (create) captured')


def run():
    drv = _driver()
    _STATE['driver'] = drv
    failures = []

    def check(name, cond, detail=''):
        tag = 'PASS' if cond else 'FAIL'
        print(f'[{tag}] {name}' + (f' — {detail}' if detail else ''))
        if not cond:
            failures.append(name)

    try:
        run_steps(drv, check)
    except Exception:
        _save_evidence('FAILURE_dump', drv)
        raise
    finally:
        pid = _STATE.get('probe_id')
        if pid:
            try:
                st = _backend_delete(pid)
                print(f'[CLEANUP] DELETE probe user {pid} → HTTP {st}')
            except Exception as e:
                print(f'[CLEANUP] DELETE probe user failed: {e}')
        try:
            drv.quit()
        except Exception:
            pass

    print('=' * 50)
    if failures:
        print(f'FAILED ({len(failures)}): {failures}')
        return 1
    print('ALL PASS')
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(run())
