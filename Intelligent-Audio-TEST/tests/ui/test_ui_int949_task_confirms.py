# -*- coding: utf-8 -*-
"""INT-949 任务列表/详情危险操作缺确认弹窗 — 浏览器实测（独立脚本，非 pytest）。

连 frontend-react dev server（5331，代理到常驻后端 5000，AUTH_MODE=off dev_user '*'）。
自建测试任务（接线测试-INT949-*）驱动页面操作；Network 证据经 Chrome performance log
（Network.requestWillBeSent）采集；结束前彻底删除测试任务（软删 + purge）。

Chrome headless 长会话不稳（多次 invalid session id），按阶段分用独立浏览器实例。

核对项（09_任务域 §5.8/§5.9/§5.10 + 旧 Vue 基线）：
  C1 行删除：确认弹窗「将把 1 个任务移入回收站，可在回收站恢复。」；取消 0 请求；确认 DELETE /tasks/{id}
  C2 批量删除：确认弹窗「将把 {n} 个任务移入回收站…」；取消 0 请求；确认 POST /tasks/batch-action
  C3 行恢复：确认弹窗「确定要恢复该任务吗？」；取消 0 请求；确认 POST /tasks/{id}/restore
  C4 行彻底删除：确认弹窗「将永久删除 1 个任务…」；取消 0 请求；确认 DELETE /tasks/{id}/purge
  C5 批量恢复：确认弹窗「确定要恢复选中的 {n} 个任务吗？」；取消 0 请求；确认 POST /tasks/restore
  C6 批量彻底删除：确认弹窗「将永久删除 {n} 个任务…」；取消 0 请求；确认 POST /tasks/purge
  C7 移除用例（多用例）：确认弹窗 §5.9 阶段文案；取消 0 请求；确认 DELETE /tasks/{id}/cases/{caseId}
  C8 末例「仅移除用例」：首段确认 → 二次弹窗文案；DELETE /cases 且无 stop
  C9 末例「移除并停止任务」：DELETE /cases + POST /tasks/{id}/stop
  C10 批量发布：确认弹窗 §5.3 文案；取消 0 请求；确认开首个任务发布弹窗
  C11 详情停止：确认弹窗 §5.8 文案；取消 0 请求；确认 POST /tasks/{id}/stop
  C12 详情暂停：确认弹窗「确定要暂停该测试任务吗？」；取消 0 请求；确认 POST /tasks/{id}/control
  C13 详情继续：确认弹窗「确定要继续该测试任务吗？」；取消 0 请求；确认 POST /tasks/{id}/control

共享库无 running/paused 任务（INT-932 P3-1 同口径），C11/C12/C13 用 window.fetch 打点伪造
详情 GET /tasks/{id} 返回指定 execution_status（仅 GET 打点，stop/control 请求仍发真实后端）。

用法：python tests/ui/test_ui_int949_task_confirms.py
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
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5331')
API = os.environ.get('API_BASE', 'http://localhost:5000/api/v1')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int949_confirms')

CASE_A = '74dae4e2-1054-4f35-ba18-17f925d4e761'  # ui467_私有用例
CASE_B = '1cb1a7ec-94fb-4a7a-8c5d-de091f39cb95'  # ui467_私有用例

_network = []
_evidence = []  # 关键 mutation 请求（跨 clear 持久，供 Network 证据页）


# ---------- 后端直连（建数据/清理） ----------
def api_json(method, path, body=None):
    req = urllib.request.Request(API + path, method=method)
    req.add_header('Content-Type', 'application/json')
    if body is not None:
        req.data = json.dumps(body).encode('utf-8')
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode('utf-8'))


def create_test_task(name, case_ids):
    d = api_json('POST', '/tasks', {
        'name': name, 'case_ids': case_ids, 'device_ids': [], 'api_ids': [],
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
    options.add_argument('--window-size=1440,900')
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


def _js_click(drv, el):
    drv.execute_script("arguments[0].click();", el)


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 15).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.8)


def _body_text(drv):
    return drv.find_element(By.TAG_NAME, 'body').text


def _save_screenshot(drv, name):
    try:
        os.makedirs(ARTIFACTS, exist_ok=True)
        drv.save_screenshot(os.path.join(ARTIFACTS, name + '.png'))
    except Exception:
        pass


def _drain_network(drv):
    for entry in drv.get_log('performance'):
        try:
            outer = json.loads(entry['message'])
            inner = outer.get('message', {})
            method = inner.get('method', '')
            params = inner.get('params', {})
            if method == 'Network.requestWillBeSent':
                req = params.get('request', {})
                _network.append({
                    'method': req.get('method', ''),
                    'url': req.get('url', ''),
                    'postData': req.get('postData', ''),
                })
        except Exception:
            pass


def _reqs(suffix, method=None):
    out = []
    for r in _network:
        if suffix in r['url']:
            if method and r['method'] != method:
                continue
            out.append(r)
    return out


def _wait_for_request(drv, suffix, method, timeout=6):
    """确认点击后尽快轮询 Network 捕获（浏览器不稳定，尽早取证）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        _drain_network(drv)
        hits = _reqs(suffix, method)
        if hits:
            for h in hits:
                _evidence.append(h)
            return True
        time.sleep(0.4)
    return False


def _toast_present(drv, text, timeout=6):
    try:
        WebDriverWait(drv, timeout).until(
            lambda d: text in d.find_element(By.TAG_NAME, 'body').text)
        return True
    except Exception:
        return False


def _row_by_name(drv, name_fragment, timeout=12):
    xp = f"//tbody/tr[.//span[contains(text(),'{name_fragment}')]]"
    try:
        WebDriverWait(drv, timeout).until(lambda d: len(d.find_elements(By.XPATH, xp)) > 0)
        return drv.find_element(By.XPATH, xp)
    except Exception:
        return None


def _open_row_menu(drv, row):
    btn = row.find_element(By.XPATH, ".//button[@aria-label='任务操作']")
    btn.click()
    time.sleep(0.6)


def _menu_click(drv, label):
    els = drv.find_elements(By.XPATH, f"//*[@role='menuitem'][contains(.,'{label}')]")
    if not els:
        return False
    for el in els:
        if el.is_displayed():
            el.click()
            return True
    els[0].click()
    return True


def _confirm_dialog(drv, title, timeout=8):
    xp = (f"//div[@data-slot='alert-dialog-content']"
          f"[.//*[@data-slot='alert-dialog-title'][contains(., '{title}')]]")
    WebDriverWait(drv, timeout).until(lambda d: len(d.find_elements(By.XPATH, xp)) > 0)
    return drv.find_element(By.XPATH, xp)


def _dialog_desc(drv, dialog):
    return dialog.find_element(By.CSS_SELECTOR, "[data-slot='alert-dialog-description']").text


def _dialog_btn(drv, dialog, text):
    els = dialog.find_elements(By.XPATH, f".//button[normalize-space(.)='{text}']")
    for el in els:
        if el.is_displayed():
            try:
                el.click()
            except Exception:
                drv.execute_script("arguments[0].click();", el)
            return True
    return False


def _last_case_dialog(drv, timeout=6):
    """末例二次确认弹窗（§5.9）：按末例文案定位，避开首段弹窗关闭动画的误命中。"""
    xp = ("//div[@data-slot='alert-dialog-content']"
          "[.//*[contains(.,'这是任务中最后一个用例，移除后任务将不含任何用例。')]]")
    WebDriverWait(drv, timeout).until(lambda d: len(d.find_elements(By.XPATH, xp)) > 0)
    return drv.find_element(By.XPATH, xp)


def _set_dark(drv):
    drv.execute_script(
        "window.localStorage.setItem('iatp:theme:v1:mode', 'dark');"
        "document.documentElement.classList.add('dark');"
    )
    time.sleep(0.5)


def _set_light(drv):
    drv.execute_script(
        "window.localStorage.setItem('iatp:theme:v1:mode', 'light');"
        "document.documentElement.classList.remove('dark');"
    )
    time.sleep(0.5)


def _patch_status(drv, task_id, status):
    """window.fetch 打点：仅伪造 GET /tasks/{task_id} 返回指定 execution_status
    （让 running/paused 态的控制按钮可渲染）；stop/control POST 仍走真实后端
    （真实请求会发出，供 Network 证据；非运行中任务后端 400 属预期）。"""
    script = f"""
    (function () {{
      const orig = window.fetch.bind(window);
      const uid = '{task_id}';
      const st = '{status}';
      window.fetch = (url, opts) => {{
        const u = typeof url === 'string' ? url : (url && url.url) || '';
        const method = (opts && opts.method) || 'GET';
        if (u.indexOf('/api/v1/tasks/' + uid) >= 0 && method === 'GET') {{
          return orig(url, opts).then(async (resp) => {{
            try {{
              const data = await resp.clone().json();
              if (data && data.data) {{
                data.data.execution_status = st;
                data.data.status = st;
              }}
              return new Response(JSON.stringify(data), {{ status: 200,
                headers: {{ 'Content-Type': 'application/json' }} }});
            }} catch (e) {{ return resp; }}
          }});
        }}
        return orig(url, opts);
      }};
    }})();
    """
    drv.execute_script(script)
    time.sleep(0.3)


RESULTS = []


def check(name, ok, detail=''):
    RESULTS.append((name, bool(ok), detail))
    print(('PASS' if ok else 'FAIL') + ' | ' + name + ((' | ' + detail) if detail else ''))


# ---------- 阶段 1：行操作（C1/C3/C4） ----------
def phase_rows(drv, ts, T):
    _goto(drv, '/tasks/daily')
    _wait(drv, By.XPATH, '//tbody/tr', timeout=25)
    check('列表页可渲染（dev_user 自动会话）',
          '任务名称' in _body_text(drv) and '执行状态' in _body_text(drv))

    # C1 行删除
    row = _row_by_name(drv, '接线测试-INT949-DEL')
    if row:
        _drain_network(drv)
        _network.clear()
        _open_row_menu(drv, row)
        _menu_click(drv, '删除')
        dlg = _confirm_dialog(drv, '删除任务')
        desc = _dialog_desc(drv, dlg)
        check('C1 行删除确认弹窗（§5.10 文案）',
              '将把 1 个任务移入回收站，可在回收站恢复。' in desc, f'desc={desc[:60]}')
        _save_screenshot(drv, 'c1_row_delete_light')
        _dialog_btn(drv, dlg, '取消')
        time.sleep(0.8)
        _drain_network(drv)
        check('C1 行删除取消不发请求（DELETE 0 新增）',
              len(_reqs(f'/api/v1/tasks/{T["del"]}', 'DELETE')) == 0)
        _open_row_menu(drv, _row_by_name(drv, '接线测试-INT949-DEL'))
        _menu_click(drv, '删除')
        _dialog_btn(drv, _confirm_dialog(drv, '删除任务'), '删除')
        req_ok = _wait_for_request(drv, f'/api/v1/tasks/{T["del"]}', 'DELETE')
        check('C1 行删除确认发真实 DELETE /tasks/{id}', req_ok,
              (_reqs(f'/api/v1/tasks/{T["del"]}', 'DELETE')[-1]['url']
               if _reqs(f'/api/v1/tasks/{T["del"]}', 'DELETE') else ''))
        check('C1 行删除 toast「已移入回收站」', _toast_present(drv, '已移入回收站'))
        _goto(drv, '/tasks/daily')
        check('C1 行删除后列表刷新（DEL 消失）',
              f'接线测试-INT949-DEL-{ts}' not in _body_text(drv))
    else:
        check('C1 行删除前置（找到 DEL 行）', False)

    # C3 行恢复
    _goto(drv, '/tasks/daily')
    _click(drv, By.XPATH, "//button[@title='回收站']")
    time.sleep(2.0)
    row = _row_by_name(drv, '接线测试-INT949-DEL')
    if row:
        _drain_network(drv)
        _network.clear()
        _open_row_menu(drv, row)
        _menu_click(drv, '恢复')
        dlg = _confirm_dialog(drv, '恢复任务')
        desc = _dialog_desc(drv, dlg)
        check('C3 行恢复确认弹窗（旧 Vue 基线文案）',
              '确定要恢复该任务吗？' in desc, f'desc={desc[:60]}')
        _save_screenshot(drv, 'c3_row_restore')
        _dialog_btn(drv, dlg, '取消')
        time.sleep(0.8)
        _drain_network(drv)
        check('C3 行恢复取消不发请求（POST restore 0 新增）',
              len(_reqs(f'/api/v1/tasks/{T["del"]}/restore', 'POST')) == 0)
        _open_row_menu(drv, _row_by_name(drv, '接线测试-INT949-DEL'))
        _menu_click(drv, '恢复')
        _dialog_btn(drv, _confirm_dialog(drv, '恢复任务'), '恢复')
        req_ok = _wait_for_request(drv, f'/api/v1/tasks/{T["del"]}/restore', 'POST')
        check('C3 行恢复确认发真实 POST /tasks/{id}/restore', req_ok)
        restored = _toast_present(drv, '已恢复', timeout=8)
        _goto(drv, '/tasks/daily')
        _click(drv, By.XPATH, "//button[@title='回收站']")
        time.sleep(2.0)
        gone = f'接线测试-INT949-DEL-{ts}' not in _body_text(drv)
        check('C3 行恢复 toast「已恢复」或任务移出回收站', restored or gone,
              f'toast={restored} gone_from_trash={gone}')
    else:
        check('C3 行恢复前置（回收站中找到 DEL）', False)

    # C4 行彻底删除（再删一次进回收站）
    _goto(drv, '/tasks/daily')
    _wait(drv, By.XPATH, '//tbody/tr', timeout=25)
    row = _row_by_name(drv, '接线测试-INT949-DEL')
    if row:
        _open_row_menu(drv, row)
        _menu_click(drv, '删除')
        _dialog_btn(drv, _confirm_dialog(drv, '删除任务'), '删除')
        time.sleep(2.0)
    _goto(drv, '/tasks/daily')
    _wait(drv, By.XPATH, '//tbody/tr', timeout=25)
    _click(drv, By.XPATH, "//button[@title='回收站']")
    _wait(drv, By.XPATH, '//tbody/tr', timeout=25)
    row = _row_by_name(drv, '接线测试-INT949-DEL')
    if row:
        _drain_network(drv)
        _network.clear()
        _open_row_menu(drv, row)
        _menu_click(drv, '彻底删除')
        dlg = _confirm_dialog(drv, '彻底删除')
        desc = _dialog_desc(drv, dlg)
        check('C4 行彻底删除确认弹窗（§5.10 文案）',
              '将永久删除 1 个任务及其全部执行数据，此操作不可恢复。' in desc,
              f'desc={desc[:70]}')
        _dialog_btn(drv, dlg, '取消')
        time.sleep(0.8)
        _drain_network(drv)
        check('C4 行彻底删除取消不发请求（DELETE purge 0 新增）',
              len(_reqs(f'/api/v1/tasks/{T["del"]}/purge', 'DELETE')) == 0)
        _open_row_menu(drv, _row_by_name(drv, '接线测试-INT949-DEL'))
        _menu_click(drv, '彻底删除')
        _dialog_btn(drv, _confirm_dialog(drv, '彻底删除'), '彻底删除')
        req_ok = _wait_for_request(drv, f'/api/v1/tasks/{T["del"]}/purge', 'DELETE')
        check('C4 行彻底删除确认发真实 DELETE /tasks/{id}/purge', req_ok)
        check('C4 行彻底删除 toast「已彻底删除」', _toast_present(drv, '已彻底删除'))
    else:
        check('C4 行彻底删除前置（回收站中找到 DEL）', False)


# ---------- 阶段 2：批量操作（C2/C5/C6） ----------
def phase_batch(drv, ts, T):
    # C2 批量删除
    _goto(drv, '/tasks/daily')
    cbs = _wait(drv, By.CSS_SELECTOR,
                f"[role='checkbox'][aria-label^='选择 接线测试-INT949-B']")
    if len(cbs) >= 2:
        for cb in cbs[:2]:
            _js_click(drv, cb)
            time.sleep(0.2)
        time.sleep(0.6)
        check('批量浮条出现（已选择 2 个任务）', '已选择 2 个任务' in _body_text(drv))
        _drain_network(drv)
        _network.clear()
        _click(drv, By.XPATH, "//button[contains(.,'批量删除')]")
        dlg = _confirm_dialog(drv, '批量删除任务')
        desc = _dialog_desc(drv, dlg)
        check('C2 批量删除确认弹窗（§5.10 文案含数量）',
              '将把 2 个任务移入回收站，可在回收站恢复。' in desc, f'desc={desc[:60]}')
        _save_screenshot(drv, 'c2_batch_delete_light')
        _dialog_btn(drv, dlg, '取消')
        time.sleep(0.8)
        _drain_network(drv)
        check('C2 批量删除取消不发请求（POST batch-action 0 新增）',
              len(_reqs('/api/v1/tasks/batch-action', 'POST')) == 0)
        _click(drv, By.XPATH, "//button[contains(.,'批量删除')]")
        _dialog_btn(drv, _confirm_dialog(drv, '批量删除任务'), '删除')
        req_ok = _wait_for_request(drv, '/api/v1/tasks/batch-action', 'POST')
        breq = _reqs('/api/v1/tasks/batch-action', 'POST')
        ok = req_ok
        pd = ''
        if breq:
            pd = breq[-1].get('postData') or ''
            ok = ok and ('delete' in pd) and (str(T['batch_a']) in pd) and (str(T['batch_b']) in pd)
        check('C2 批量删除确认发真实 POST /tasks/batch-action', ok, f'body={pd[:140]}')
        check('C2 批量删除 toast「已批量移入回收站 2 个」',
              _toast_present(drv, '已批量移入回收站 2 个'))
    else:
        check('C2 批量删除前置（找到 BA/BB 任务行）', False, f'count={len(cbs)}')

    # C5 批量恢复
    _goto(drv, '/tasks/daily')
    _click(drv, By.XPATH, "//button[@title='回收站']")
    time.sleep(2.0)
    cbs = _wait(drv, By.CSS_SELECTOR,
                f"[role='checkbox'][aria-label^='选择 接线测试-INT949-B']")
    if len(cbs) >= 2:
        for cb in cbs[:2]:
            _js_click(drv, cb)
            time.sleep(0.2)
        time.sleep(0.6)
        _drain_network(drv)
        _network.clear()
        _click(drv, By.XPATH, "//button[contains(.,'批量恢复')]")
        dlg = _confirm_dialog(drv, '批量恢复任务')
        desc = _dialog_desc(drv, dlg)
        check('C5 批量恢复确认弹窗（旧 Vue 文案含数量）',
              '确定要恢复选中的 2 个任务吗？' in desc, f'desc={desc[:60]}')
        _dialog_btn(drv, dlg, '取消')
        time.sleep(0.8)
        _drain_network(drv)
        check('C5 批量恢复取消不发请求（POST /tasks/restore 0 新增）',
              len(_reqs('/api/v1/tasks/restore', 'POST')) == 0)
        _click(drv, By.XPATH, "//button[contains(.,'批量恢复')]")
        _dialog_btn(drv, _confirm_dialog(drv, '批量恢复任务'), '恢复')
        req_ok = _wait_for_request(drv, '/api/v1/tasks/restore', 'POST')
        rreq = _reqs('/api/v1/tasks/restore', 'POST')
        ok = req_ok
        pd = ''
        if rreq:
            pd = rreq[-1].get('postData') or ''
            ok = ok and (str(T['batch_a']) in pd) and (str(T['batch_b']) in pd)
        check('C5 批量恢复确认发真实 POST /tasks/restore', ok, f'body={pd[:120]}')
        check('C5 批量恢复 toast「已批量恢复」', _toast_present(drv, '已批量恢复'))
    else:
        check('C5 批量恢复前置（回收站中找到 BA/BB 任务）', False, f'count={len(cbs)}')

    # C6 批量彻底删除（再删回回收站）
    _goto(drv, '/tasks/daily')
    cbs = _wait(drv, By.CSS_SELECTOR,
                f"[role='checkbox'][aria-label^='选择 接线测试-INT949-B']")
    if len(cbs) >= 2:
        for cb in cbs[:2]:
            _js_click(drv, cb)
            time.sleep(0.2)
        time.sleep(0.5)
        _click(drv, By.XPATH, "//button[contains(.,'批量删除')]")
        _dialog_btn(drv, _confirm_dialog(drv, '批量删除任务'), '删除')
        time.sleep(2.0)
    _goto(drv, '/tasks/daily')
    _click(drv, By.XPATH, "//button[@title='回收站']")
    time.sleep(2.0)
    cbs = _wait(drv, By.CSS_SELECTOR,
                f"[role='checkbox'][aria-label^='选择 接线测试-INT949-B']")
    if len(cbs) >= 2:
        for cb in cbs[:2]:
            _js_click(drv, cb)
            time.sleep(0.2)
        time.sleep(0.6)
        _drain_network(drv)
        _network.clear()
        _click(drv, By.XPATH, "//button[contains(.,'批量彻底删除')]")
        dlg = _confirm_dialog(drv, '批量彻底删除')
        desc = _dialog_desc(drv, dlg)
        check('C6 批量彻底删除确认弹窗（§5.10 文案含数量）',
              '将永久删除 2 个任务及其全部执行数据，此操作不可恢复。' in desc,
              f'desc={desc[:70]}')
        _save_screenshot(drv, 'c6_batch_purge')
        _dialog_btn(drv, dlg, '取消')
        time.sleep(0.8)
        _drain_network(drv)
        check('C6 批量彻底删除取消不发请求（POST /tasks/purge 0 新增）',
              len(_reqs('/api/v1/tasks/purge', 'POST')) == 0)
        _click(drv, By.XPATH, "//button[contains(.,'批量彻底删除')]")
        _dialog_btn(drv, _confirm_dialog(drv, '批量彻底删除'), '彻底删除')
        req_ok = _wait_for_request(drv, '/api/v1/tasks/purge', 'POST')
        preq = _reqs('/api/v1/tasks/purge', 'POST')
        ok = req_ok
        pd = ''
        if preq:
            pd = preq[-1].get('postData') or ''
            ok = ok and (str(T['batch_a']) in pd) and (str(T['batch_b']) in pd)
        check('C6 批量彻底删除确认发真实 POST /tasks/purge', ok, f'body={pd[:120]}')
        check('C6 批量彻底删除 toast「已批量彻底删除」',
              _toast_present(drv, '已批量彻底删除'))
    else:
        check('C6 批量彻底删除前置（回收站中找到 BA/BB 任务）', False, f'count={len(cbs)}')


# ---------- 阶段 3：批量发布 + 移除用例（C10/C7/C8/C9） ----------
def phase_publish_and_cases(drv, ts, T):
    # C10 批量发布
    _goto(drv, '/tasks/daily')
    cbs = _wait(drv, By.CSS_SELECTOR,
                f"[role='checkbox'][aria-label^='选择 接线测试-INT949-MULTI']")
    if len(cbs) >= 1:
        cbs2 = drv.find_elements(By.CSS_SELECTOR,
                f"[role='checkbox'][aria-label^='选择 接线测试-INT949-LAST']")
        if cbs2:
            _js_click(drv, cbs[0])
            _js_click(drv, cbs2[0])
            time.sleep(0.6)
        _drain_network(drv)
        _network.clear()
        _click(drv, By.XPATH,
              "//div[contains(@class,'fixed bottom-6')]//button[contains(.,'发布')]")
        dlg = _confirm_dialog(drv, '批量发布')
        desc = _dialog_desc(drv, dlg)
        check('C10 批量发布确认弹窗（§5.3 文案）',
              '将为选中的 2 个任务发布' in desc and '名称沿用源任务名，不可发布状态自动跳过' in desc,
              f'desc={desc[:60]}')
        _save_screenshot(drv, 'c10_batch_publish')
        _dialog_btn(drv, dlg, '取消')
        time.sleep(0.8)
        _drain_network(drv)
        check('C10 批量发布取消后无发布弹窗', '发布任务' not in _body_text(drv))
        _click(drv, By.XPATH,
              "//div[contains(@class,'fixed bottom-6')]//button[contains(.,'发布')]")
        _dialog_btn(drv, _confirm_dialog(drv, '批量发布'), '发布')
        time.sleep(1.5)
        check('C10 批量发布确认后打开首个任务发布弹窗（§5.2）',
              '发布任务' in _body_text(drv))
        close_btns = drv.find_elements(By.XPATH,
            "//div[@data-slot='dialog-content'][.//*[@data-slot='dialog-title'][contains(.,'发布任务')]]"
            "//button[contains(@aria-label,'关闭')]")
        if close_btns:
            _js_click(drv, close_btns[0])
            time.sleep(0.8)
    else:
        check('C10 批量发布前置（找到 MULTI 任务）', False)

    # C7 移除用例（多用例任务）
    _goto(drv, f'/tasks/{T["multi"]}')
    _wait(drv, By.XPATH, "//button[@aria-label='移除用例']", timeout=20)
    time.sleep(1.0)
    _drain_network(drv)
    _network.clear()
    _click(drv, By.XPATH, "//button[@aria-label='移除用例']")
    dlg = _confirm_dialog(drv, '移除用例')
    desc = _dialog_desc(drv, dlg)
    phase_ok = ('该任务尚未开始执行，用例将被直接移除。' in desc
                or '其当前轮次将被中断' in desc
                or '报告聚合将重算剔除该用例' in desc)
    check('C7 移除用例确认弹窗（§5.9 阶段后果文案）', phase_ok, f'desc={desc[:60]}')
    _save_screenshot(drv, 'c7_remove_case_light')
    _dialog_btn(drv, dlg, '取消')
    time.sleep(0.8)
    _drain_network(drv)
    check('C7 移除用例取消不发请求（DELETE /cases 0 新增）',
          len(_reqs(f'/api/v1/tasks/{T["multi"]}/cases/', 'DELETE')) == 0)
    _click(drv, By.XPATH, "//button[@aria-label='移除用例']")
    _dialog_btn(drv, _confirm_dialog(drv, '移除用例'), '移除')
    req_ok = _wait_for_request(drv, f'/api/v1/tasks/{T["multi"]}/cases/', 'DELETE')
    creq = _reqs(f'/api/v1/tasks/{T["multi"]}/cases/', 'DELETE')
    check('C7 移除用例确认发真实 DELETE /tasks/{id}/cases/{caseId}',
          req_ok, (creq[-1]['url']) if creq else '')
    check('C7 移除用例 toast「已移除用例」', _toast_present(drv, '已移除用例'))

    # C8 末例「仅移除用例」
    _goto(drv, f'/tasks/{T["last"]}')
    _wait(drv, By.XPATH, "//button[@aria-label='移除用例']", timeout=20)
    time.sleep(1.0)
    _click(drv, By.XPATH, "//button[@aria-label='移除用例']")
    _dialog_btn(drv, _confirm_dialog(drv, '移除用例'), '移除')
    # 等待末例二次确认文案出现（首段弹窗关闭动画期间避免误命中）
    WebDriverWait(drv, 6).until(
        lambda d: '这是任务中最后一个用例，移除后任务将不含任何用例。'
        in d.find_element(By.TAG_NAME, 'body').text)
    dlg2 = _last_case_dialog(drv)
    desc2 = _dialog_desc(drv, dlg2)
    check('C8 末例二次确认弹窗（§5.9 文案）',
          '这是任务中最后一个用例，移除后任务将不含任何用例。' in desc2
          and '移除并停止任务' in dlg2.text and '仅移除用例' in dlg2.text,
          f'desc={desc2[:80]}')
    _save_screenshot(drv, 'c8_last_case_confirm')
    _drain_network(drv)
    _network.clear()
    _dialog_btn(drv, dlg2, '仅移除用例')
    req_ok = _wait_for_request(drv, f'/api/v1/tasks/{T["last"]}/cases/', 'DELETE')
    creq = _reqs(f'/api/v1/tasks/{T["last"]}/cases/', 'DELETE')
    sreq = _reqs(f'/api/v1/tasks/{T["last"]}/stop', 'POST')
    check('C8 仅移除用例发真实 DELETE /cases（无 stop 请求）',
          req_ok and len(sreq) == 0, f'delete={len(creq)} stop={len(sreq)}')
    check('C8 仅移除用例 toast「已移除用例」', _toast_present(drv, '已移除用例'))

    # C9 末例「移除并停止任务」
    _goto(drv, f'/tasks/{T["last2"]}')
    _wait(drv, By.XPATH, "//button[@aria-label='移除用例']", timeout=20)
    time.sleep(1.0)
    _click(drv, By.XPATH, "//button[@aria-label='移除用例']")
    _dialog_btn(drv, _confirm_dialog(drv, '移除用例'), '移除')
    WebDriverWait(drv, 6).until(
        lambda d: '这是任务中最后一个用例，移除后任务将不含任何用例。'
        in d.find_element(By.TAG_NAME, 'body').text)
    dlg3 = _last_case_dialog(drv)
    _drain_network(drv)
    _network.clear()
    _dialog_btn(drv, dlg3, '移除并停止任务')
    del_ok = _wait_for_request(drv, f'/api/v1/tasks/{T["last2"]}/cases/', 'DELETE')
    stop_ok = _wait_for_request(drv, f'/api/v1/tasks/{T["last2"]}/stop', 'POST')
    creq = _reqs(f'/api/v1/tasks/{T["last2"]}/cases/', 'DELETE')
    sreq = _reqs(f'/api/v1/tasks/{T["last2"]}/stop', 'POST')
    check('C9 移除并停止任务发 DELETE /cases + POST /tasks/{id}/stop',
          del_ok and stop_ok, f'delete={len(creq)} stop={len(sreq)}')
    check('C9 移除并停止任务 toast「已移除用例」', _toast_present(drv, '已移除用例'))


# ---------- 阶段 4：控制按钮（C11/C12/C13）+ 深色截图 ----------
def phase_control(drv, ts, T):
    # C11 详情停止
    _goto(drv, '/tasks/daily')
    _patch_status(drv, T['ctrl'], 'running')
    row = _row_by_name(drv, '接线测试-INT949-CTRL')
    if row:
        name_btn = row.find_elements(By.XPATH,
            ".//td[2]//button[.//span[contains(@class,'truncate')]]")
        if name_btn:
            _js_click(drv, name_btn[0])
            _wait(drv, By.XPATH, "//button[contains(.,'停止测试')]", timeout=20)
            time.sleep(1.0)
            check('C11 伪造 running 详情渲染「停止测试」按钮', True)
            _drain_network(drv)
            _network.clear()
            _click(drv, By.XPATH, "//button[contains(.,'停止测试')]")
            dlg = _confirm_dialog(drv, '停止任务')
            desc = _dialog_desc(drv, dlg)
            check('C11 详情停止确认弹窗（§5.8 文案）',
                  '确定要停止该任务吗？' in desc, f'desc={desc[:50]}')
            _save_screenshot(drv, 'c11_detail_stop_light')
            _dialog_btn(drv, dlg, '取消')
            time.sleep(0.8)
            _drain_network(drv)
            check('C11 停止取消不发请求（POST stop 0 新增）',
                  len(_reqs(f'/api/v1/tasks/{T["ctrl"]}/stop', 'POST')) == 0)
            _click(drv, By.XPATH, "//button[contains(.,'停止测试')]")
            _dialog_btn(drv, _confirm_dialog(drv, '停止任务'), '停止')
            req_ok = _wait_for_request(drv, f'/api/v1/tasks/{T["ctrl"]}/stop', 'POST')
            sreq = _reqs(f'/api/v1/tasks/{T["ctrl"]}/stop', 'POST')
            check('C11 停止确认发真实 POST /tasks/{id}/stop',
                  req_ok, (sreq[-1]['url']) if sreq else '')
            _dialog_btn(drv, _confirm_dialog(drv, '停止任务'), '取消')
            time.sleep(0.5)
        else:
            check('C11 前置（CTRL 行详情入口）', False)
    else:
        check('C11 前置（找到 CTRL 行）', False)

    # C12 详情暂停
    _goto(drv, '/tasks/daily')
    _patch_status(drv, T['ctrl'], 'running')
    row = _row_by_name(drv, '接线测试-INT949-CTRL')
    if row:
        name_btn = row.find_elements(By.XPATH,
            ".//td[2]//button[.//span[contains(@class,'truncate')]]")
        if name_btn:
            _js_click(drv, name_btn[0])
            _wait(drv, By.XPATH, "//button[contains(.,'暂停')]", timeout=20)
            time.sleep(1.0)
            _drain_network(drv)
            _network.clear()
            _click(drv, By.XPATH, "//button[contains(.,'暂停')]")
            dlg = _confirm_dialog(drv, '暂停任务')
            desc = _dialog_desc(drv, dlg)
            check('C12 详情暂停确认弹窗（旧 Vue 基线文案）',
                  '确定要暂停该测试任务吗？' in desc, f'desc={desc[:50]}')
            _save_screenshot(drv, 'c12_detail_pause_light')
            _dialog_btn(drv, dlg, '取消')
            time.sleep(0.8)
            _drain_network(drv)
            check('C12 暂停取消不发请求（POST control 0 新增）',
                  len(_reqs(f'/api/v1/tasks/{T["ctrl"]}/control', 'POST')) == 0)
            _click(drv, By.XPATH, "//button[contains(.,'暂停')]")
            _dialog_btn(drv, _confirm_dialog(drv, '暂停任务'), '暂停')
            req_ok = _wait_for_request(drv, f'/api/v1/tasks/{T["ctrl"]}/control', 'POST')
            creq = _reqs(f'/api/v1/tasks/{T["ctrl"]}/control', 'POST')
            check('C12 暂停确认发真实 POST /tasks/{id}/control',
                  req_ok, (creq[-1]['url']) if creq else '')
            _dialog_btn(drv, _confirm_dialog(drv, '暂停任务'), '取消')
            time.sleep(0.5)
        else:
            check('C12 前置（CTRL 行详情入口）', False)
    else:
        check('C12 前置（找到 CTRL 行）', False)

    # C13 详情继续（paused）
    _goto(drv, '/tasks/daily')
    _patch_status(drv, T['ctrl'], 'paused')
    row = _row_by_name(drv, '接线测试-INT949-CTRL')
    if row:
        name_btn = row.find_elements(By.XPATH,
            ".//td[2]//button[.//span[contains(@class,'truncate')]]")
        if name_btn:
            _js_click(drv, name_btn[0])
            _wait(drv, By.XPATH, "//button[contains(.,'继续')]", timeout=20)
            time.sleep(1.0)
            _drain_network(drv)
            _network.clear()
            _click(drv, By.XPATH, "//button[contains(.,'继续')]")
            dlg = _confirm_dialog(drv, '继续任务')
            desc = _dialog_desc(drv, dlg)
            check('C13 详情继续确认弹窗（旧 Vue 基线文案）',
                  '确定要继续该测试任务吗？' in desc, f'desc={desc[:50]}')
            _save_screenshot(drv, 'c13_detail_resume_light')
            _dialog_btn(drv, dlg, '取消')
            time.sleep(0.8)
            _drain_network(drv)
            check('C13 继续取消不发请求（POST control 0 新增）',
                  len(_reqs(f'/api/v1/tasks/{T["ctrl"]}/control', 'POST')) == 0)
            _click(drv, By.XPATH, "//button[contains(.,'继续')]")
            _dialog_btn(drv, _confirm_dialog(drv, '继续任务'), '继续')
            req_ok = _wait_for_request(drv, f'/api/v1/tasks/{T["ctrl"]}/control', 'POST')
            creq = _reqs(f'/api/v1/tasks/{T["ctrl"]}/control', 'POST')
            check('C13 继续确认发真实 POST /tasks/{id}/control（resume）',
                  req_ok, (creq[-1]['url']) if creq else '')
            _dialog_btn(drv, _confirm_dialog(drv, '继续任务'), '取消')
            time.sleep(0.5)
        else:
            check('C13 前置（CTRL 行详情入口）', False)
    else:
        check('C13 前置（找到 CTRL 行）', False)

    # 深色主题确认弹窗截图
    _set_dark(drv)
    _goto(drv, '/tasks/daily')
    _wait(drv, By.XPATH, '//tbody/tr', timeout=25)
    row = _row_by_name(drv, '接线测试-INT949-MULTI')
    if row:
        _open_row_menu(drv, row)
        _menu_click(drv, '删除')
        dlg = _confirm_dialog(drv, '删除任务')
        check('深色主题行删除确认弹窗（destructive 主钮渲染）', True)
        _save_screenshot(drv, 'dark_row_delete')
        _dialog_btn(drv, dlg, '取消')
        time.sleep(0.5)
    _goto(drv, f'/tasks/{T["multi"]}')
    _wait(drv, By.XPATH, "//button[@aria-label='移除用例']", timeout=20)
    time.sleep(1.0)
    _click(drv, By.XPATH, "//button[@aria-label='移除用例']")
    dlg = _confirm_dialog(drv, '移除用例')
    check('深色主题移除用例确认弹窗渲染', True)
    _save_screenshot(drv, 'dark_remove_case')
    _dialog_btn(drv, dlg, '取消')
    _set_light(drv)


def _write_network_evidence(drv):
    try:
        os.makedirs(ARTIFACTS, exist_ok=True)
        rows = []
        seen = set()
        for r in _evidence:
            url = r['url'].replace('http://localhost:5331', '')
            key = (r['method'], url.split('?')[0])
            if key in seen:
                continue
            seen.add(key)
            rows.append(f"<tr><td>{r['method']}</td><td>{url}</td>"
                        f"<td>{urllib.parse.quote((r['postData'] or '')[:120])}</td></tr>")
        net_html = (f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
                    f"<title>INT-949 Network 证据</title></head><body>"
                    f"<h3>INT-949 确认弹窗实测请求清单（requestWillBeSent）</h3>"
                    f"<table border='1' cellspacing='0' cellpadding='4'>"
                    f"<tr><th>method</th><th>url</th><th>postData</th></tr>"
                    f"{''.join(rows)}</table></body></html>")
        net_path = os.path.join(ARTIFACTS, 'network_evidence.html')
        with open(net_path, 'w', encoding='utf-8') as f:
            f.write(net_html)
        drv.get('file:///' + net_path.replace('\\', '/'))
        time.sleep(1.5)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'network_evidence.png'))
        check('Network 证据页生成', True)
    except Exception as e:
        check('Network 证据页生成', False, str(e)[:80])


def main():
    # 可选 --phases 1 3 只跑指定阶段（各阶段独立浏览器，便于崩溃重试）
    wanted = set()
    for a in sys.argv[1:]:
        if a.isdigit():
            wanted.add(int(a))
    ts = int(time.time())
    T = {
        'del': create_test_task(f'接线测试-INT949-DEL-{ts}', [CASE_A]),
        'batch_a': create_test_task(f'接线测试-INT949-BA-{ts}', []),
        'batch_b': create_test_task(f'接线测试-INT949-BB-{ts}', []),
        'multi': create_test_task(f'接线测试-INT949-MULTI-{ts}', [CASE_A, CASE_B]),
        'last': create_test_task(f'接线测试-INT949-LAST-{ts}', [CASE_A]),
        'last2': create_test_task(f'接线测试-INT949-LAST2-{ts}', [CASE_A]),
        'ctrl': create_test_task(f'接线测试-INT949-CTRL-{ts}', [CASE_A]),
    }
    print(f'[setup] tasks: ' + ' '.join(f'{k}={v}' for k, v in T.items()))

    # 阶段 1：行操作
    if not wanted or 1 in wanted:
        drv = _driver()
        try:
            try:
                phase_rows(drv, ts, T)
            except Exception as e:
                check('阶段1 浏览器异常', False, str(e)[:80])
        finally:
            try:
                drv.quit()
            except Exception:
                pass

    # 阶段 2：批量操作
    if not wanted or 2 in wanted:
        drv = _driver()
        try:
            try:
                phase_batch(drv, ts, T)
            except Exception as e:
                check('阶段2 浏览器异常', False, str(e)[:80])
        finally:
            try:
                drv.quit()
            except Exception:
                pass

    # 阶段 3：批量发布 + 移除用例
    if not wanted or 3 in wanted:
        drv = _driver()
        try:
            try:
                phase_publish_and_cases(drv, ts, T)
            except Exception as e:
                check('阶段3 浏览器异常', False, str(e)[:80])
        finally:
            try:
                drv.quit()
            except Exception:
                pass

    # 阶段 4：控制按钮 + 深色截图
    if not wanted or 4 in wanted:
        drv = _driver()
        try:
            try:
                phase_control(drv, ts, T)
            except Exception as e:
                check('阶段4 浏览器异常', False, str(e)[:80])
        finally:
            try:
                drv.quit()
            except Exception:
                pass

    # 阶段 5：Network 证据页（独立浏览器打开 HTML 截图，避免阶段4浏览器崩溃影响）
    if not wanted or 5 in wanted:
        drv = _driver()
        try:
            _write_network_evidence(drv)
        except Exception as e:
            check('Network 证据页生成', False, str(e)[:80])
        finally:
            try:
                drv.quit()
            except Exception:
                pass

    # 清理测试数据
    for tid in T.values():
        cleanup_task(tid)
    try:
        left = api_json('GET', '/tasks?search=' + urllib.parse.quote('接线测试-INT949'))
        left_n = len(left.get('data', {}).get('items', []))
    except Exception:
        left_n = -1
    check('测试数据已彻底删除（无 INT949 残留）', left_n == 0, f'left={left_n}')

    print('\n===== INT-949 验收结果 =====')
    for name, ok, detail in RESULTS:
        print(('PASS' if ok else 'FAIL') + ' | ' + name)
    failed = [r for r in RESULTS if not r[1]]
    print(f'TOTAL {len(RESULTS)} / PASS {len(RESULTS) - len(failed)} / FAIL {len(failed)}')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
