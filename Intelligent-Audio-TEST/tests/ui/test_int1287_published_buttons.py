# -*- coding: utf-8 -*-
"""INT-1287 验收主脚本：真实库栈(5700 via 5310) 已发布任务四按钮逐点。
执行/新版本/重命名/归档 → 真实请求(Network performance log) + toast + 弹窗 + 列表刷新。
浅色全程截图 + 深色一图。数据：脚本自建 published 行（接线测试_INT1287_...），
动作后清理（执行创建的日常任务软删+purge；published 行及版本行 DB 删除）。
注意：新版本会创建新的当前版本行（新 id），后续重命名/归档作用于该新行——
断言按实际 URL 目标匹配，不预设 id。
"""
import json
import os
import re
import subprocess
import time
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = 'http://localhost:5310'
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ARTIFACTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1287_accept')
PSQL = r'D:\00_env\postgresql-16.8-1-windows-x64-binaries\pgsql\bin\psql.exe'
PGPASSWORD = 'intelligent_audio_test666'

MY_PREFIX = '接线测试_INT1287_'

_network = []


def _api_token():
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1287_probe', 'token.txt')
    return open(p, encoding='utf-8').read().strip()


def _api(method, path, body=None):
    token = _api_token()
    req = urllib.request.Request('http://127.0.0.1:5700/api/v1' + path, method=method)
    req.add_header('Authorization', 'Bearer ' + token)
    req.add_header('Content-Type', 'application/json')
    if body is not None:
        req.data = json.dumps(body).encode('utf-8')
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode('utf-8'))


# ---------- DB 直连（自建数据清理） ----------
def db_sql(sql):
    env = dict(os.environ, PGPASSWORD=PGPASSWORD)
    r = subprocess.run(
        [PSQL, '-h', 'localhost', '-p', '15432', '-U', 'intelligent_audio_test',
         '-d', 'intelligent_audio_test', '-t', '-A', '-c', sql],
        capture_output=True, text=True, encoding='utf-8', env=env)
    return r.stdout.strip()


def cleanup_published(anchor_id):
    rows = db_sql(
        "SELECT id FROM published_tasks WHERE (id=%d OR task_group_id=%d)" % (anchor_id, anchor_id))
    for rid in rows.splitlines():
        if rid.strip().isdigit():
            db_sql("DELETE FROM published_tasks WHERE id=%s" % rid.strip())
            print('[cleanup] deleted published_tasks id', rid.strip())


def cleanup_daily_task(task_id):
    try:
        _api('DELETE', '/tasks/%s' % task_id)
        print('[cleanup] soft-deleted daily task', task_id)
    except Exception as e:
        print('[cleanup] soft-delete fail', task_id, e)
    try:
        _api('POST', '/tasks/purge', {'ids': [task_id]})
        print('[cleanup] purged daily task', task_id)
    except Exception as e:
        print('[cleanup] purge fail', task_id, e)


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


def _wait(drv, by, value, timeout=15):
    return WebDriverWait(drv, timeout).until(lambda d: d.find_elements(by, value))


def _click_visible(drv, els):
    for el in els:
        try:
            if el.is_displayed():
                el.click()
                return el
        except Exception:
            continue
    if els:
        drv.execute_script("arguments[0].click();", els[0])
        return els[0]
    return None


def _drain_network(drv):
    batch = []
    for entry in drv.get_log('performance'):
        try:
            outer = json.loads(entry['message'])
            inner = outer.get('message', {})
            if inner.get('method') == 'Network.requestWillBeSent':
                req = inner.get('params', {}).get('request', {})
                batch.append({'method': req.get('method', ''), 'url': req.get('url', ''),
                              'postData': req.get('postData', '')})
        except Exception:
            pass
    _network.extend(batch)
    return batch


_step_evidence = []  # 每步收集的 mutations，跨清空保留


def _start_step(name):
    """步骤开始：清空当前累计，记下本步标签；返回清空的列表"""
    _network.clear()
    return _network


def _capture_step(name):
    """步骤结束后收集 mutation 请求写入 _step_evidence（清空前调用）"""
    for r in _network:
        if 'published-tasks' in r['url'] and r['method'] in ('POST', 'PUT', 'DELETE'):
            _step_evidence.append({'step': name, 'method': r['method'], 'url': r['url'],
                                   'postData': r.get('postData', '')})


def _reqs(suffix, method=None):
    out = []
    for r in _network:
        if suffix in r['url']:
            if method and r['method'] != method:
                continue
            out.append(r)
    return out


def _toast_present(drv, text, timeout=8):
    try:
        WebDriverWait(drv, timeout).until(
            lambda d: text in d.find_element(By.TAG_NAME, 'body').text)
        return True
    except Exception:
        return False


def _row_by_name(drv, fragment):
    rows = drv.find_elements(By.XPATH, f"//tbody/tr[.//span[contains(text(),'{fragment}')]]")
    return rows[0] if rows else None


def _row_btn(drv, row, label):
    btns = row.find_elements(By.XPATH, f".//button[normalize-space(.)='{label}']")
    return _click_visible(drv, btns)


def _shot(drv, name):
    os.makedirs(ARTIFACTS, exist_ok=True)
    drv.save_screenshot(os.path.join(ARTIFACTS, name + '.png'))
    print('[shot]', name)


def _set_theme(drv, theme):
    drv.execute_script(
        "window.localStorage.setItem('iatp:theme:v1:mode', arguments[0]);"
        "var r=document.documentElement;r.classList.remove('light','dark');"
        "r.classList.add(arguments[0]);", theme)
    time.sleep(0.5)


RESULTS = []


def check(name, ok, detail=''):
    RESULTS.append((name, bool(ok), detail))
    print(('PASS' if ok else 'FAIL') + ' | ' + name + ((' | ' + detail) if detail else ''))


def main():
    # ---------- 自建 published 行（真实库栈） ----------
    ts = int(time.time())
    pub_name = MY_PREFIX + '按钮验收_' + str(ts)
    pub = _api('POST', '/published-tasks', {
        'source_task_id': 474, 'name': pub_name,
        'description': 'INT-1287 四按钮验收自建',
    })
    anchor_id = pub['data']['id']
    print('[setup] created published row id=%s name=%s' % (anchor_id, pub_name))
    created_task = None

    drv = _driver()
    try:
        # ---------- 登录（真实库栈） ----------
        drv.get(BASE + '/login')
        WebDriverWait(drv, 15).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(2.0)
        drv.find_element(By.ID, 'username').send_keys('接线测试_admin')
        drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
        drv.find_element(By.XPATH, "//button[@type='submit']").click()
        time.sleep(6.0)
        check('登录真实库栈成功跳 dashboard', 'dashboard' in drv.current_url, drv.current_url)

        # ---------- 已发布任务列表 ----------
        drv.get(BASE + '/tasks/published')
        WebDriverWait(drv, 20).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(2.5)
        _drain_network(drv)
        _wait(drv, By.XPATH, '//tbody/tr', timeout=25)
        row = _row_by_name(drv, pub_name)
        check('列表渲染自建 published 行', row is not None, 'name=' + pub_name)
        body = drv.find_element(By.TAG_NAME, 'body').text
        check('四按钮文案存在', all(x in body for x in ('执行', '新版本', '重命名', '归档')))
        _shot(drv, 'light_00_published_list')

        # ---------- 执行 ----------
        row = _row_by_name(drv, pub_name)
        _drain_network(drv); _start_step('执行')
        _row_btn(drv, row, '执行')
        time.sleep(1.2)
        dlg = drv.find_element(By.TAG_NAME, 'body').text
        check('执行弹窗打开(执行此版本)', '执行此版本' in dlg and '创建日常任务' in dlg, 'dialog present')
        _shot(drv, 'light_01_execute_dialog')
        _drain_network(drv); _network.clear()
        _click_visible(drv, drv.find_elements(By.XPATH,
            "//*[@role='alertdialog' or contains(@class,'AlertDialog')]//button[contains(.,'创建日常任务')]"))
        ok_nav = False
        for _ in range(12):
            time.sleep(0.8)
            cur = drv.current_url
            m = re.search(r'/tasks/(\d+)', cur)
            if m and '/published' not in cur:
                ok_nav = True
                created_task = int(m.group(1))
                break
        time.sleep(1.0)
        _drain_network(drv)
        _capture_step('执行')
        exec_reqs = _reqs('/published-tasks/%d/execute' % anchor_id, 'POST')
        check('执行发真实 POST execute', len(exec_reqs) >= 1,
              json.dumps([r['url'] for r in exec_reqs]))
        check('执行后跳转任务详情 /tasks/{id}', ok_nav, 'task_id=%s url=%s' % (created_task, drv.current_url))
        toasts = [e.text for e in drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
        check('执行 toast 含日常任务已创建', any('日常任务已创建' in t for t in toasts),
              json.dumps(toasts, ensure_ascii=False))
        _shot(drv, 'light_02_after_execute')

        # ---------- 回到已发布列表：新版本 ----------
        drv.get(BASE + '/tasks/published')
        WebDriverWait(drv, 20).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(2.5)
        _wait(drv, By.XPATH, '//tbody/tr', timeout=25)
        row = _row_by_name(drv, pub_name)
        _drain_network(drv); _start_step('新版本')
        _row_btn(drv, row, '新版本')
        time.sleep(1.2)
        dlg = drv.find_element(By.TAG_NAME, 'body').text
        check('新版本弹窗打开(单字段命名)', '新版本名称' in dlg and '留空沿用当前版本名称' in dlg)
        _shot(drv, 'light_03_new_version_dialog')
        _drain_network(drv); _network.clear()
        _click_visible(drv, drv.find_elements(By.XPATH,
            "//*[@role='dialog' and contains(.,'新版本')]//button[normalize-space(.)='确定']"))
        time.sleep(2.5)
        _drain_network(drv)
        _capture_step('新版本')
        ver_reqs = _reqs('/published-tasks/%d/versions' % anchor_id, 'POST')
        check('新版本发真实 POST versions', len(ver_reqs) >= 1, json.dumps([r['url'] for r in ver_reqs]))
        toasts = [e.text for e in drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
        check('新版本 toast 新版本创建成功', any('新版本创建成功' in t for t in toasts),
              json.dumps(toasts, ensure_ascii=False))
        time.sleep(1.0)
        body = drv.find_element(By.TAG_NAME, 'body').text
        check('新版本后列表刷新(共 2 个版本)', '共 2 个版本' in body, 'v2 rendered')
        _shot(drv, 'light_04_after_new_version')

        # 新版本后当前版本是新行：重命名/归档 URL 目标为当前行 id（可能 != anchor_id）
        cur_id = anchor_id
        m = re.search(r'/published-tasks/(\d+)/versions', _reqs('/versions', 'POST')[0]['url']) if _reqs('/versions', 'POST') else None
        if m:
            cur_id = int(m.group(1))  # 请求发往旧 anchor，新行 id 需从 DB 取
        rows = db_sql("SELECT id FROM published_tasks WHERE task_group_id=%d AND is_current=true" % anchor_id)
        if rows.strip().isdigit():
            cur_id = int(rows.strip())

        # ---------- 重命名 ----------
        row = _row_by_name(drv, pub_name)
        _drain_network(drv); _start_step('重命名')
        _row_btn(drv, row, '重命名')
        time.sleep(1.2)
        dlg = drv.find_element(By.TAG_NAME, 'body').text
        check('重命名弹窗打开(单字段+预填)', '新的任务名称' in dlg)
        inp = drv.find_elements(By.XPATH, "//*[@role='dialog' and contains(.,'重命名')]//input")
        check('重命名输入框预填当前名', len(inp) > 0 and inp[0].get_attribute('value') == pub_name,
              'value=%r' % (inp[0].get_attribute('value') if inp else None))
        _shot(drv, 'light_05_rename_dialog')
        new_name = pub_name + '_已重命名'
        if inp:
            drv.execute_script("arguments[0].value='';", inp[0])
            inp[0].send_keys(new_name)
        _drain_network(drv); _network.clear()
        _click_visible(drv, drv.find_elements(By.XPATH,
            "//*[@role='dialog' and contains(.,'重命名')]//button[normalize-space(.)='确定']"))
        time.sleep(2.5)
        _drain_network(drv)
        _capture_step('重命名')
        ren_reqs = _reqs('/published-tasks/%d' % cur_id, 'PUT')
        check('重命名发真实 PUT 到当前版本行', len(ren_reqs) >= 1,
              json.dumps([r['url'] for r in ren_reqs]))
        toasts = [e.text for e in drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
        check('重命名 toast 任务名称已更新', any('任务名称已更新' in t for t in toasts),
              json.dumps(toasts, ensure_ascii=False))
        time.sleep(1.0)
        body = drv.find_element(By.TAG_NAME, 'body').text
        check('重命名后列表刷新显示新名', new_name in body, 'new_name in body')
        _shot(drv, 'light_06_after_rename')

        # ---------- 归档 ----------
        row = _row_by_name(drv, new_name)
        _drain_network(drv); _start_step('归档')
        _row_btn(drv, row, '归档')
        time.sleep(1.2)
        dlg = drv.find_element(By.TAG_NAME, 'body').text
        check('归档弹窗打开(归档已发布任务)', '归档已发布任务' in dlg and '归档后不可直接执行' in dlg)
        _shot(drv, 'light_07_archive_dialog')
        _drain_network(drv); _network.clear()
        _click_visible(drv, drv.find_elements(By.XPATH,
            "//*[@role='alertdialog' or contains(@class,'AlertDialog')]//button[normalize-space(.)='归档']"))
        time.sleep(2.5)
        _drain_network(drv)
        _capture_step('归档')
        arch_reqs = _reqs('/published-tasks/%d/archive' % cur_id, 'POST')
        check('归档发真实 POST archive 到当前版本行', len(arch_reqs) >= 1,
              json.dumps([r['url'] for r in arch_reqs]))
        toasts = [e.text for e in drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
        check('归档 toast 任务已归档', any('任务已归档' in t for t in toasts),
              json.dumps(toasts, ensure_ascii=False))
        time.sleep(1.0)
        body = drv.find_element(By.TAG_NAME, 'body').text
        check('归档后列表刷新(行状态已归档)', '已归档' in body or ('共 1 条' in body and '归档' in body),
              'archived rendered')
        _shot(drv, 'light_08_after_archive')

        # ---------- 深色 ----------
        drv.get(BASE + '/tasks/published')
        WebDriverWait(drv, 20).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(2.5)
        _wait(drv, By.XPATH, '//tbody/tr', timeout=25)
        _set_theme(drv, 'dark')
        drv.get(BASE + '/tasks/published')
        WebDriverWait(drv, 20).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(2.5)
        _wait(drv, By.XPATH, '//tbody/tr', timeout=25)
        _shot(drv, 'dark_01_published_list')

        # ---------- 汇总 Network ----------
        os.makedirs(ARTIFACTS, exist_ok=True)
        with open(os.path.join(ARTIFACTS, 'network_evidence.json'), 'w', encoding='utf-8') as f:
            json.dump(_step_evidence, f, ensure_ascii=False, indent=1)
        with open(os.path.join(ARTIFACTS, 'network_all.json'), 'w', encoding='utf-8') as f:
            json.dump(_network, f, ensure_ascii=False, indent=1)
        print('STEP_EVIDENCE:')
        for e in _step_evidence:
            print('  ', e['step'], e['method'], e['url'], (e.get('postData') or ''))
        print('TOTAL_NET_REQUESTS', len(_network))
        print('created_task=', created_task, 'cur_id=', cur_id)
    finally:
        try:
            drv.quit()
        except Exception:
            pass

    # ---------- 清理 ----------
    if created_task:
        cleanup_daily_task(created_task)
    cleanup_published(anchor_id)

    print('\n===== RESULTS =====')
    fails = [r for r in RESULTS if not r[1]]
    for r in RESULTS:
        print(('PASS' if r[1] else 'FAIL'), '|', r[0], ('| ' + r[2] if r[2] else ''))
    print('TOTAL', len(RESULTS), 'FAIL', len(fails))


if __name__ == '__main__':
    main()
