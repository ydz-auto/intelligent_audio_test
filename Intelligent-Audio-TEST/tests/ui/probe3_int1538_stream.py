# -*- coding: utf-8 -*-
"""探针 3：抓浏览器播放流的真实请求/响应（哪个 endpoint 生成 rustfs:9000 URL）。"""
import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1538_lib as L
from selenium.webdriver.common.by import By

GROUP = os.environ.get('CASE_GROUP', '接线测试_INT1538_播放器复测组')
OUT = {}


def vis(el):
    try:
        return el.is_displayed()
    except Exception:
        return False


def retry(fn, timeout=60, interval=1.0):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        try:
            r = fn()
            if r is not None:
                return r
        except Exception as e:
            last = e
        time.sleep(interval)
    if last:
        raise last
    return None


d = None
try:
    import winreg
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    o = Options()
    o.binary_location = L.CHROME_BINARY
    for a in ('--headless=new', '--window-size=1600,1000', '--disable-gpu', '--no-sandbox',
              '--lang=zh-CN', '--disable-dev-shm-usage', '--autoplay-policy=no-user-gesture-required'):
        o.add_argument(a)
    o.add_experimental_option('excludeSwitches', ['enable-logging'])
    o.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    path = ''
    if major and os.path.isdir(cache):
        for ver in os.listdir(cache):
            exe = os.path.join(cache, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    if int(ver.split('.')[0]) == major:
                        path = exe
                except ValueError:
                    pass
    d = webdriver.Chrome(options=o, service=Service(executable_path=path) if path else Service())
    d.set_page_load_timeout(60)
    d.set_script_timeout(60)
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': L.FETCH_PATCH})
    d.get(L.BASE + '/testcases')
    time.sleep(8)
    if '/login' in d.current_url:
        for b in d.find_elements(By.TAG_NAME, 'button'):
            if '进入' in (b.text or '') or '登录' in (b.text or ''):
                L.js_click(d, b)
                time.sleep(4)
                break
        d.get(L.BASE + '/testcases')
        time.sleep(8)
    # 拉全分组并展开目标组
    for _ in range(8):
        if GROUP in L.body_text(d):
            break
        more = next((b for b in d.find_elements(By.TAG_NAME, 'button') if vis(b) and '加载更多' in (b.text or '')), None)
        if not more:
            break
        L.js_click(d, more)
        time.sleep(4)
    h = retry(lambda: d.execute_script("""
        const g = arguments[0];
        for (const el of document.querySelectorAll('div')) {
          const cls = (el.className || '').toString();
          if (cls.includes('cursor-pointer') && cls.includes('justify-between') &&
              (el.innerText || '').trim().startsWith(g)) { return el; }
        }
        return null;
    """, GROUP))
    d.execute_script('arguments[0].click();', h)
    retry(lambda: next((b for b in d.find_elements(By.CSS_SELECTOR, "button[aria-label='预览音频']") if vis(b)), None), 90)

    L.clear_fetch_log(d)
    try:
        d.get_log('browser')
        d.get_log('performance')
    except Exception:
        pass
    btn = next((b for b in d.find_elements(By.CSS_SELECTOR, "button[aria-label='预览音频']") if vis(b)), None)
    L.js_click(d, btn)
    w = L.wait_dialog(d, '音频试听配置', 30)
    time.sleep(1)
    lab = next((x for x in d.find_elements(By.XPATH, "//label[contains(normalize-space(.), '浏览器播放')]") if vis(x)), None)
    L.js_click(d, lab)
    time.sleep(1)
    start = next((x for x in d.find_elements(By.TAG_NAME, 'button') if vis(x) and (x.text or '').strip() == '开始试听'), None)
    L.js_click(d, start)
    time.sleep(6)
    OUT['fetch_log'] = [e for e in L.fetch_log(d) if '/audios/' in (e.get('url') or '') or 'stream' in (e.get('url') or '')]
    OUT['all_fetch'] = [(e.get('method'), (e.get('url') or '')[:120], e.get('status')) for e in L.fetch_log(d)][:20]
    OUT['console'] = [x.get('message', '')[:400] for x in d.get_log('browser')]
    OUT['perf'] = []
    for x in d.get_log('performance'):
        try:
            m = json.loads(x['message'])['message']
        except Exception:
            continue
        if m.get('method') == 'Network.responseReceived':
            u = m['params']['response']['url']
            if '/audios/' in u or ':9000/' in u:
                OUT['perf'].append({'url': u[:200], 'status': m['params']['response']['status']})
    OUT['time'] = (next((e.text for e in d.find_elements(By.CSS_SELECTOR, "[data-testid='player-time']") if vis(e)), ''))
    L.shot(d, 'probe3_player_browser')
finally:
    L.save_evidence('probe3_stream', OUT)
    try:
        d.quit()
    except Exception:
        pass
