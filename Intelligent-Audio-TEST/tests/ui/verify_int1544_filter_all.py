# -*- coding: utf-8 -*-
"""INT-1544 交付附证：开始测试 filter-all 携带步骤一筛选条件（真实数据浏览器实测）。

环境：dev server 5333（本 worktree 源码）→ docker 网关 http://localhost:15000（AUTH_MODE=off）。
缺陷：步骤一搜索把列表筛到 1 条、汇总行「全部 1 条用例」，提交 POST /tasks 却按全部用例
（582 条）建任务。修复后 filter-all 圈定与界面同源。

本脚本核对：
1. 步骤一搜索「JG0081」→ 汇总行「未选择用例时，将按当前筛选条件使用全部 1 条用例」；
2. 下一步 → 选设备 → 开始测试 → 任务名称弹窗摘要显示「1 条」（INT-1544 附带修复）；
3. 提交时抓 POST /testcases/ids 请求体（应含 search=JG0081）与 POST /tasks 请求体
   （case_ids 应恰为 1 条，且等于接口按同一筛选返回的 id）；
4. Network（performance log）确认 POST /tasks 状态码；
5. 浅/深色截图；
6. 写数据纪律：任务名「接线测试_INT1544_」前缀，run 结束前停止 + 软删 + 彻底删除。

运行：PYTHONIOENCODING=utf-8 python tests/ui/verify_int1544_filter_all.py
"""
import json
import os
import re
import time
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5333')
API = os.environ.get('IAT_API_BASE', 'http://127.0.0.1:15000/api/v1')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1544')
SEARCH_KEY = 'JG0081'
DEVICE_NAME = 'pura90gpt'
SUFFIX = int(time.time())
TASK_NAME = '接线测试_INT1544_%d' % SUFFIX
os.makedirs(ART, exist_ok=True)

FETCH_PATCH = r"""
window.__fetchLog = [];
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = ((init && init.method) || 'GET').toUpperCase();
  const entry = { url: url, method: method };
  try {
    const res = await __origFetch.apply(this, arguments);
    entry.status = res.status;
    if (init && init.body) entry.reqBody = String(init.body).slice(0, 200000);
    if (url.indexOf('/tasks') !== -1 || url.indexOf('/testcases/ids') !== -1) {
      try { entry.resBody = (await res.clone().text()).slice(0, 2000); } catch (e) {}
    }
    window.__fetchLog.push(entry);
    return res;
  } catch (e) {
    entry.error = String(e);
    window.__fetchLog.push(entry);
    throw e;
  }
};
"""


def driver_new():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--no-first-run')
    options.add_argument('--disable-extensions')
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    drv_path = ''
    if os.path.isdir(cache_root):
        cands = []
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
                except ValueError:
                    continue
        if cands:
            drv_path = sorted(cands, key=lambda c: c[0])[0][1]
    service = Service(drv_path) if drv_path else Service()
    d = webdriver.Chrome(service=service, options=options)
    d.set_page_load_timeout(120)
    return d


def js_click(d, el):
    d.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)


def shot(d, name):
    path = os.path.join(ART, name)
    d.save_screenshot(path)
    print('SHOT', path)
    return path


def net_status(d, url_part, method='POST'):
    """从 performance log 取请求的最终响应状态（双层解包）。"""
    found = []
    for raw in d.get_log('performance'):
        try:
            msg = json.loads(raw['message'])['message']
        except Exception:
            continue
        if msg.get('method') != 'Network.responseReceived':
            continue
        params = msg.get('params') or {}
        resp = params.get('response') or {}
        if url_part in (resp.get('url') or ''):
            found.append({'url': resp.get('url'), 'status': resp.get('status'), 'mime': resp.get('mimeType')})
    return found


def api_call(method, path, body=None):
    url = API + path
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode('utf-8', 'replace')[:500]
    except Exception as e:
        return None, str(e)


def fetch_log(d):
    return d.execute_script('return window.__fetchLog || []')


def wait_summary(d, expect, timeout=40):
    """expect 为字符串（子串）或 compiled regex；返回命中的汇总行文本。"""
    end = time.time() + timeout
    last = ''
    xp = "//span[contains(@class,'text-info')][contains(normalize-space(.),'未选择用例时')]"
    while time.time() < end:
        try:
            txt = d.find_element(By.XPATH, xp).text
        except Exception:
            txt = ''
        last = txt
        if hasattr(expect, 'search'):
            if expect.search(txt):
                return txt
        elif expect in txt:
            return txt
        time.sleep(0.5)
    raise AssertionError('汇总行未出现预期 %r，当前=%r' % (expect, last))


def open_task_dialog(d):
    """步骤一 → 下一步 → 选设备 → 开始测试（返回弹窗元素）。"""
    next_btn = WebDriverWait(d, 30).until(
        EC.element_to_be_clickable((By.XPATH, "//button[normalize-space(.)='下一步']"))
    )
    js_click(d, next_btn)
    time.sleep(2)
    cb = WebDriverWait(d, 40).until(
        EC.presence_of_element_located((By.XPATH, "//*[@aria-label='选择设备 %s']" % DEVICE_NAME))
    )
    if cb.get_attribute('aria-checked') != 'true' and cb.get_attribute('data-state') != 'checked':
        js_click(d, cb)
    time.sleep(1)
    start_btn = WebDriverWait(d, 30).until(
        EC.element_to_be_clickable((By.XPATH, "//button[normalize-space(.)='开始测试']"))
    )
    js_click(d, start_btn)
    dialog = WebDriverWait(d, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "[data-slot='dialog-content']"))
    )
    time.sleep(1)
    return dialog


def fill_task_name(d, dialog, name):
    inp = dialog.find_element(By.CSS_SELECTOR, '#task-name')
    inp.send_keys(Keys.CONTROL, 'a')
    inp.send_keys(Keys.DELETE)
    inp.send_keys(name)
    time.sleep(0.3)
    return inp.get_attribute('value')


def main():
    results = []
    created_task_id = None
    d = driver_new()
    try:
        # ---- 浅色：缺陷复现路径 ----
        d.get('about:blank')
        d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
        d.get(BASE + '/start-test')
        WebDriverWait(d, 60).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[placeholder*='搜索用例']"))
        )
        base_txt = wait_summary(d, re.compile(r'全部 [1-9]\d* 条用例'))
        results.append('初始汇总行：%s' % base_txt)

        inp = d.find_element(By.CSS_SELECTOR, "input[placeholder*='搜索用例']")
        inp.send_keys(SEARCH_KEY)
        txt = wait_summary(d, '全部 1 条用例')
        results.append('搜索 %s 后汇总行：%s' % (SEARCH_KEY, txt))
        shot(d, 'step1_light_filtered_1.png')

        dialog = open_task_dialog(d)
        dlg_text = dialog.text.replace('\n', ' | ')
        print('DIALOG:', dlg_text)
        results.append('任务名称弹窗：%s' % dlg_text)
        shot(d, 'dialog_light.png')

        name_val = fill_task_name(d, dialog, TASK_NAME)
        results.append('任务名称输入：%s' % name_val)

        # 提交
        confirm = dialog.find_element(By.XPATH, ".//button[normalize-space(.)='开始测试']")
        js_click(d, confirm)
        # 等 POST /tasks 落地
        end = time.time() + 120
        task_entry = None
        while time.time() < end:
            for e in fetch_log(d):
                if e.get('method') == 'POST' and '/tasks' in (e.get('url') or '') and not (e.get('url') or '').rstrip('/').endswith('/ids'):
                    if 'testcases' not in (e.get('url') or ''):
                        task_entry = e
                        break
            if task_entry:
                break
            time.sleep(1)
        assert task_entry, '未捕获 POST /tasks'
        body = json.loads(task_entry['reqBody'])
        results.append('POST /tasks 状态：%s' % task_entry.get('status'))
        results.append('POST /tasks 请求体 name=%s case_ids=%d' % (body.get('name'), len(body.get('case_ids') or [])))
        print('TASK BODY:', json.dumps({k: body[k] for k in ('name', 'device_ids', 'api_ids', 'target_modes')}, ensure_ascii=False))
        print('CASE_IDS_SAMPLE:', (body.get('case_ids') or [])[:3])

        # 抓 /testcases/ids 的圈定请求
        ids_entries = [e for e in fetch_log(d) if e.get('method') == 'POST' and '/testcases/ids' in (e.get('url') or '')]
        assert ids_entries, '未捕获 POST /testcases/ids（filter-all 圈定）'
        ids_body = json.loads(ids_entries[-1]['reqBody'])
        results.append('POST /testcases/ids 请求体：%s' % json.dumps(ids_body, ensure_ascii=False))
        ids_resp = ids_entries[-1].get('resBody') or ''
        try:
            ids_ids = (json.loads(ids_resp).get('data') or {}).get('ids') or []
        except Exception:
            ids_ids = []
        results.append('POST /testcases/ids 返回 %d 条：%s' % (len(ids_ids), ids_ids[:3]))

        # 断言
        assert ids_body.get('search') == SEARCH_KEY, 'ids 请求未携带 search=%s：%s' % (SEARCH_KEY, ids_body)
        assert len(body.get('case_ids') or []) == 1, 'case_ids 应为 1 条，实际 %d' % len(body.get('case_ids') or [])
        assert body['case_ids'] == ids_ids, 'case_ids 与 ids 接口返回不一致'
        results.append('✅ 断言通过：filter-all 圈定 = 搜索筛选的 1 条用例')

        # 响应体取任务 id（用于清理）
        try:
            resp = json.loads(task_entry.get('resBody') or '{}')
            created_task_id = (resp.get('data') or {}).get('id') or resp.get('id')
        except Exception:
            created_task_id = None
        print('TASK_ID:', created_task_id)
        if created_task_id:
            results.append('新建任务 id=%s（接线测试前缀，收尾删除）' % created_task_id)

        time.sleep(3)
        shot(d, 'after_submit_light.png')
        net = net_status(d, '/tasks')
        print('NET:', net)
        results.append('Network /tasks 响应：%s' % json.dumps(
            [n for n in net if n['status'] >= 200][-3:], ensure_ascii=False))
        evidence = {
            'generated_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
            'ui_summary_after_filter': txt,
            'task_dialog_summary': dlg_text,
            'post_testcases_ids_request': ids_body,
            'post_testcases_ids_response_count': len(ids_ids),
            'post_testcases_ids_response_ids': ids_ids,
            'post_tasks_status': task_entry.get('status'),
            'post_tasks_case_ids_count': len(body.get('case_ids') or []),
            'post_tasks_body': body,
            'network': net,
        }
        ev_path = os.path.join(ART, 'task_submit_evidence.json')
        with open(ev_path, 'w', encoding='utf-8') as fh:
            json.dump(evidence, fh, ensure_ascii=False, indent=2)
        print('EVIDENCE', ev_path)

        # ---- 深色 ----
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark');")
        d.get('about:blank')
        d.get(BASE + '/start-test')
        WebDriverWait(d, 60).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[placeholder*='搜索用例']"))
        )
        wait_summary(d, re.compile(r'全部 [1-9]\d* 条用例'))
        inp = d.find_element(By.CSS_SELECTOR, "input[placeholder*='搜索用例']")
        inp.send_keys(SEARCH_KEY)
        wait_summary(d, '全部 1 条用例')
        shot(d, 'step1_dark_filtered_1.png')
        dialog = open_task_dialog(d)
        shot(d, 'dialog_dark.png')
        results.append('深色截图完成')
    finally:
        # 恢复浅色，避免污染后续 run 的默认主题
        try:
            d.execute_script("localStorage.setItem('iatp:theme:v1:mode','light');")
        except Exception:
            pass
        try:
            d.quit()
        except Exception:
            pass
        # 写数据清理：停止 → 软删 → 彻底删除
        if created_task_id:
            print('CLEANUP stop:', api_call('POST', '/tasks/%s/stop' % created_task_id))
            print('CLEANUP soft-delete:', api_call('DELETE', '/tasks/%s' % created_task_id))
            print('CLEANUP purge:', api_call('DELETE', '/tasks/%s/purge' % created_task_id))
            results.append('清理：任务 %s 停止+软删+彻底删除' % created_task_id)

    print('\n=== RESULTS ===')
    for r in results:
        print('-', r)


if __name__ == '__main__':
    main()
