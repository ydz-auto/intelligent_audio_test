# -*- coding: utf-8 -*-
"""INT-1290 日常任务重命名入口 — React页面工程师A 自测浏览器实测（独立脚本，非 pytest）。

连 frontend-react dev server（5392，代理到真实库栈 5700，AUTH_MODE=dev 表单登录）。
自建测试任务「接线测试-INT1290-*」，日常列表行菜单「重命名」+ 详情页「重命名」各驱动一次
保存，Network 证据经 Chrome performance log（Network.requestWillBeSent）采集真实 PUT /tasks/{id}；
列表/详情名称同步刷新；浅色+深色截图；结束前彻底删除测试任务（软删 + purge）。

用法：python verify_int1290_task_rename.py
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5392')
API = os.environ.get('API_BASE', 'http://127.0.0.1:5700/api/v1')
USER = os.environ.get('REAL_USER', '接线测试_admin')
PWD = os.environ.get('REAL_PWD', 'JieXianTest@2026')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1290_rename')

_token = None
_network = []


# ---------- 后端直连（建数据/清理，Bearer token 取自浏览器登录态） ----------
def api_json(method, path, body=None, token=None):
    headers = {'Content-Type': 'application/json'}
    tk = token or _token
    if tk:
        headers['Authorization'] = 'Bearer ' + tk
    req = urllib.request.Request(API + path, method=method, headers=headers)
    if body is not None:
        req.data = json.dumps(body).encode('utf-8')
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode('utf-8'))


def create_test_task(name):
    d = api_json('POST', '/tasks', {
        'name': name, 'case_ids': [], 'device_ids': [], 'api_ids': [],
        'config': {'rounds': 1, 'timeout': 60, 'retries': 0, 'concurrency': 1},
    })
    return d['data']['id']


def cleanup_task(task_id):
    try:
        api_json('DELETE', f'/tasks/{task_id}')
    except Exception:
        pass
    try:
        api_json('POST', '/tasks/purge', {'ids': [task_id]})
    except Exception:
        pass


# ---------- Selenium ----------
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


def _wait(drv, by, value, timeout=15):
    return WebDriverWait(drv, timeout).until(lambda d: d.find_elements(by, value))


def _click(drv, by, value, timeout=15):
    els = _wait(drv, by, value, timeout)
    for el in els:
        if el.is_displayed():
            try:
                el.click()
            except Exception:
                drv.execute_script("arguments[0].click();", el)
            return el
    els[0].click()
    return els[0]


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 15).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(2.0)


def _body_text(drv):
    return drv.find_element(By.TAG_NAME, 'body').text


def _save_screenshot(drv, name):
    try:
        os.makedirs(ARTIFACTS, exist_ok=True)
        drv.save_screenshot(os.path.join(ARTIFACTS, name + '.png'))
    except Exception:
        pass


def _drain_network(drv):
    batch = []
    for entry in drv.get_log('performance'):
        try:
            outer = json.loads(entry['message'])
            inner = outer.get('message', {})
            method = inner.get('method', '')
            params = inner.get('params', {})
            if method == 'Network.requestWillBeSent':
                req = params.get('request', {})
                batch.append({
                    'method': req.get('method', ''),
                    'url': req.get('url', ''),
                    'postData': req.get('postData', ''),
                })
        except Exception:
            pass
    _network.extend(batch)
    return batch


def _reqs(suffix, method=None):
    out = []
    for r in _network:
        if suffix in r['url']:
            if method and r['method'] != method:
                continue
            out.append(r)
    return out


def _toast_present(drv, text, timeout=6):
    try:
        WebDriverWait(drv, timeout).until(
            lambda d: text in d.find_element(By.TAG_NAME, 'body').text)
        return True
    except Exception:
        return False


def _row_by_name(drv, name_fragment):
    rows = drv.find_elements(By.XPATH, f"//tbody/tr[.//span[contains(text(),'{name_fragment}')]]")
    return rows[0] if rows else None


def _open_row_menu(drv, row):
    btn = row.find_element(By.XPATH, ".//button[@aria-label='任务操作']")
    btn.click()
    time.sleep(0.6)


def _menu_click(drv, label):
    els = drv.find_elements(By.XPATH, f"//*[@role='menuitem' and normalize-space(.)='{label}']")
    if not els:
        els = drv.find_elements(By.XPATH, f"//*[@role='menuitem'][contains(.,'{label}')]")
    if not els:
        return False
    for el in els:
        if el.is_displayed():
            el.click()
            return True
    els[0].click()
    return True


def _set_theme(drv, mode):
    """写主题持久化 key + about:blank 打断 bfcache 强刷（iatp:theme:v1:mode）。"""
    drv.execute_script(f"localStorage.setItem('iatp:theme:v1:mode','{mode}');")
    drv.get('about:blank')
    time.sleep(0.5)


def _rename_in_dialog(drv, new_name):
    """在重命名弹窗里替换输入并点「确定」，返回是否成功。"""
    inp = _wait(drv, By.CSS_SELECTOR, '#rename-task-input', timeout=10)
    inp = inp[0]
    time.sleep(0.4)  # 等弹窗打开动画 + 初值 effect 完成
    # 全选替换（Ctrl+A 对 base-ui input 兼容性更好）
    inp.send_keys(Keys.CONTROL, 'a')
    inp.send_keys(new_name)
    time.sleep(0.3)
    # 点「确定」
    btns = [b for b in drv.find_elements(By.XPATH, "//button[contains(.,'确定')]")
            if b.is_displayed()]
    if not btns:
        return False
    btns[0].click()
    time.sleep(0.5)
    return True


RESULTS = []


def check(name, ok, detail=''):
    RESULTS.append((name, bool(ok), detail))
    print(('PASS' if ok else 'FAIL') + ' | ' + name + ((' | ' + detail) if detail else ''))


def main():
    ts = int(time.time())
    orig = f'接线测试-INT1290-初始-{ts}'
    renamed_list = f'接线测试-INT1290-列表改名-{ts}'
    renamed_detail = f'接线测试-INT1290-详情改名-{ts}'

    drv = _driver()
    task_id = None
    try:
        # ---------- 表单登录（真实库栈 AUTH_MODE=dev 加密链路） ----------
        _goto(drv, '/login')
        _wait(drv, By.CSS_SELECTOR, '#username', timeout=15)
        drv.find_element(By.CSS_SELECTOR, '#username').send_keys(USER)
        drv.find_element(By.CSS_SELECTOR, '#password').send_keys(PWD)
        _click(drv, By.XPATH, "//button[@type='submit']")
        WebDriverWait(drv, 20).until(
            lambda d: '/dashboard' in d.current_url or '/tasks' in d.current_url)
        time.sleep(2.0)
        global _token
        _token = drv.execute_script("return localStorage.getItem('iatp:auth:token:v1');")
        check('登录成功（真实库栈 dev 加密链路）', bool(_token) and _token != 'null',
              f'token_len={len(_token or "")}')
        if not _token or _token == 'null':
            print('[FATAL] no token; login failed')
            return 1

        # ---------- 自建测试任务 ----------
        task_id = create_test_task(orig)
        check('自建测试任务（POST /tasks，接线测试 前缀）', bool(task_id),
              f'id={task_id} name={orig}')

        # ---------- 日常列表行菜单「重命名」 → 弹窗 → PUT → 列表刷新 ----------
        _goto(drv, '/tasks/daily')
        _wait(drv, By.XPATH, '//tbody/tr', timeout=25)
        body = _body_text(drv)
        check('日常列表渲染真实数据', orig in body, '列表含自建任务')

        row = _row_by_name(drv, orig)
        check('前置：找到自建任务行', row is not None)
        if row:
            _drain_network(drv)
            _open_row_menu(drv, row)
            time.sleep(0.6)
            _save_screenshot(drv, 'daily_list_menu_light')
            menu_ok = _menu_click(drv, '重命名')
            check('行菜单含「重命名」入口', menu_ok)
            # 弹窗出现
            dialog_ok = len(_wait(drv, By.CSS_SELECTOR, '#rename-task-input', timeout=8)) > 0
            check('点击「重命名」弹名称编辑弹窗', dialog_ok)
            if dialog_ok:
                time.sleep(0.6)  # 等弹窗开合动画稳定再截
                _save_screenshot(drv, 'daily_rename_dialog_light')
                inp_ok = _rename_in_dialog(drv, renamed_list)
                check('保存名称（点「确定」）', inp_ok)
                time.sleep(3.0)
                _drain_network(drv)
                preq = _reqs(f'/api/v1/tasks/{task_id}', 'PUT')
                ok = len(preq) > 0
                detail = ''
                if preq:
                    pd = preq[-1].get('postData') or ''
                    ok = ok and f'接线测试-INT1290-列表改名-{ts}' in pd and 'name' in pd
                    detail = f'body={pd[:120]}'
                check('保存发真实 PUT /tasks/{id}（Network）', ok, detail)
                check('toast「任务名称已更新」', _toast_present(drv, '任务名称已更新'))
                # 列表名称同步刷新
                refresh_ok = False
                try:
                    WebDriverWait(drv, 12).until(
                        lambda d: renamed_list in d.find_element(By.TAG_NAME, 'body').text)
                    refresh_ok = True
                except Exception:
                    pass
                check('列表名称同步刷新（显示新名）', refresh_ok)
            _save_screenshot(drv, 'daily_list_renamed_light')
        # ---------- 详情页「重命名」入口 → 弹窗 → PUT → 详情刷新 ----------
        _goto(drv, f'/tasks/{task_id}')
        _wait(drv, By.XPATH, f"//*[contains(.,'{renamed_list}')]", timeout=20)
        time.sleep(1.0)
        body = _body_text(drv)
        check('详情页渲染新名', renamed_list in body)
        rename_btn = drv.find_elements(By.XPATH,
            "//*[contains(@class,'actions')]//button[normalize-space(.)='重命名']"
            "| //button[contains(.,'重命名')]")
        check('详情页提供「重命名」入口', any(b.is_displayed() for b in rename_btn))
        if rename_btn and any(b.is_displayed() for b in rename_btn):
            for b in rename_btn:
                if b.is_displayed():
                    b.click()
                    break
            time.sleep(0.6)
            dialog_ok = len(_wait(drv, By.CSS_SELECTOR, '#rename-task-input', timeout=8)) > 0
            check('详情点击「重命名」弹名称编辑弹窗', dialog_ok)
            if dialog_ok:
                _rename_in_dialog(drv, renamed_detail)
                time.sleep(3.0)
                _drain_network(drv)
                preq = _reqs(f'/api/v1/tasks/{task_id}', 'PUT')
                ok = len(preq) > 0
                detail = ''
                if preq:
                    pd = preq[-1].get('postData') or ''
                    ok = ok and renamed_detail in pd
                    detail = f'body={pd[:120]}'
                check('详情保存发真实 PUT /tasks/{id}（Network）', ok, detail)
                check('toast「任务名称已更新」', _toast_present(drv, '任务名称已更新'))
                refresh_ok = False
                try:
                    WebDriverWait(drv, 12).until(
                        lambda d: renamed_detail in d.find_element(By.TAG_NAME, 'body').text)
                    refresh_ok = True
                except Exception:
                    pass
                check('详情名称同步刷新（显示新名）', refresh_ok)
            _save_screenshot(drv, 'detail_renamed_light')

        # ---------- 深色截图（列表行菜单 + 弹窗 + 详情按钮） ----------
        _set_theme(drv, 'dark')
        _goto(drv, '/tasks/daily')
        _wait(drv, By.XPATH, '//tbody/tr', timeout=25)
        time.sleep(1.0)
        row = _row_by_name(drv, renamed_detail)
        if row:
            _open_row_menu(drv, row)
            time.sleep(0.6)
            _save_screenshot(drv, 'daily_list_menu_dark')
            _menu_click(drv, '重命名')
            _wait(drv, By.CSS_SELECTOR, '#rename-task-input', timeout=8)
            time.sleep(0.6)
            _save_screenshot(drv, 'daily_rename_dialog_dark')
            # 关闭弹窗（Esc）
            drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            time.sleep(0.6)
        _goto(drv, f'/tasks/{task_id}')
        _wait(drv, By.XPATH, f"//*[contains(.,'{renamed_detail}')]", timeout=20)
        time.sleep(1.0)
        _save_screenshot(drv, 'detail_renamed_dark')

        # ---------- 后端权威核对：名称已持久化 ----------
        try:
            d = api_json('GET', f'/tasks/{task_id}')
            cur_name = d.get('data', {}).get('name', '')
            check('后端 GET /tasks/{id} 名称已持久化', cur_name == renamed_detail,
                  f'cur={cur_name!r}')
        except Exception as e:
            check('后端 GET /tasks/{id} 名称已持久化', False, str(e)[:100])

    finally:
        drv.quit()

    # ---------- 清理测试数据 ----------
    if task_id:
        cleanup_task(task_id)
    try:
        left = api_json('GET', '/tasks?search=' + urllib.parse.quote('接线测试-INT1290'))
        left_n = len(left.get('data', {}).get('items', []))
    except Exception:
        left_n = -1
    check('测试数据已彻底删除（无 INT1290 残留）', left_n == 0, f'left={left_n}')

    print('\n===== INT-1290 自测结果 =====')
    for name, ok, detail in RESULTS:
        print(('PASS' if ok else 'FAIL') + ' | ' + name)
    failed = [r for r in RESULTS if not r[1]]
    print(f'TOTAL {len(RESULTS)} / PASS {len(RESULTS) - len(failed)} / FAIL {len(failed)}')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
