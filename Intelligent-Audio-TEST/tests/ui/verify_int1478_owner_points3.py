# -*- coding: utf-8 -*-
"""INT-1478 补充复核（三）：/tasks/526 真实网络请求/响应 + 页面内聚合核对。"""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = 'http://127.0.0.1:15173'
ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1478_owner_points')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
DRIVER = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver',
                      'win64', '155.0.8059.84', 'chromedriver.exe')
out = {}


def main():
    o = Options()
    o.binary_location = CHROME
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1050')
    o.add_argument('--no-sandbox')
    o.add_argument('--disable-gpu')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--user-data-dir=' + os.path.join(
        os.environ.get('TEMP', r'C:\Windows\Temp'), 'int1478_owner_points_profile'))
    o.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
    d = webdriver.Chrome(service=Service(DRIVER), options=o)
    d.set_page_load_timeout(120)
    d.set_script_timeout(120)
    try:
        d.get(BASE + '/tasks/daily')
        time.sleep(4)
        if '/login' in d.current_url:
            d.find_element(By.ID, 'username').send_keys('接线测试_admin')
            d.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
            d.find_element(By.XPATH, "//button[contains(., '登')]").click()
            WebDriverWait(d, 30).until(lambda x: '/login' not in x.current_url)
            time.sleep(2)

        # 清空旧日志基线
        d.get_log('performance')
        mark = len(d.get_log('performance'))
        d.get(BASE + '/tasks/526')
        WebDriverWait(d, 150).until(
            lambda x: x.execute_script('return !!document.querySelector(\'div[class*="xl:grid-cols-3"]\')'))
        time.sleep(10)

        sent, recv = [], []
        for m in d.get_log('performance')[mark:]:
            try:
                msg = json.loads(m['message'])['message']
            except Exception:
                continue
            if msg.get('method') == 'Network.requestWillBeSent':
                u = msg['params']['request']['url']
                if '526' in u or '/api/' in u:
                    sent.append(msg['params']['request']['method'] + ' ' + u.replace(BASE, ''))
            if msg.get('method') == 'Network.responseReceived':
                r = msg['params']['response']
                if '526' in r['url'] or '/api/' in r['url']:
                    recv.append({'status': r['status'], 'url': r['url'].replace(BASE, ''),
                                 'mime': r.get('mimeType'),
                                 'fromCache': r.get('fromDiskCache') or r.get('fromMemoryCache')})
        out['requests'] = list(dict.fromkeys(sent))
        out['responses'] = recv
        print('requests:', json.dumps(out['requests'], ensure_ascii=False, indent=1))
        print('responses:', json.dumps(recv, ensure_ascii=False, indent=1))

        # 页面内 fetch：聚合详情数据（不在 Python 侧解析大 body）
        fetch = r"""
        const ar = arguments[arguments.length-1];
        fetch('/api/v1/tasks/526', {headers: {'Accept':'application/json'}})
          .then(r => r.json().then(j => {
            const data = j.data || j;
            const cases = data.cases || [];
            const ev = {}, ex = {}, st = {};
            for (const c of cases) {
              ev[c.evaluation_status] = (ev[c.evaluation_status]||0)+1;
              ex[c.execution_status] = (ex[c.execution_status]||0)+1;
              st[c.status] = (st[c.status]||0)+1;
            }
            ar({status: r.status, total_cases: data.total_cases, case_count: data.case_count,
                cases: cases.length, failed_cases: data.failed_cases,
                completed_cases: data.completed_cases, task_status: data.status,
                evaluation_status_counts: ev, execution_status_counts: ex, status_counts: st});
          }))
          .catch(e => ar({error: String(e)}));
        """
        out['fetch'] = d.execute_async_script(fetch)
        print('fetch:', json.dumps(out['fetch'], ensure_ascii=False))
    except Exception as exc:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        out['error'] = '%s: %s' % (type(exc).__name__, exc)
    finally:
        with open(os.path.join(ART, 'report3.json'), 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        d.quit()
        print('report3 written')


if __name__ == '__main__':
    main()
