# -*- coding: utf-8 -*-
"""INT-1542 验收：手动勾选用例后「开始测试」应打开任务命名弹窗（不再恒报无可用用例）。

连本 run 的 dev server（默认 5342，源码含交付分支 67a9659f）→ docker 真实库栈网关 15000。
GET /testcases 在该栈约 45~55s（全表聚合），页面首屏与分组内懒加载都要等，故各组用例等待放宽。

覆盖：
  A 浅色 happy path：手动勾选 2 条 → 摘要「已选 2 条用例」→ 下一步 → 选设备 → 开始测试
    → 弹窗（摘要 2 条 · 1 台 · 0 个）→ 真实创建/启动 → 回读 → 清理
  B 反向：勾选后全部取消（手动集空、filterAllMode=false）→ 拦截 toast，不开弹窗
  C 回归：未手动选择（filterAllMode=true）→ 弹窗照常打开
  D 深色：手动勾选 2 条 → 弹窗
证据：浅/深色截图 + performance log（POST /tasks 状态）。
"""
import json
import os
import sys
import time

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:5342')
API = os.environ.get('BACKEND_API', 'http://127.0.0.1:15000')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.path.join('tests', 'ui', 'artifacts', 'int1542')
THEME_KEY = 'iatp:theme:v1:mode'
TASK_PREFIX = '接线测试_INT1542'
NO_CASE_MSG = '没有可用的测试用例'
CASE_WAIT = int(os.environ.get('CASE_WAIT', '120'))

results = []


def check(name, ok, detail=''):
    results.append((name, ok, detail))
    print(('PASS' if ok else 'FAIL') + ' | ' + name + (' | ' + detail if detail else ''))
    return ok


def shot(driver, name):
    os.makedirs(ART, exist_ok=True)
    path = os.path.join(ART, name)
    driver.save_screenshot(path)
    print('SHOT ' + path)
    return path


def js(driver, script, *args):
    return driver.execute_script(script, *args)


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--no-first-run')
    options.add_argument('--no-default-browser-check')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-background-networking')
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    import shutil
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    drv = os.environ.get('CHROMEDRIVER', '')
    if not drv and chrome_major and os.path.isdir(cache_root):
        cands = [os.path.join(cache_root, v, 'chromedriver.exe') for v in os.listdir(cache_root)]
        cands = [c for c in cands if os.path.isfile(c)]
        if cands:
            drv = sorted(cands)[-1]
    if not drv:
        drv = shutil.which('chromedriver') or ''
    service = Service(drv) if drv else Service()
    return webdriver.Chrome(service=service, options=options)


def open_start_test(driver, dark=False, wait_cases=True):
    driver.get(BASE + '/')
    js(driver, "window.localStorage.setItem(arguments[0], arguments[1]);",
       THEME_KEY, 'dark' if dark else 'light')
    last = None
    for attempt in range(3):
        driver.get(BASE + '/start-test')
        try:
            WebDriverWait(driver, 90).until(
                lambda d: d.find_elements(By.CSS_SELECTOR, "[aria-label^='全选分组 ']")
            )
            last = None
            break
        except Exception as exc:  # 网关偶发 ECONNRESET（proxy），重载一次
            last = exc
            time.sleep(3)
    if last is not None:
        raise last
    if wait_cases:
        # 用例列表 GET /testcases 在该栈约 45~55s；以「未选择…使用全部 N 条用例」的 N>0 判定已加载
        WebDriverWait(driver, CASE_WAIT).until(
            lambda d: any(int(n) > 0 for n in
                          __import__('re').findall(r'使用全部\s*(\d+)\s*条用例',
                                                   d.find_element(By.TAG_NAME, 'body').text))
        )
    time.sleep(1.0)


def group_labels(driver):
    return js(driver, """
        return Array.from(document.querySelectorAll("[aria-label^='全选分组 ']"))
          .map(e => e.getAttribute('aria-label').replace('全选分组 ', ''));
    """)


def case_boxes(driver):
    return driver.find_elements(By.CSS_SELECTOR, "[aria-label^='选择 ']")


def expand_first_group_with_cases(driver, timeout=CASE_WAIT):
    """点开第一个分组，等组内用例卡渲染（组内懒加载 GET /testcases 很慢）。"""
    handles = driver.find_elements(By.CSS_SELECTOR, "[aria-label^='全选分组 ']")
    for idx, cb in enumerate(handles):
        try:
            header = cb.find_element(By.XPATH, './..')
            js(driver, "arguments[0].click();", header)
            deadline = time.time() + timeout
            while time.time() < deadline:
                if case_boxes(driver):
                    label = cb.get_attribute('aria-label').replace('全选分组 ', '')
                    return label, len(case_boxes(driver))
                time.sleep(2)
        except Exception:
            continue
    return None, 0


def pick_cases(driver, n=2):
    boxes = case_boxes(driver)
    picked = []
    for box in boxes[:n]:
        label = box.get_attribute('aria-label')
        js(driver, "arguments[0].click();", box)
        picked.append(label.replace('选择 ', ''))
        time.sleep(0.5)
    return picked


def own_summary(driver):
    """步骤一侧的「已选 N 条用例」汇总行（外层 span 文本，内层只有数字）。"""
    return js(driver, """
        const hits = Array.from(document.querySelectorAll('span'))
          .map(e => (e.textContent || '').trim())
          .filter(t => /^已选\\s*\\d+\\s*条用例$/.test(t));
        return hits.join(' | ');
    """)


def footer_click(driver, label):
    btn = WebDriverWait(driver, 25).until(
        lambda d: [b for b in d.find_elements(By.TAG_NAME, 'button') if b.text.strip() == label] or False
    )
    js(driver, "arguments[0].click();", btn[0])
    time.sleep(1.0)


def pick_first_online_device(driver):
    """选第一台在线（未 aria-disabled）设备；返回名称。"""
    WebDriverWait(driver, 60).until(
        lambda d: d.find_elements(By.CSS_SELECTOR, "[aria-label^='选择设备 ']")
    )
    picked = js(driver, """
        const boxes = Array.from(document.querySelectorAll("[aria-label^='选择设备 ']"));
        const el = boxes.find(b => b.getAttribute('aria-disabled') !== 'true'
                                  && !b.hasAttribute('data-disabled')
                                  && b.getAttribute('data-disabled') !== '');
        if (!el) return null;
        el.click();
        return el.getAttribute('aria-label').replace('选择设备 ', '');
    """)
    time.sleep(1.2)
    return picked


def resources_summary(driver):
    return js(driver, """
        const t = document.body.innerText;
        const m = t.match(/已选[^\\n]{0,40}/g) || [];
        return m.join(' | ');
    """)


def dialog_state(driver):
    return js(driver, """
        const dlgs = Array.from(document.querySelectorAll("[role='dialog']"));
        const d = dlgs.find(x => (x.textContent || '').includes('任务名称'));
        if (!d) return null;
        const r = d.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) return null;
        const summary = Array.from(d.querySelectorAll('p')).map(p => p.textContent.trim()).join(' | ');
        return { summary };
    """)


def toast_texts(driver):
    return js(driver, """
        return Array.from(document.querySelectorAll("[data-sonner-toast]"))
          .map(t => (t.textContent || '').trim());
    """)


def clear_toasts(driver):
    js(driver, "document.querySelectorAll('[data-sonner-toast]').forEach(t => t.remove());")


def drain_perf(driver):
    driver.get_log('performance')


def network_after(driver):
    out = []
    for entry in driver.get_log('performance'):
        try:
            out.append(json.loads(entry['message'])['message'])
        except Exception:
            continue
    return out


def task_posts(msgs):
    reqs, pairs = {}, []
    for msg in msgs:
        method = msg.get('method')
        p = msg.get('params', {})
        if method == 'Network.requestWillBeSent':
            req = p.get('request', {})
            if '/api/v1/tasks' in req.get('url', ''):
                reqs[p.get('requestId')] = {'method': req.get('method'), 'url': req.get('url')}
        elif method == 'Network.responseReceived':
            rid = p.get('requestId')
            if rid in reqs:
                pairs.append({**reqs[rid], 'status': p.get('response', {}).get('status')})
    return pairs


def api_cleanup(task_id):
    out = []
    for url, label in (
        (API + '/api/v1/tasks/%s' % task_id, 'soft'),
        (API + '/api/v1/tasks/%s/purge' % task_id, 'purge'),
    ):
        try:
            r = requests.delete(url, timeout=60)
            out.append((label, r.status_code, r.text[:100]))
        except Exception as exc:
            out.append((label, 'EXC', str(exc)[:100]))
    return out


def api_get(path, **params):
    r = requests.get(API + path, params=params, timeout=90)
    return r.status_code, (r.json() if r.headers.get('content-type', '').startswith('application/json') else {})


def find_task(name):
    code, data = api_get('/api/v1/tasks', page=1, page_size=100, search=name)
    body = data.get('data', data) if isinstance(data, dict) else {}
    items = body.get('items', [])
    hits = [t for t in items if t.get('name') == name]
    return (hits[0] if hits else None), code


def scenario_a_light_happy():
    """浅色 happy path + 真实创建/启动 + 回读/清理。"""
    created = []
    driver = _driver()
    try:
        open_start_test(driver, dark=False)
        labels = group_labels(driver)
        check('A 步骤一用例分组已渲染（真实数据）', len(labels) > 2, 'groups=%d %s' % (len(labels), labels[:4]))
        shot(driver, '01_step1_loaded_light.png')

        group, rendered = expand_first_group_with_cases(driver)
        check('A 展开分组后可勾选用例', bool(group) and rendered > 0,
              'group=%s rendered=%d' % (group, rendered))

        picked = pick_cases(driver, 2)
        time.sleep(1.0)
        stext = own_summary(driver)
        check('A 勾选 2 条后汇总行显示「已选 2 条用例」', '已选 2 条用例' in stext, stext or '(空)')
        shot(driver, '02_step1_two_selected_light.png')

        footer_click(driver, '下一步')
        device = pick_first_online_device(driver)
        check('A 步骤二选中在线设备', bool(device), str(device))
        rsum = resources_summary(driver)
        print('RESOURCE_SUMMARY', rsum)
        clear_toasts(driver)
        drain_perf(driver)

        footer_click(driver, '开始测试')
        time.sleep(1.5)
        dlg = dialog_state(driver)
        toasts = toast_texts(driver)
        check('A 手动勾选后点「开始测试」打开任务命名弹窗', bool(dlg), str(dlg))
        check('A 未出现「没有可用的测试用例」toast',
              all(NO_CASE_MSG not in t for t in toasts), str(toasts))
        check('A 弹窗摘要为 2 条 · 1 台 · 0 个',
              bool(dlg) and '2 条' in dlg['summary'] and '1 台' in dlg['summary'] and '0 个' in dlg['summary'],
              (dlg or {}).get('summary', ''))
        shot(driver, '03_task_name_dialog_manual_light.png')
        if not dlg:
            return created

        name = TASK_PREFIX + '_' + time.strftime('%H%M%S')
        js(driver, """
            const el = document.getElementById('task-name');
            el.focus();
            const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            setter.call(el, arguments[0]);
            el.dispatchEvent(new Event('input', { bubbles: true }));
        """, name)
        time.sleep(0.5)
        btns = [b for b in driver.find_elements(By.CSS_SELECTOR, "[role='dialog'] button")
                if b.text.strip() == '开始测试']
        check('A 弹窗内「开始测试」按钮可点（名称已填）', bool(btns), 'buttons=%d' % len(btns))
        if not btns:
            return created
        js(driver, "arguments[0].click();", btns[0])

        WebDriverWait(driver, 90).until(lambda d: 'step=3' in d.current_url)
        time.sleep(2.5)
        calls = task_posts(network_after(driver))
        posts = [c for c in calls if c['method'] == 'POST' and c['url'].rstrip('/').endswith('/api/v1/tasks')]
        starts = [c for c in calls if c['method'] == 'POST' and c['url'].rstrip('/').endswith('/start')]
        check('A 创建任务 POST /tasks 成功（2xx）',
              bool(posts) and posts[0].get('status', 0) < 300,
              str([(c['method'], c['url'].split('/api')[-1], c.get('status')) for c in posts]))
        check('A 启动任务 POST /tasks/{id}/start 成功（2xx）',
              bool(starts) and starts[0].get('status', 0) < 300,
              str([(c['url'].split('/api')[-1], c.get('status')) for c in starts]))
        check('A 提交后跳执行步骤 step=3', 'step=3' in driver.current_url, driver.current_url)
        shot(driver, '04_step_after_submit_light.png')

        hit, code = find_task(name)
        check('A 回读任务存在', bool(hit), 'name=%s status=%s id=%s' % (name, code, (hit or {}).get('id')))
        if hit:
            tid = hit['id']
            created.append(tid)
            check('A 任务用例数 = 勾选的 2 条',
                  hit.get('case_count') == 2 or hit.get('total_cases') == 2,
                  'case_count=%s total_cases=%s' % (hit.get('case_count'), hit.get('total_cases')))
            check('A 任务已启动（queued/running/…）',
                  hit.get('status') in ('queued', 'running', 'pending', 'executing', 'failed', 'completed'),
                  str(hit.get('status')))
    finally:
        driver.quit()
        for tid in created:
            print('CLEANUP', tid, api_cleanup(tid))
    return created


def scenario_b_negative():
    """勾选后全部取消（手动集空）→ 拦截 toast，不开弹窗。"""
    driver = _driver()
    try:
        open_start_test(driver)
        expand_first_group_with_cases(driver)
        pick_cases(driver, 2)
        time.sleep(1.0)
        picked_text = own_summary(driver)
        # 再点一次同样两处 → 取消勾选
        boxes = case_boxes(driver)[:2]
        for box in boxes:
            js(driver, "arguments[0].click();", box)
            time.sleep(0.5)
        stext = own_summary(driver)
        check('B 取消勾选后手动集为空（已选 0 条用例）', '已选 0 条用例' in stext,
              'before=%s after=%s' % (picked_text, stext))
        footer_click(driver, '下一步')
        device = pick_first_online_device(driver)
        clear_toasts(driver)
        footer_click(driver, '开始测试')
        time.sleep(1.5)
        dlg = dialog_state(driver)
        toasts = toast_texts(driver)
        check('B 手动集为空时不开任务命名弹窗', not dlg, str(dlg))
        check('B toast 提示「没有可用的测试用例」', any(NO_CASE_MSG in t for t in toasts), str(toasts))
        shot(driver, '05_empty_selection_blocked_light.png')
    finally:
        driver.quit()


def scenario_c_filter_all():
    """未手动选择（filterAllMode=true）→ 弹窗照常打开。"""
    driver = _driver()
    try:
        open_start_test(driver)
        footer_click(driver, '下一步')
        device = pick_first_online_device(driver)
        check('C 步骤二选中在线设备', bool(device), str(device))
        clear_toasts(driver)
        footer_click(driver, '开始测试')
        time.sleep(1.5)
        dlg = dialog_state(driver)
        check('C filter-all（未手动选择）弹窗照常打开', bool(dlg), (dlg or {}).get('summary', ''))
        shot(driver, '06_filterall_dialog_light.png')
        if dlg:
            btns = [b for b in driver.find_elements(By.CSS_SELECTOR, "[role='dialog'] button")
                    if b.text.strip() == '取消']
            if btns:
                js(driver, "arguments[0].click();", btns[0])
    finally:
        driver.quit()


def scenario_d_dark():
    driver = _driver()
    try:
        open_start_test(driver, dark=True)
        expand_first_group_with_cases(driver)
        pick_cases(driver, 2)
        time.sleep(1.0)
        check('D 深色：勾选 2 条', '已选 2 条用例' in own_summary(driver), own_summary(driver))
        shot(driver, '07_step1_two_selected_dark.png')
        footer_click(driver, '下一步')
        pick_first_online_device(driver)
        clear_toasts(driver)
        footer_click(driver, '开始测试')
        time.sleep(1.5)
        dlg = dialog_state(driver)
        check('D 深色：手动勾选 2 条后弹窗打开', bool(dlg), (dlg or {}).get('summary', ''))
        shot(driver, '08_task_name_dialog_manual_dark.png')
        if dlg:
            btns = [b for b in driver.find_elements(By.CSS_SELECTOR, "[role='dialog'] button")
                    if b.text.strip() == '取消']
            if btns:
                js(driver, "arguments[0].click();", btns[0])
    finally:
        driver.quit()


def main():
    picked = os.environ.get('SCENARIOS', 'A,B,C,D').split(',')
    created = []
    if 'A' in picked:
        created += scenario_a_light_happy()
    if 'B' in picked:
        scenario_b_negative()
    if 'C' in picked:
        scenario_c_filter_all()
    if 'D' in picked:
        scenario_d_dark()

    # 残留核对
    code, data = api_get('/api/v1/tasks', page=1, page_size=100, search=TASK_PREFIX)
    body = data.get('data', data) if isinstance(data, dict) else {}
    leftovers = [t for t in body.get('items', []) if t.get('name', '').startswith(TASK_PREFIX)]
    check('清理后无本卡残留任务', not leftovers, 'status=%s remaining=%s' % (code, [t.get('name') for t in leftovers]))

    failed = [r for r in results if not r[1]]
    print('SUMMARY pass=%d fail=%d' % (len(results) - len(failed), len(failed)))
    return 1 if failed else 0


if __name__ == '__main__':
    import traceback
    try:
        code = main()
    except Exception:
        traceback.print_exc()
        code = 2
    sys.exit(code)
