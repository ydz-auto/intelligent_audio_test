# -*- coding: utf-8 -*-
"""INT-1437 聚焦复检：编辑回显摘要 + 留空保存不清池（mock 5701 仅 seed 2 条）。"""
import json, os, time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5310')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = 'tests/ui/artifacts/int1437'
SUFFIX = int(time.time())

FETCH_PATCH = r"""
window.__fetchLog = [];
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const res = await __origFetch.apply(this, arguments);
  try {
    const entry = { url: url, method: init && init.method, status: res.status };
    if (init && (init.method === 'POST' || init.method === 'PUT')) entry.reqBody = init.body;
    if (url.indexOf('/apis') !== -1) {
      const ct = res.headers.get('content-type') || '';
      if (ct.indexOf('json') !== -1) entry.resBody = await res.clone().text();
    }
    window.__fetchLog.push(entry);
  } catch (e) {}
  return res;
};
"""

KEY_TEXTAREA_XPATH = "//textarea[contains(@placeholder, '每行一个密钥')]"
# 摘要所在 <p>（JSX 拆分文本节点 → normalize-space(.)）
SUMMARY_XPATH = "//p[contains(normalize-space(.), '已配置') and contains(normalize-space(.), '个密钥')]"


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
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        chrome_major = 0
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    drv_path = ''
    if chrome_major and os.path.isdir(cache_root):
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    drv_path = exe if tuple(int(x) for x in ver.split('.') if x.isdigit())[0] == chrome_major else drv_path
                except ValueError:
                    continue
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
        return True
    except Exception:
        return False


def login(drv):
    drv.get(BASE + '/login')
    WebDriverWait(drv, 25).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)
    try:
        uname = WebDriverWait(drv, 10).until(EC.presence_of_element_located((By.ID, 'username')))
    except Exception:
        if '/login' not in drv.current_url:
            return drv.current_url
        raise
    uname.send_keys('接线测试_admin')
    drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    drv.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]").click()
    WebDriverWait(drv, 25).until(lambda d: '/login' not in d.current_url)
    time.sleep(2)


def wait_algorithm_filled(drv, timeout=30):
    try:
        WebDriverWait(drv, timeout).until(
            lambda d: not d.find_elements(
                By.CSS_SELECTOR, '[role="dialog"] [data-slot="select-trigger"][data-placeholder]'))
        time.sleep(0.5)
    except Exception:
        pass


def set_global_algorithm(drv):
    drv.execute_script(
        "localStorage.setItem('iatp:algorithm:v1', JSON.stringify({state:{algorithmId:'voice_llm'},version:0}));")


def dump_summary(drv, label):
    summaries = [e.text for e in drv.find_elements(By.XPATH, SUMMARY_XPATH)]
    textareas = drv.find_elements(By.XPATH, KEY_TEXTAREA_XPATH)
    ta_values = [t.get_attribute('value') for t in textareas]
    container = drv.find_elements(By.XPATH, "//*[@role='dialog'] | //*[@role='dialog']/..")
    leak = False
    if container:
        leak = ('sk-full-secret-1' in container[0].text) or ('sk-full-secret-2' in container[0].text)
    print('%s 摘要:' % label, json.dumps(summaries, ensure_ascii=False))
    print('%s textarea 值(应空):' % label, json.dumps(ta_values, ensure_ascii=False))
    print('%s 完整密钥泄漏:' % label, leak)
    return summaries


def main():
    os.makedirs(ART, exist_ok=True)
    drv = _driver()
    try:
        login(drv)
        set_global_algorithm(drv)

        # ===== 开始测试弹窗编辑回显 =====
        drv.get(BASE + '/start-test?step=1')
        WebDriverWait(drv, 25).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(3)
        try:
            btn = WebDriverWait(drv, 15).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//*[contains(normalize-space(.), '演示密钥池API')]//button[@aria-label='更多操作'][1]")))
            btn.click()
            time.sleep(0.8)
            WebDriverWait(drv, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//*[@role='menuitem'][contains(normalize-space(.), '编辑')]"))).click()
            time.sleep(1.2)
            dump_summary(drv, '[starttest-echo]')
            time.sleep(0.5)
            drv.save_screenshot(f'{ART}/starttest_edit_echo_light.png')
            try:
                drv.find_element(By.XPATH, "//button[normalize-space(.)='取消']").click()
                time.sleep(0.5)
            except Exception:
                pass
        except Exception as e:
            print('[starttest-echo] FAIL:', str(e)[:150])

        # ===== 设备抽屉编辑回显 + 留空保存不清池 =====
        drv.get(BASE + '/devices/api')
        WebDriverWait(drv, 25).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(2)
        try:
            WebDriverWait(drv, 15).until(
                EC.element_to_be_clickable((By.XPATH, "//button[@aria-label='操作 演示密钥池API']"))).click()
            time.sleep(0.8)
            WebDriverWait(drv, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//*[@role='menuitem'][contains(normalize-space(.), '编辑')]"))).click()
            time.sleep(1.2)
            dump_summary(drv, '[drawer-echo]')
            time.sleep(0.5)
            drv.save_screenshot(f'{ART}/device_drawer_edit_echo_light.png')

            # 留空保存：改名称，密钥区不动（空）→ 保存
            new_name = '演示密钥池API_改名'
            name_in = WebDriverWait(drv, 5).until(
                EC.presence_of_element_located((By.XPATH, "//input[@placeholder='如：音箱-客厅位']")))
            name_in.clear()
            name_in.send_keys(new_name)
            time.sleep(0.5)
            drv.find_element(By.XPATH, "//button[normalize-space(.)='保存']").click()
            ok = wait_toast(drv, '测试 API 已保存')
            print('[keep-pool] 改名保存 toast:', ok)
            time.sleep(2)
            for item in read_fetch_log(drv) or []:
                if item.get('method') == 'PUT':
                    print('[keep-pool] PUT body:', (item.get('reqBody') or '')[:300])
            # 重开验证池仍保留
            drv.get(BASE + '/devices/api')
            WebDriverWait(drv, 25).until(lambda d: d.execute_script('return document.readyState') == 'complete')
            time.sleep(2)
            WebDriverWait(drv, 15).until(
                EC.element_to_be_clickable((By.XPATH, f"//button[@aria-label='操作 {new_name}']"))).click()
            time.sleep(0.8)
            WebDriverWait(drv, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//*[@role='menuitem'][contains(normalize-space(.), '编辑')]"))).click()
            time.sleep(1.2)
            dump_summary(drv, '[keep-pool-echo]')
        except Exception as e:
            print('[drawer-echo] FAIL:', str(e)[:200])

        # ===== 深色抽屉截图 =====
        drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', 'dark');")
        drv.get('about:blank')
        time.sleep(0.5)
        drv.get(BASE + '/devices/api')
        WebDriverWait(drv, 25).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(2)
        try:
            WebDriverWait(drv, 15).until(
                EC.element_to_be_clickable((By.XPATH, f"//button[@aria-label='操作 {new_name}']"))).click()
            time.sleep(0.8)
            WebDriverWait(drv, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//*[@role='menuitem'][contains(normalize-space(.), '编辑')]"))).click()
            time.sleep(1.2)
            drv.save_screenshot(f'{ART}/device_drawer_edit_echo_dark.png')
        except Exception as e:
            print('[dark echo] FAIL:', str(e)[:150])
        print('DONE')
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
