# -*- coding: utf-8 -*-
"""INT-948 评估维度「编辑维度」缺陷修复验收（POST 副本 → PUT 更新）。

针对 frontend-react 接线版（连常驻 5000 后端，dev server 5337，AUTH_MODE=off）：
① 新增测试维度（真实后端）→ 列表出现一条；
② 编辑改名保存：Network 唯一写请求是 PUT /evaluation/dimensions/{id}（非 POST 新建）；
③ 后端 GET 核对：原记录 id 不变、name 已更新，列表仅一条（无同名副本）；
④ 浅/深色截图 + Network 证据；run 结束前删除测试维度。
"""
import json
import os
import time
import urllib.error
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5337')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
HERE = os.path.dirname(os.path.abspath(__file__))
ARTIFACTS = os.path.join(HERE, 'artifacts', 'int948_dimension_edit_put')

STAMP = str(int(time.time()))
ORIG_NAME = f'INT948_接线测试_{STAMP}_原'
RENAMED_NAME = f'INT948_接线测试_{STAMP}_改'
DESC = 'INT-948 编辑维度应走 PUT 更新原记录'


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
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
    WebDriverWait(drv, 20).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.0)


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _shot(drv, name, sub='light'):
    d = os.path.join(ARTIFACTS, sub)
    os.makedirs(d, exist_ok=True)
    drv.save_screenshot(os.path.join(d, f'{name}.png'))


def _set_theme(drv, mode):
    drv.execute_script(
        "localStorage.setItem('iatp:theme:v1:mode', arguments[0]);"
        "document.documentElement.classList.remove('light','dark');"
        "document.documentElement.classList.add(arguments[0]);", mode)
    time.sleep(0.5)


def _enter_workbench(drv):
    _goto(drv, '/login')
    WebDriverWait(drv, 15).until(lambda d: '进入工作台' in _body_text(d))
    drv.find_element(By.XPATH, "//button[contains(., '进入工作台')]").click()
    WebDriverWait(drv, 20).until(lambda d: 'dashboard' in d.current_url)
    time.sleep(1.0)


def _drain_requests(drv, marker):
    """从 performance 日志提取 /evaluation/dimensions 写请求（PUT/POST），本轮起。"""
    reqs = []
    for e in drv.get_log('performance'):
        msg = e.get('message')
        if isinstance(msg, str):
            try:
                msg = json.loads(msg)
            except Exception:
                continue
        if not isinstance(msg, dict):
            continue
        evt = msg.get('message') if isinstance(msg.get('message'), dict) else msg
        if not evt or not isinstance(evt, dict) or evt.get('method') != 'Network.requestWillBeSent':
            continue
        req = evt.get('params', {}).get('request', {})
        url = req.get('url', '')
        if '/evaluation/dimensions' not in url:
            continue
        method = req.get('method', '')
        post = req.get('postData')
        body = None
        if post:
            try:
                body = json.loads(post)
            except Exception:
                body = {'raw': post}
        reqs.append({'method': method, 'url': url, 'body': body})
    return reqs


def _click_save(drv):
    """抽屉底部保存钮：右下角可能被 sonner toast 覆盖，用 JS click 规避拦截。"""
    btn = drv.find_element(By.XPATH, "//button[@type='submit'][contains(., '保存')]")
    drv.execute_script('arguments[0].click()', btn)


def _dismiss_toasts(drv):
    """清掉右下角残留 toast（sonner 到点自动消失；显式移除可加速）。"""
    try:
        drv.execute_script(
            "document.querySelectorAll('[data-sonner-toast]').forEach(t=>t.remove())")
    except Exception:
        pass


def _api_dimensions():
    url = BASE + '/api/v1/evaluation/dimensions?per_page=1000'
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _delete_dimension(dim_id):
    url = f'{BASE}/api/v1/evaluation/dimensions/{dim_id}'
    req = urllib.request.Request(url, method='DELETE')
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return f'HTTP {e.code}: {e.read().decode()[:200]}'


def main():
    os.makedirs(ARTIFACTS, exist_ok=True)
    # 0. 预清理上一轮可能的 INT948 残留
    try:
        data = _api_dimensions()
        for i in data.get('data', {}).get('items', []):
            if i.get('name', '').startswith('INT948_接线测试_'):
                print('PRE-CLEAN:', _delete_dimension(i['id']), i['id'], i['name'], flush=True)
    except Exception as e:
        print('PRE-CLEAN error:', e, flush=True)
    results = {'created_id': None}
    created_id = None
    drv = _driver()
    try:
        _enter_workbench(drv)
        _goto(drv, '/Evaluation')
        WebDriverWait(drv, 20).until(lambda d: '评估维度' in _body_text(d))

        # ── 1. 新增测试维度 ──
        drv.find_element(By.XPATH, "//button[contains(., '新增维度')]").click()
        WebDriverWait(drv, 10).until(lambda d: '新增评估维度' in _body_text(d))
        name_input = drv.find_element(By.ID, 'dim-name')
        name_input.send_keys(ORIG_NAME)
        drv.find_element(By.ID, 'dim-description').send_keys(DESC)
        _shot(drv, '01-create-dialog-light', 'light')
        _dismiss_toasts(drv)
        _click_save(drv)
        WebDriverWait(drv, 10).until(lambda d: '评估维度添加成功' in _body_text(d))
        time.sleep(1.0)
        results['create_toast_ok'] = '评估维度添加成功' in _body_text(drv)

        # 找到新建记录 id（后端真实 id）
        data = _api_dimensions()
        items = data.get('data', {}).get('items', [])
        matches = [i for i in items if i.get('name') == ORIG_NAME]
        results['created_found'] = len(matches) == 1
        if matches:
            created_id = matches[0]['id']
            results['created_id'] = created_id
            results['created_name'] = matches[0]['name']
        else:
            results['error'] = '创建后后端未查到 ORIG_NAME'
            return results

        # ── 2. 编辑改名保存：捕获写请求 ──
        _drain_requests(drv, 'before-edit-save')
        edit_btn = drv.find_element(
            By.XPATH, f"//*[@aria-label='编辑维度 {ORIG_NAME}']")
        edit_btn.click()
        WebDriverWait(drv, 10).until(lambda d: '编辑评估维度' in _body_text(d))
        # 抽屉反填
        WebDriverWait(drv, 10).until(
            lambda d: d.find_element(By.ID, 'dim-name').get_attribute('value') == ORIG_NAME)
        results['edit_refill_ok'] = True
        _shot(drv, '02-edit-drawer-light', 'light')
        # 改名
        name_input = drv.find_element(By.ID, 'dim-name')
        name_input.clear()
        name_input.send_keys(RENAMED_NAME)
        _shot(drv, '03-edit-renamed-light', 'light')
        _dismiss_toasts(drv)
        _click_save(drv)
        WebDriverWait(drv, 10).until(lambda d: '评估维度更新成功' in _body_text(d))
        time.sleep(1.5)

        write_reqs = _drain_requests(drv, 'after-edit-save')
        dim_write_reqs = [
            r for r in write_reqs if r['method'] in ('PUT', 'POST')
        ]
        results['edit_write_requests'] = dim_write_reqs
        put_reqs = [r for r in dim_write_reqs if r['method'] == 'PUT']
        post_reqs = [r for r in dim_write_reqs if r['method'] == 'POST']
        results['edit_has_put'] = len(put_reqs) == 1
        results['edit_no_new_post'] = len(post_reqs) == 0
        if put_reqs:
            put = put_reqs[0]
            results['edit_put_url'] = put['url']
            results['edit_put_body_name'] = (
                (put['body'] or {}).get('name') == RENAMED_NAME)
            # PUT URL 应含原记录 id
            results['edit_put_url_has_id'] = f'/evaluation/dimensions/{created_id}' in put['url']
        else:
            results['edit_put_url'] = None
            results['edit_put_body_name'] = False
            results['edit_put_url_has_id'] = False

        # ── 3. 列表仅一条（改后名）──
        WebDriverWait(drv, 10).until(
            lambda d: _body_text(d).count(RENAMED_NAME) >= 1)
        results['list_has_renamed'] = RENAMED_NAME in _body_text(drv)
        results['list_no_original'] = ORIG_NAME not in _body_text(drv)

        # 后端核对：id 不变、name 更新、无同名副本
        data = _api_dimensions()
        items = data.get('data', {}).get('items', [])
        renamed = [i for i in items if i.get('name') == RENAMED_NAME]
        orig = [i for i in items if i.get('name') == ORIG_NAME]
        results['backend_one_renamed'] = len(renamed) == 1
        results['backend_no_original'] = len(orig) == 0
        results['backend_id_preserved'] = (
            len(renamed) == 1 and created_id is not None
            and renamed[0]['id'] == created_id)
        if renamed:
            results['backend_renamed_id'] = renamed[0]['id']
            results['backend_renamed_desc'] = renamed[0].get('description')

        # ── 4. 深色截图 ──
        _set_theme(drv, 'dark')
        time.sleep(0.5)
        _shot(drv, '04-list-after-edit-dark', 'dark')

        # 清理
        if created_id is not None:
            results['cleanup'] = _delete_dimension(created_id)
    finally:
        drv.quit()

    print(json.dumps(results, ensure_ascii=False, indent=2), flush=True)
    ok = all([
        results.get('create_toast_ok'),
        results.get('created_found'),
        results.get('edit_refill_ok'),
        results.get('edit_has_put'),
        results.get('edit_no_new_post'),
        results.get('edit_put_body_name'),
        results.get('edit_put_url_has_id'),
        results.get('list_has_renamed'),
        results.get('list_no_original'),
        results.get('backend_one_renamed'),
        results.get('backend_no_original'),
        results.get('backend_id_preserved'),
    ])
    print('RESULT:', 'PASS' if ok else 'FAIL', flush=True)
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
