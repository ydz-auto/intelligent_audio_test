# -*- coding: utf-8 -*-
"""INT-1701 探针：报告域页面（/reports、/report-center、/report/:id）是否发数据请求。

只读：不提交任何写操作。用于判定「页面骨架存在但计数恒 0 / 详情恒骨架」是
前端请求未发出，还是后端 4xx/5xx。
"""
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = 'http://localhost:15173'
ART = os.path.join('tests', 'ui', 'artifacts', 'int1701')
FETCH_PATCH = r"""
window.__fetchLog = [];
window.__errLog = [];
window.addEventListener('error', function(e){ window.__errLog.push('error: ' + (e.message||'')); });
window.addEventListener('unhandledrejection', function(e){ window.__errLog.push('rejection: ' + String(e.reason)); });
const of = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = ((init && init.method) || 'GET').toUpperCase();
  const entry = { url, method, t: Date.now() };
  try {
    const res = await of.apply(this, arguments);
    entry.status = res.status;
    window.__fetchLog.push(entry);
    return res;
  } catch (e) {
    entry.error = String(e);
    window.__fetchLog.push(entry);
    throw e;
  }
};
const ox = XMLHttpRequest.prototype.open;
const osend = XMLHttpRequest.prototype.send;
XMLHttpRequest.prototype.open = function(m, u) { this.__m = m; this.__u = u; return ox.apply(this, arguments); };
XMLHttpRequest.prototype.send = function() {
  const x = this;
  x.addEventListener('loadend', function() {
    window.__fetchLog.push({ url: x.__u, method: x.__m, status: x.status, xhr: true });
  });
  return osend.apply(this, arguments);
};
"""


def make_driver():
    opts = Options()
    opts.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    opts.add_argument('--headless=new')
    opts.add_argument('--window-size=1680,1050')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--lang=zh-CN')
    opts.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    drv = webdriver.Chrome(options=opts, service=Service())
    drv.set_page_load_timeout(90)
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    return drv


def login(drv):
    drv.get(BASE + '/login')
    WebDriverWait(drv, 40).until(lambda d: d.find_elements(By.ID, 'username'))
    drv.find_element(By.ID, 'username').send_keys('接线测试_admin')
    drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    drv.execute_script('arguments[0].click()',
                       drv.find_element(By.CSS_SELECTOR, "button[type='submit']"))
    WebDriverWait(drv, 40).until(lambda d: '/login' not in d.current_url)
    time.sleep(1)


def probe(drv, route, seconds=30):
    drv.get(BASE + route)
    time.sleep(seconds)
    fetch = drv.execute_script('return window.__fetchLog || []') or []
    errs = drv.execute_script('return window.__errLog || []') or []
    out = {
        'route': route,
        'url': drv.current_url,
        'fetch': [f for f in fetch if '/api/' in (f.get('url') or '')],
        'js_errors': errs[:10],
        'console': [e.get('message', '')[:300] for e in drv.get_log('browser')
                    if e.get('level') == 'SEVERE'][:10],
        'text': (drv.execute_script('return document.body.innerText') or '')[:700],
    }
    # 全量网络（非仅 api）
    perf = []
    for e in drv.get_log('performance'):
        try:
            m = json.loads(e['message'])['message']
            if m.get('method') == 'Network.responseReceived':
                r = m['params']['response']
                if r.get('status', 0) >= 400:
                    perf.append({'url': r.get('url'), 'status': r.get('status')})
        except Exception:
            pass
    out['http_errors'] = perf
    return out


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    os.makedirs(ART, exist_ok=True)
    drv = make_driver()
    results = []
    try:
        login(drv)
        for route in ('/reports', '/report-center', '/report/567'):
            r = probe(drv, route)
            results.append(r)
            print('=' * 20, route)
            print('url:', r['url'])
            print('fetch:', [(f.get('method'), f.get('url'), f.get('status')) for f in r['fetch']])
            print('js_errors:', r['js_errors'])
            print('console:', r['console'])
            print('http_errors:', r['http_errors'])
            print('text:', r['text'][:300].replace('\n', ' | '))
            drv.save_screenshot(os.path.join(ART, 'probe_%s.png' % route.strip('/').replace('/', '_')))
    finally:
        drv.quit()
    with open(os.path.join(ART, 'probe_reports.json'), 'w', encoding='utf-8') as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2)
