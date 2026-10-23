# -*- coding: utf-8 -*-
"""INT-1544 验收：filter-all 圈定携带步骤一筛选条件（docker 实测）。

被测前端：docker 容器（由交付分支 6f77e7f8 源码 build，叠加在 wiring/react 头 c72a7871 之上）
          http://localhost:15274  —— 与 15173 同一 nginx 反代配置，同一后端网关。
对照前端：http://localhost:15173（现网镜像，不含本卡修复）—— 只做只读对照。

安全约束：不使用 Network.setRequestInterception（Chrome 155 已移除），用 window.fetch 打点。
          所有 POST /tasks/{id}/start 一律合成响应（避免真实设备下发）；
          --mode baseline 时 POST /tasks 也合成响应（只取证、不写库）。

用法：
  python tests/ui/verify_int1544_accept.py --mode fixed     # 交付分支：真实建任务（接线测试_ 前缀，收尾删除）
  python tests/ui/verify_int1544_accept.py --mode baseline  # 现网镜像：只取请求体，不写库
"""
import argparse
import json
import os
import re
import time
import urllib.parse
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

API = os.environ.get('IAT_API_BASE', 'http://127.0.0.1:15000/api/v1')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1544_accept')
SEARCH_KEY = 'JG0081'
GROUP_NAME = '音频上传生成'
DEVICE_NAME = 'pura90gpt'
TS = time.strftime('%H%M%S')
os.makedirs(ART, exist_ok=True)

FETCH_PATCH = r"""
window.__fetchLog = [];
window.__stub = { tasks: false, start: true };
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = ((init && init.method) || 'GET').toUpperCase();
  const entry = { url: url, method: method };
  if (window.__stub.start && method === 'POST' && /\/tasks\/\d+\/start$/.test(url)) {
    entry.stubbed = 'start'; entry.status = 200;
    window.__fetchLog.push(entry);
    return new Response(JSON.stringify({ success: true, code: 0, message: 'stubbed-by-tester' }),
      { status: 200, headers: { 'Content-Type': 'application/json' } });
  }
  if (window.__stub.tasks && method === 'POST' && /\/tasks(\?|$)/.test(url)) {
    entry.stubbed = 'tasks'; entry.status = 201;
    if (init && init.body) entry.reqBody = String(init.body).slice(0, 2000000);
    window.__fetchLog.push(entry);
    return new Response(JSON.stringify({ success: true, code: 0, data: { id: 999999 } }),
      { status: 201, headers: { 'Content-Type': 'application/json' } });
  }
  try {
    const res = await __origFetch.apply(this, arguments);
    entry.status = res.status;
    if (init && init.body) entry.reqBody = String(init.body).slice(0, 2000000);
    if (url.indexOf('/testcases/ids') !== -1) {
      try { entry.resBody = (await res.clone().text()).slice(0, 400000); } catch (e) {}
    }
    if (url.indexOf('/tasks') !== -1 && method !== 'GET') {
      try { entry.resBody = (await res.clone().text()).slice(0, 4000); } catch (e) {}
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
    for arg in ('--headless=new', '--window-size=1680,1050', '--disable-gpu', '--no-sandbox',
                '--lang=zh-CN', '--disable-dev-shm-usage', '--no-first-run', '--disable-extensions'):
        options.add_argument(arg)
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


def api_json(path):
    with urllib.request.urlopen(API + path, timeout=60) as resp:
        return json.loads(resp.read().decode('utf-8', 'replace'))


def api_call(method, path):
    req = urllib.request.Request(API + path, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, resp.read().decode('utf-8', 'replace')[:300]
    except Exception as e:
        return None, str(e)


def flog(d):
    return d.execute_script('return window.__fetchLog || []')


def summary_text(d):
    xp = "//span[contains(@class,'text-info')][contains(normalize-space(.),'未选择用例时')]"
    try:
        return d.find_element(By.XPATH, xp).text
    except Exception:
        return ''


def wait_summary(d, pattern, timeout=60):
    end = time.time() + timeout
    last = ''
    while time.time() < end:
        last = summary_text(d)
        if pattern.search(last):
            return last
        time.sleep(0.5)
    raise AssertionError('汇总行未达预期 %s，当前=%r' % (pattern.pattern, last))


def net_responses(d, url_part):
    out = []
    for raw in d.get_log('performance'):
        try:
            msg = json.loads(raw['message'])['message']
        except Exception:
            continue
        if msg.get('method') != 'Network.responseReceived':
            continue
        resp = (msg.get('params') or {}).get('response') or {}
        if url_part in (resp.get('url') or ''):
            out.append({'url': resp.get('url'), 'status': resp.get('status')})
    return out


def open_page(d, base):
    d.get('about:blank')
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    d.get(base + '/start-test')
    WebDriverWait(d, 90).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[placeholder*='搜索用例']"))
    )
    wait_summary(d, re.compile(r'全部 \d+ 条用例'))


def go_step2_and_start(d, with_device=True):
    next_btn = WebDriverWait(d, 40).until(
        EC.element_to_be_clickable((By.XPATH, "//button[normalize-space(.)='下一步']"))
    )
    js_click(d, next_btn)
    time.sleep(2)
    if with_device:
        cb = WebDriverWait(d, 60).until(
            EC.presence_of_element_located((By.XPATH, "//*[@aria-label='选择设备 %s']" % DEVICE_NAME))
        )
        if cb.get_attribute('aria-checked') != 'true' and cb.get_attribute('data-state') != 'checked':
            js_click(d, cb)
        time.sleep(1)
    js_click(d, WebDriverWait(d, 40).until(
        EC.element_to_be_clickable((By.XPATH, "//button[normalize-space(.)='开始测试']"))
    ))


def wait_dialog(d, timeout=40):
    dlg = WebDriverWait(d, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "[data-slot='dialog-content']"))
    )
    time.sleep(1)
    return dlg


def submit_named(d, dlg, name):
    inp = dlg.find_element(By.CSS_SELECTOR, '#task-name')
    inp.send_keys(Keys.CONTROL, 'a')
    inp.send_keys(Keys.DELETE)
    inp.send_keys(name)
    js_click(d, dlg.find_element(By.XPATH, ".//button[normalize-space(.)='开始测试']"))


def wait_task_post(d, timeout=150):
    end = time.time() + timeout
    while time.time() < end:
        for e in flog(d):
            u = e.get('url') or ''
            if e.get('method') == 'POST' and '/tasks' in u and 'testcases' not in u \
                    and not re.search(r'/tasks/\d+/start$', u):
                return e
        time.sleep(1)
    raise AssertionError('未捕获 POST /tasks；最近请求=%s' % [
        (e.get('method') or '') + ' ' + (e.get('url') or '') for e in flog(d)][-10:])


def last_ids_entry(d):
    entries = [e for e in flog(d) if e.get('method') == 'POST' and '/testcases/ids' in (e.get('url') or '')]
    return entries[-1] if entries else None


def ids_response_ids(entry):
    try:
        return ((json.loads(entry.get('resBody') or '{}').get('data') or {}).get('ids')) or []
    except Exception:
        return []


def toasts_text(d):
    els = d.find_elements(By.CSS_SELECTOR, "[data-sonner-toast]")
    return [e.text for e in els if e.text]


def set_theme(d, mode):
    # localStorage 不能在 about:blank 写，先落到同源页面再设主题
    d.get(BASE + '/start-test')
    WebDriverWait(d, 90).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[placeholder*='搜索用例']"))
    )
    d.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", mode)
    d.get('about:blank')
    d.get(BASE + '/start-test')
    WebDriverWait(d, 90).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[placeholder*='搜索用例']"))
    )
    wait_summary(d, re.compile(r'全部 \d+ 条用例'))


def scenario_search(base, real_task, art_prefix):
    """搜索 JG0081 → 全部 1 条 → 提交，核对 ids 请求体与 case_ids。"""
    res = {}
    d = driver_new()
    created = None
    try:
        open_page(d, base)
        if not real_task:
            d.execute_script('window.__stub.tasks = true;')
        base_txt = summary_text(d)
        res['summary_initial'] = base_txt
        inp = d.find_element(By.CSS_SELECTOR, "input[placeholder*='搜索用例']")
        inp.send_keys(SEARCH_KEY)
        txt = wait_summary(d, re.compile(r'全部 1 条用例'))
        res['summary_filtered'] = txt
        shot(d, '%s_step1_light_filtered.png' % art_prefix)
        go_step2_and_start(d)
        dlg = wait_dialog(d)
        res['dialog_text'] = dlg.text.replace('\n', ' | ')
        shot(d, '%s_dialog_light.png' % art_prefix)
        if real_task:
            submit_named(d, dlg, '接线测试_INT1544_%s' % TS)
        else:
            submit_named(d, dlg, '接线测试_INT1544_probe_%s' % TS)
        entry = wait_task_post(d)
        body = json.loads(entry['reqBody'])
        res['tasks_status'] = entry.get('status')
        res['tasks_stubbed'] = entry.get('stubbed')
        res['case_ids_count'] = len(body.get('case_ids') or [])
        res['tasks_name'] = body.get('name')
        res['target_modes'] = body.get('target_modes')
        ids_e = last_ids_entry(d)
        if ids_e:
            res['ids_request'] = json.loads(ids_e['reqBody'])
            ids_ids = ids_response_ids(ids_e)
            res['ids_count'] = len(ids_ids)
            res['ids_sample'] = ids_ids[:3]
            res['case_ids_equal_ids'] = (body.get('case_ids') or []) == ids_ids
            res['case_ids_sample'] = (body.get('case_ids') or [])[:3]
        res['network'] = net_responses(d, '/api/v1/tasks')
        if real_task:
            try:
                resp = json.loads(entry.get('resBody') or '{}')
                created = (resp.get('data') or {}).get('id') or resp.get('id')
            except Exception:
                created = None
            res['created_task_id'] = created
            if created:
                detail = api_json('/tasks/%s' % created)
                dd = detail.get('data') or {}
                res['task_readback'] = {k: dd.get(k) for k in ('id', 'name', 'total_cases', 'status')}
            shot(d, '%s_after_submit_light.png' % art_prefix)
        res['ok'] = True
        return res
    finally:
        try:
            d.quit()
        except Exception:
            pass
        res['_created'] = created


def scenario_group(base, art_prefix):
    """分组筛选 + 清空选择 → 提交，核对 group 名与 case_ids 条数。"""
    res = {}
    d = driver_new()
    created = None
    try:
        groups = api_json('/groups?per_page=200')['data']['items']
        g = next((x for x in groups if x.get('name') == GROUP_NAME), None)
        assert g, '分组 %s 不存在' % GROUP_NAME
        total = api_json('/testcases?page=1&per_page=1&group_id=%s' % g['id'])['data']['total']
        res['group'] = GROUP_NAME
        res['group_id'] = g['id']
        res['api_total'] = total

        open_page(d, base)
        trigger = d.find_element(By.XPATH, "//button[.//span[normalize-space(.)='分组']]")
        js_click(d, trigger)
        time.sleep(1)
        js_click(d, WebDriverWait(d, 20).until(
            EC.presence_of_element_located((By.XPATH, "//button[.//span[normalize-space(.)='%s']]" % GROUP_NAME))))
        txt = wait_summary(d, re.compile(r'全部 %d 条用例' % total))
        res['summary_group'] = txt
        shot(d, '%s_step1_light_group.png' % art_prefix)

        # 先手动勾选一条，再「清空选择」——验证 clearSelection 不清筛选条件（否则 filter-all 回退全库）
        res['manual_select'] = 'skipped'
        boxes = [b for b in d.find_elements(By.CSS_SELECTOR, "[role='checkbox']")
                 if b.get_attribute('aria-label') and '选择' in (b.get_attribute('aria-label') or '')]
        if boxes:
            js_click(d, boxes[0])
            time.sleep(1)
            res['manual_select'] = 'clicked'
            res['summary_after_manual'] = summary_text(d)
        clear_btns = d.find_elements(By.XPATH, "//button[normalize-space(.)='清空选择']")
        if clear_btns:
            js_click(d, clear_btns[0])
            time.sleep(1)
            res['clear_clicked'] = True
        else:
            res['clear_clicked'] = False
        res['summary_after_clear'] = summary_text(d)

        go_step2_and_start(d)
        dlg = wait_dialog(d)
        res['dialog_text'] = dlg.text.replace('\n', ' | ')
        shot(d, '%s_dialog_light_group.png' % art_prefix)
        submit_named(d, dlg, '接线测试_INT1544G_%s' % TS)
        entry = wait_task_post(d)
        body = json.loads(entry['reqBody'])
        res['tasks_status'] = entry.get('status')
        res['case_ids_count'] = len(body.get('case_ids') or [])
        ids_e = last_ids_entry(d)
        if ids_e:
            res['ids_request'] = json.loads(ids_e['reqBody'])
            res['case_ids_equal_ids'] = (body.get('case_ids') or []) == ids_response_ids(ids_e)
        try:
            resp = json.loads(entry.get('resBody') or '{}')
            created = (resp.get('data') or {}).get('id') or resp.get('id')
        except Exception:
            created = None
        res['created_task_id'] = created
        if created:
            detail = api_json('/tasks/%s' % created)
            dd = detail.get('data') or {}
            res['task_readback'] = {k: dd.get(k) for k in ('id', 'name', 'total_cases', 'status')}
        res['network'] = net_responses(d, '/api/v1/tasks')
        res['ok'] = True
        return res
    finally:
        try:
            d.quit()
        except Exception:
            pass
        res['_created'] = created


def scenario_empty(base, art_prefix):
    """空筛选 → 入口拦截，不弹窗、不发起 POST /tasks。"""
    res = {}
    d = driver_new()
    try:
        open_page(d, base)
        inp = d.find_element(By.CSS_SELECTOR, "input[placeholder*='搜索用例']")
        inp.send_keys('ZZZ_NO_SUCH_CASE_1544')
        txt = wait_summary(d, re.compile(r'全部 0 条用例'))
        res['summary_empty'] = txt
        shot(d, '%s_step1_light_empty.png' % art_prefix)
        go_step2_and_start(d)
        time.sleep(4)
        res['dialogs'] = len(d.find_elements(By.CSS_SELECTOR, "[data-slot='dialog-content']"))
        res['toasts'] = toasts_text(d)
        posts = [e for e in flog(d) if e.get('method') == 'POST' and '/tasks' in (e.get('url') or '')
                 and 'testcases' not in (e.get('url') or '')]
        res['tasks_posts'] = len(posts)
        shot(d, '%s_empty_blocked.png' % art_prefix)
        res['ok'] = True
        return res
    finally:
        try:
            d.quit()
        except Exception:
            pass


def scenario_dark(base, art_prefix):
    """深色：筛选 1 条 + 任务命名弹窗截图。"""
    res = {}
    d = driver_new()
    try:
        set_theme(d, 'dark')
        inp = d.find_element(By.CSS_SELECTOR, "input[placeholder*='搜索用例']")
        inp.send_keys(SEARCH_KEY)
        res['summary_dark'] = wait_summary(d, re.compile(r'全部 1 条用例'))
        shot(d, '%s_step1_dark_filtered.png' % art_prefix)
        go_step2_and_start(d)
        dlg = wait_dialog(d)
        res['dialog_text_dark'] = dlg.text.replace('\n', ' | ')
        shot(d, '%s_dialog_dark.png' % art_prefix)
        res['ok'] = True
        return res
    finally:
        try:
            d.execute_script("localStorage.setItem('iatp:theme:v1:mode','light');")
        except Exception:
            pass
        try:
            d.quit()
        except Exception:
            pass


def cleanup_task(tid):
    out = {}
    out['stop'] = api_call('POST', '/tasks/%s/stop' % tid)
    out['soft_delete'] = api_call('DELETE', '/tasks/%s' % tid)
    out['purge'] = api_call('DELETE', '/tasks/%s/purge' % tid)
    return out


def sweep_tasks(prefix='接线测试_INT1544'):
    """兜底清理：本卡前缀任务全部 停止 → 软删 → 彻底删除（含场景异常时遗留）。"""
    cleaned = []
    try:
        data = api_json('/tasks?search=%s&per_page=50' % urllib.parse.quote(prefix))['data']
    except Exception as exc:
        return {'error': str(exc)}
    for it in data.get('items', []):
        if prefix in (it.get('name') or ''):
            cleaned.append({'id': it.get('id'), 'name': it.get('name'),
                            'cleanup': cleanup_task(it.get('id'))})
    return {'cleaned': cleaned}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mode', choices=['fixed', 'baseline', 'all'], default='fixed')
    ap.add_argument('--base', default=None)
    args = ap.parse_args()

    global BASE
    out = {'generated_at': time.strftime('%Y-%m-%dT%H:%M:%S'), 'scenarios': {}}
    created_ids = []

    def run(name, fn):
        try:
            out['scenarios'][name] = fn()
        except Exception as exc:  # 场景隔离：一个失败不影响后续取证
            out['scenarios'][name] = {'error': '%s: %s' % (type(exc).__name__, exc)}
            print('SCENARIO FAIL', name, exc)
        tid = (out['scenarios'][name] or {}).get('created_task_id')
        if tid:
            created_ids.append(tid)

    try:
        if args.mode in ('fixed', 'all'):
            BASE = args.base or 'http://localhost:15274'
            out['base_fixed'] = BASE
            run('search', lambda: scenario_search(BASE, True, 'fixed'))
            run('group', lambda: scenario_group(BASE, 'fixed'))
            run('empty', lambda: scenario_empty(BASE, 'fixed'))
            run('dark', lambda: scenario_dark(BASE, 'fixed'))

        if args.mode in ('baseline', 'all'):
            BASE = 'http://localhost:15173'
            out['base_baseline'] = BASE
            run('baseline_search', lambda: scenario_search(BASE, False, 'baseline'))
    finally:
        out['cleanup'] = {str(t): cleanup_task(t) for t in created_ids}
        out['sweep'] = sweep_tasks()
        out['post_cleanup_search'] = api_call('GET', '/tasks?search=接线测试_INT1544')[1][:300]
        path = os.path.join(ART, 'evidence_%s.json' % args.mode)
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(out, fh, ensure_ascii=False, indent=2, default=str)
        print('EVIDENCE', path)

    print(json.dumps({k: {kk: vv for kk, vv in (v or {}).items() if kk in (
        'summary_filtered', 'summary_group', 'summary_after_clear', 'summary_empty', 'dialog_text',
        'case_ids_count', 'ids_request', 'tasks_status', 'created_task_id', 'task_readback',
        'case_ids_equal_ids', 'tasks_posts', 'dialogs', 'toasts', 'error')}
        for k, v in out['scenarios'].items()}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    BASE = 'http://localhost:15274'
    main()
