# -*- coding: utf-8 -*-
"""INT-1544 附证 B：分组筛选 + 「清空选择」后 filter-all 仍按筛选圈定。

环境同 verify_int1544_filter_all.py（dev 5333 → docker 网关 15000）。
核对：
1. 步骤一分组筛选「音频上传生成」→ 汇总行「全部 N 条」= 该分组真实用例数（GET /testcases total）；
2. 点「清空选择」（INT-1544 起 clearSelection 不再清筛选条件）→ 汇总行仍为 N；
3. 提交时 POST /testcases/ids 请求体携带 group 名（不是 group_id）、POST /tasks case_ids = N 条；
4. 任务名称弹窗摘要显示 N 条；
5. 写数据纪律：任务名「接线测试_INT1544G_」，收尾停止 + 软删 + 彻底删除。
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
GROUP_NAME = '音频上传生成'
DEVICE_NAME = 'pura90gpt'
TASK_NAME = '接线测试_INT1544G_%d' % int(time.time())
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
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--no-first-run')
    options.add_argument('--disable-extensions')
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


def api_get(path):
    req = urllib.request.Request(API + path)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode('utf-8', 'replace'))


def api_call(method, path):
    req = urllib.request.Request(API + path, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode('utf-8', 'replace')[:300]
    except Exception as e:
        return None, str(e)


def summary_text(d):
    xp = "//span[contains(@class,'text-info')][contains(normalize-space(.),'未选择用例时')]"
    try:
        return d.find_element(By.XPATH, xp).text
    except Exception:
        return ''


def wait_summary(d, pattern, timeout=45):
    end = time.time() + timeout
    last = ''
    while time.time() < end:
        last = summary_text(d)
        if pattern.search(last):
            return last
        time.sleep(0.5)
    raise AssertionError('汇总行未达预期 %s，当前=%r' % (pattern.pattern, last))


def main():
    results = []
    created = None
    d = driver_new()
    try:
        # 分组真实用例数
        groups = api_get('/groups?per_page=200')['data']['items']
        g = next(x for x in groups if x.get('name') == GROUP_NAME)
        gid = g['id']
        total = api_get('/testcases?page=1&per_page=1&group_id=%s' % gid)['data']['total']
        results.append('分组「%s」id=%s，GET /testcases total=%s' % (GROUP_NAME, gid, total))

        d.get('about:blank')
        d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
        d.get(BASE + '/start-test')
        WebDriverWait(d, 60).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[placeholder*='搜索用例']"))
        )
        wait_summary(d, re.compile(r'全部 \d+ 条用例'))

        # 分组 facet
        trigger = d.find_element(By.XPATH, "//button[.//span[normalize-space(.)='分组']]")
        js_click(d, trigger)
        time.sleep(1)
        opt = WebDriverWait(d, 20).until(
            EC.presence_of_element_located(
                (By.XPATH, "//button[.//span[normalize-space(.)='%s']]" % GROUP_NAME)
            )
        )
        js_click(d, opt)
        time.sleep(2)
        txt = wait_summary(d, re.compile(r'全部 %d 条用例' % total))
        results.append('分组筛选后汇总行：%s' % txt)
        d.save_screenshot(os.path.join(ART, 'step1_light_group_filtered.png'))

        # 清空选择（INT-1544：不再清筛选条件）
        clear_btn = d.find_element(By.XPATH, "//button[normalize-space(.)='清空选择']")
        js_click(d, clear_btn)
        time.sleep(1)
        txt2 = summary_text(d)
        results.append('点「清空选择」后汇总行：%s' % txt2)
        assert ('全部 %d 条用例' % total) in txt2, '清空选择后筛选丢失：%r' % txt2

        # 下一步 → 选设备 → 开始测试
        js_click(d, d.find_element(By.XPATH, "//button[normalize-space(.)='下一步']"))
        time.sleep(2)
        cb = WebDriverWait(d, 40).until(
            EC.presence_of_element_located((By.XPATH, "//*[@aria-label='选择设备 %s']" % DEVICE_NAME))
        )
        if cb.get_attribute('aria-checked') != 'true' and cb.get_attribute('data-state') != 'checked':
            js_click(d, cb)
        time.sleep(1)
        js_click(d, d.find_element(By.XPATH, "//button[normalize-space(.)='开始测试']"))
        dialog = WebDriverWait(d, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "[data-slot='dialog-content']"))
        )
        time.sleep(1)
        dlg_text = dialog.text.replace('\n', ' | ')
        results.append('任务名称弹窗：%s' % dlg_text)
        assert ('%d 条' % total) in dlg_text, '弹窗摘要用例数不符：%r' % dlg_text

        inp = dialog.find_element(By.CSS_SELECTOR, '#task-name')
        inp.send_keys(Keys.CONTROL, 'a')
        inp.send_keys(Keys.DELETE)
        inp.send_keys(TASK_NAME)
        js_click(d, dialog.find_element(By.XPATH, ".//button[normalize-space(.)='开始测试']"))

        end = time.time() + 120
        task_entry = None
        while time.time() < end and not task_entry:
            for e in d.execute_script('return window.__fetchLog || []'):
                if e.get('method') == 'POST' and '/tasks' in (e.get('url') or '') and 'testcases' not in (e.get('url') or ''):
                    task_entry = e
                    break
            time.sleep(1)
        assert task_entry, '未捕获 POST /tasks；fetch=%s；dialog_open=%s' % (
            [e.get('method') + ' ' + (e.get('url') or '') for e in d.execute_script('return window.__fetchLog || []')][-8:],
            len(d.find_elements(By.CSS_SELECTOR, "[data-slot='dialog-content']")),
        )
        body = json.loads(task_entry['reqBody'])
        ids_entries = [e for e in d.execute_script('return window.__fetchLog || []')
                       if e.get('method') == 'POST' and '/testcases/ids' in (e.get('url') or '')]
        ids_body = json.loads(ids_entries[-1]['reqBody'])
        results.append('POST /testcases/ids 请求体：%s' % json.dumps(ids_body, ensure_ascii=False))
        results.append('POST /tasks 状态=%s case_ids=%d' % (task_entry.get('status'), len(body.get('case_ids') or [])))
        assert ids_body.get('group') == GROUP_NAME, 'ids 请求未按分组名圈定：%s' % ids_body
        assert len(body.get('case_ids') or []) == total, 'case_ids=%d 应为 %s' % (len(body.get('case_ids') or []), total)
        results.append('✅ 断言通过：分组筛选 + 清空选择后 filter-all 圈定 = %s 条' % total)
        try:
            resp = json.loads(task_entry.get('resBody') or '{}')
            created = (resp.get('data') or {}).get('id') or resp.get('id')
        except Exception:
            created = None
        results.append('新建任务 id=%s（接线测试前缀，收尾删除）' % created)
    finally:
        try:
            d.quit()
        except Exception:
            pass
        if created:
            print('CLEANUP stop:', api_call('POST', '/tasks/%s/stop' % created))
            print('CLEANUP soft-delete:', api_call('DELETE', '/tasks/%s' % created))
            print('CLEANUP purge:', api_call('DELETE', '/tasks/%s/purge' % created))
            results.append('清理：任务 %s 停止+软删+彻底删除' % created)

    print('\n=== RESULTS B ===')
    for r in results:
        print('-', r)


if __name__ == '__main__':
    main()
