# -*- coding: utf-8 -*-
"""INT-1489 探针：/dashboard 数据加载与网络请求全量核对。"""
import json, os, time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = 'http://localhost:15173'
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = 'tests/ui/artifacts/int1489'

FETCH_PATCH = r"""
window.__fetchLog = [];
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = (init && init.method) || (input && input.method) || 'GET';
  let entry = { url: url, method: method, t: Date.now() };
  try {
    const res = await __origFetch.apply(this, arguments);
    entry.status = res.status;
    entry.dt = Date.now() - entry.t;
    window.__fetchLog.push(entry);
    return res;
  } catch (e) {
    entry.status = 'ERR'; entry.error = String(e); entry.dt = Date.now() - entry.t;
    window.__fetchLog.push(entry); throw e;
  }
};
window.__perf = [];
"""


def driver():
    o = Options()
    o.binary_location = CHROME_BINARY
    for a in ('--headless=new', '--window-size=1600,1200', '--disable-gpu', '--no-sandbox',
              '--lang=zh-CN', '--disable-dev-shm-usage', '--no-first-run'):
        o.add_argument(a)
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    drv_path = ''
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe) and ver.split('.')[0] == str(major):
                drv_path = exe
    except Exception:
        pass
    drv = webdriver.Chrome(options=o, service=Service(executable_path=drv_path) if drv_path else Service())
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    return drv


def main():
    drv = driver()
    try:
        drv.get(BASE + '/dashboard')
        WebDriverWait(drv, 30).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(6)
        print('MID has spinner:', '刷新中' in (drv.execute_script('return document.body.textContent') or ''))
        time.sleep(14)
        body = drv.execute_script('return document.body.textContent') or ''
        print('TEXT_HEAD:', body[:120].replace('\n', ' '))
        print('has_loading_spinner:', '刷新中' in body)
        log = drv.execute_script('return window.__fetchLog || []')
        print('FETCH COUNT', len(log))
        for e in log:
            print(' ', e.get('method'), e.get('status'), e.get('dt'), e.get('url', '')[:120])
        perf = drv.execute_script(
            "return (window.performance.getEntriesByType('resource')||[]).map(e=>({n:e.name,s:e.responseStatus,d:Math.round(e.duration)}))")
        print('PERF entries', len(perf))
        for e in perf:
            if '/api/' in e['n']:
                print('  P', e['s'], e['d'], e['n'][:140])
        cards = {}
        for t in ('任务总数', '完成率', '最近任务'):
            try:
                el = drv.find_element(By.XPATH, f"//*[normalize-space(text())='{t}']")
                cards[t] = el.find_element(By.XPATH, './ancestor::div[1]').text.replace('\n', ' | ')[:160]
            except Exception as e:
                cards[t] = f'FAIL {str(e)[:60]}'
        print('CARDS', json.dumps(cards, ensure_ascii=False))
        drv.save_screenshot(f'{ART}/probe_dashboard.png')
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
