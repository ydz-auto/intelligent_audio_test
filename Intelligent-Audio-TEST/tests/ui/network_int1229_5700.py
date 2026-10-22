# -*- coding: utf-8 -*-
"""INT-1229 Network 证据采集（5700 真实栈）：抽屉留空 Master URL 保存后立即 drain performance log。"""
import json, os, time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5310')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = 'tests/ui/artifacts/int1229'
SUFFIX = int(time.time())

def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--no-first-run')
    options.add_argument('--no-default-browser-check')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-background-networking')
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
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
    return webdriver.Chrome(options=options, service=service)

def drain_perf(drv, tag):
    out = []
    try:
        for entry in drv.get_log('performance'):
            try:
                msg = json.loads(entry['message'])
                inner = msg.get('message', {})
                p = inner.get('params', {})
                if inner.get('method') == 'Network.requestWillBeSent':
                    req = p.get('request', {})
                    url = req.get('url', '')
                    if '/apis' in url and req.get('method') == 'POST':
                        out.append({'url': url, 'method': req.get('method'), 'postData': req.get('postData')})
            except Exception:
                pass
    except Exception as e:
        print('perf drain err', tag, repr(e)[:200])
    return out

def main():
    os.makedirs(ART, exist_ok=True)
    drv = _driver()
    try:
        drv.get(BASE + '/login')
        WebDriverWait(drv, 25).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(1.5)
        drv.find_element(By.ID, 'username').send_keys('接线测试_admin')
        drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
        drv.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]").click()
        WebDriverWait(drv, 25).until(lambda d: '/dashboard' in d.current_url)
        time.sleep(1)
        _ = drain_perf(drv, 'after-login')

        drv.get(BASE + '/devices/api')
        WebDriverWait(drv, 25).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(2)
        _ = drain_perf(drv, 'after-nav')

        btn = WebDriverWait(drv, 15).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(normalize-space(.), '添加测试API')]")))
        btn.click()
        WebDriverWait(drv, 10).until(
            EC.presence_of_element_located((By.XPATH, "//input[@placeholder='如：音箱-客厅位']")))
        name = f'接线测试_INT1229_net_{SUFFIX}'
        drv.find_element(By.XPATH, "//input[@placeholder='如：音箱-客厅位']").send_keys(name)
        drv.find_element(By.XPATH, "//button[contains(normalize-space(.), '添加端点')]").click()
        WebDriverWait(drv, 10).until(
            EC.presence_of_element_located((By.XPATH, "//input[@aria-label='端点 URL']")))
        drv.find_element(By.XPATH, "//input[@aria-label='端点 URL']").send_keys('https://example.com/v1/asr')
        time.sleep(0.6)
        drv.save_screenshot(f'{ART}/network_drawer_before_save.png')
        drv.find_element(By.XPATH, "//button[normalize-space(.)='保存']").click()
        time.sleep(4)
        posts = drain_perf(drv, 'after-save')
        print('NETWORK POST /apis:', json.dumps(posts, ensure_ascii=False, indent=1)[:2000])
        with open(f'{ART}/network_posts.json', 'w', encoding='utf-8') as f:
            json.dump(posts, f, ensure_ascii=False, indent=2)
        time.sleep(2)
        body = drv.execute_script('return document.body.textContent || ""')
        print('list contains new api:', name in body)
        drv.save_screenshot(f'{ART}/network_list_after_save.png')
    finally:
        try: drv.quit()
        except Exception: pass

if __name__ == '__main__':
    main()
