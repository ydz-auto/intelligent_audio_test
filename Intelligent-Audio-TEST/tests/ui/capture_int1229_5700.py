# -*- coding: utf-8 -*-
"""INT-1229 真实库栈 5700 浏览器实测（auth dev + 登录）：两处表单留空 Master URL 保存成功。

连 dev server 5310 → 网关 5700（主库 intelligent_audio_test，当前代码）。
登录：接线测试_admin / JieXianTest@2026。Network 证据用 CDP 预注入 window.fetch 打点。
"""
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

FETCH_PATCH = r"""
window.__fetchLog = [];
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  try {
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    if (url.indexOf('/apis') !== -1 && init && init.method === 'POST') {
      window.__fetchLog.push({ url: url, method: init.method, body: init.body });
    }
  } catch (e) {}
  return __origFetch.apply(this, arguments);
};
"""

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
    try:
        drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    except Exception:
        pass
    return drv

def read_fetch_log(drv):
    try:
        return drv.execute_script('return window.__fetchLog || []')
    except Exception:
        return None

def wait_toast(drv, text, timeout=25):
    try:
        WebDriverWait(drv, timeout).until(
            lambda d: any(text in (e.text or '') for e in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')))
        toasts = [e.text for e in drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
        print('TOAST:', json.dumps(toasts, ensure_ascii=False)[:300])
        return True
    except Exception:
        return False

def login(drv):
    drv.get(BASE + '/login')
    WebDriverWait(drv, 25).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)
    uname = WebDriverWait(drv, 10).until(EC.presence_of_element_located((By.ID, 'username')))
    uname.send_keys('接线测试_admin')
    drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    drv.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]").click()
    WebDriverWait(drv, 25).until(
        lambda d: '/login' not in d.current_url or '欢迎' in (d.execute_script('return document.body.textContent || ""') or ''))
    time.sleep(2)
    print('login URL:', drv.current_url)
    return drv.current_url

def fill_drawer_api(drv, name):
    name_in = WebDriverWait(drv, 10).until(
        EC.presence_of_element_located((By.XPATH, "//input[@placeholder='如：音箱-客厅位']")))
    name_in.clear()
    name_in.send_keys(name)
    master = drv.find_elements(By.XPATH, "//input[@placeholder='https://api.example.com/v1/asr']")
    found_master = len(master) > 0
    add = WebDriverWait(drv, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//button[contains(normalize-space(.), '添加端点')]")))
    add.click()
    ep = WebDriverWait(drv, 10).until(
        EC.presence_of_element_located((By.XPATH, "//input[@aria-label='端点 URL']")))
    ep.send_keys('https://example.com/v1/asr')
    return found_master, ep.get_attribute('value')

def open_device_drawer(drv):
    btn = WebDriverWait(drv, 15).until(
        EC.element_to_be_clickable((By.XPATH, "//button[contains(normalize-space(.), '添加测试API')]")))
    btn.click()
    WebDriverWait(drv, 10).until(
        EC.presence_of_element_located((By.XPATH, "//input[@placeholder='如：音箱-客厅位']")))

def wait_algorithm_filled(drv, timeout=30):
    try:
        WebDriverWait(drv, timeout).until(
            lambda d: not d.find_elements(
                By.CSS_SELECTOR, '[role="dialog"] [data-slot="select-trigger"][data-placeholder]'))
        time.sleep(0.5)
        return True
    except Exception:
        return False

def set_global_algorithm(drv):
    drv.execute_script(
        "localStorage.setItem('iatp:algorithm:v1', JSON.stringify({state:{algorithmId:'voice_llm'},version:0}));")

def show_post_evidence(drv, label):
    log = read_fetch_log(drv)
    if not log:
        print(label, 'fetch log empty')
        return
    for item in log:
        body = item.get('body')
        parsed = None
        if body:
            try:
                parsed = json.loads(body)
            except Exception:
                pass
        print(label, 'POST', item.get('url'),
              '| api_url:', repr(parsed.get('api_url')) if isinstance(parsed, dict) else '?',
              '| name:', (parsed or {}).get('name'),
              '| endpoints:', len((parsed or {}).get('endpoints') or []))

def main():
    os.makedirs(ART, exist_ok=True)
    drv = _driver()
    created = []
    try:
        login(drv)
        # 全局算法预设
        drv.execute_script(
            "localStorage.setItem('iatp:algorithm:v1', JSON.stringify({state:{algorithmId:'voice_llm'},version:0}));")

        # ========== 设备管理 → API 页签（浅色） ==========
        drv.get(BASE + '/devices/api')
        WebDriverWait(drv, 25).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(2)
        print('URL1:', drv.current_url)
        open_device_drawer(drv)
        name1 = f'接线测试_INT1229_空MasterURL_{SUFFIX}'
        found_master, ep_val = fill_drawer_api(drv, name1)
        print('drawer Master URL 输入存在:', found_master, '| 端点已填:', repr(ep_val))
        time.sleep(0.8)
        drv.save_screenshot(f'{ART}/device_drawer_light.png')
        drv.find_element(By.XPATH, "//button[normalize-space(.)='保存']").click()
        ok1 = wait_toast(drv, '测试 API 已保存')
        print('drawer 保存 toast:', ok1)
        time.sleep(2)
        show_post_evidence(drv, '[drawer]')

        # ========== 开始测试 step1「新增 API」弹窗（浅色） ==========
        drv.get(BASE + '/start-test?step=1')
        WebDriverWait(drv, 25).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(3)
        print('URL2:', drv.current_url)
        WebDriverWait(drv, 15).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(normalize-space(.), '新增 API')]"))).click()
        dlg_name = WebDriverWait(drv, 10).until(EC.presence_of_element_located((By.ID, 'api-name')))
        dlg_name.clear()
        name2 = f'接线测试_INT1229_dialog_{SUFFIX}'
        dlg_name.send_keys(name2)
        dlg_url = drv.find_elements(By.ID, 'api-url')
        print('dialog Master URL 输入存在:', len(dlg_url) > 0)
        label_txt = [e.text for e in drv.find_elements(By.CSS_SELECTOR, 'label[for="api-url"]')]
        print('dialog api-url label:', json.dumps(label_txt, ensure_ascii=False))
        alg_ok = wait_algorithm_filled(drv)
        print('dialog 算法自动填值:', alg_ok)
        time.sleep(0.8)
        drv.save_screenshot(f'{ART}/starttest_dialog_light.png')
        drv.find_element(By.XPATH, "//button[normalize-space(.)='保存']").click()
        ok2 = wait_toast(drv, 'API 已保存')
        print('dialog 保存 toast:', ok2)
        time.sleep(2)
        show_post_evidence(drv, '[dialog]')

        # ========== 深色 ==========
        drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', 'dark');")
        drv.get('about:blank')
        time.sleep(0.5)
        drv.get(BASE + '/devices/api')
        WebDriverWait(drv, 25).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(2)
        open_device_drawer(drv)
        name3 = f'接线测试_INT1229_深色_{SUFFIX}'
        fill_drawer_api(drv, name3)
        time.sleep(0.8)
        drv.save_screenshot(f'{ART}/device_drawer_dark.png')
        drv.find_element(By.XPATH, "//button[normalize-space(.)='保存']").click()
        wait_toast(drv, '测试 API 已保存')
        time.sleep(1)

        drv.get(BASE + '/start-test?step=1')
        WebDriverWait(drv, 25).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(3)
        WebDriverWait(drv, 15).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(normalize-space(.), '新增 API')]"))).click()
        WebDriverWait(drv, 10).until(EC.presence_of_element_located((By.ID, 'api-name')))
        wait_algorithm_filled(drv)
        time.sleep(0.6)
        drv.save_screenshot(f'{ART}/starttest_dialog_dark.png')

        created = [
            {'name': name1, 'form': 'drawer'},
            {'name': name2, 'form': 'dialog'},
            {'name': name3, 'form': 'drawer-dark'},
        ]
        with open(f'{ART}/created.json', 'w', encoding='utf-8') as f:
            json.dump({'suffix': SUFFIX, 'created': created}, f, ensure_ascii=False, indent=2)
        print('CREATED:', json.dumps(created, ensure_ascii=False))
    finally:
        try: drv.quit()
        except Exception: pass

if __name__ == '__main__':
    main()
