# -*- coding: utf-8 -*-
"""INT-1433 验收：REACT 建任务接入 case_devices 混选（websocket_api Realtime 路由前置）。

连 dev server 5333 → 真实库栈 5700（主库 intelligent_audio_test）。
登录：接线测试_admin / JieXianTest@2026（AUTH_MODE=dev 表单登录）。
流程：
1. 登录 + 全局算法 voice_llm
2. /start-test?step=1 → 新增 API：设备类型选「Realtime WS」+ wss:// 端点 → 保存
   （验证新 deviceType 表单字段；浅色截图）
3. 勾选该 API → 开始测试 → 任务名称弹窗 → 开始测试
   （fetch 打点捕获 POST /tasks 请求体，验证 case_devices 含 {device_type:websocket_api}）
4. 深色主题重开编辑弹窗截图 + deviceType 回显核对
写数据纪律：API 名/任务名带「接线测试_INT1433_」前缀，run 结束前删除。
"""
import json
import os
import time
import winreg

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5333')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1433_case_devices')
SUFFIX = int(time.time())
API_NAME = '接线测试_INT1433_WS_%d' % SUFFIX
TASK_NAME = '接线测试_INT1433_%d' % SUFFIX

FETCH_PATCH = r"""
window.__fetchLog = [];
window.__iatpErrors = [];
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  try {
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    const method = (init && init.method) || 'GET';
    if (url.indexOf('/tasks') !== -1 && method === 'POST') {
      window.__fetchLog.push({ url: url, method: method, body: init.body });
    }
  } catch (e) {}
  return __origFetch.apply(this, arguments);
};
const __origConsoleError = console.error;
console.error = function() {
  const parts = [];
  for (let i = 0; i < arguments.length; i++) {
    const a = arguments[i];
    let s;
    try { s = typeof a === 'string' ? a : JSON.stringify(a); } catch (e) { s = String(a); }
    parts.push(String(s).slice(0, 300));
  }
  window.__iatpErrors.push(parts.join(' ||| '));
  return __origConsoleError.apply(console, arguments);
};
"""


def _driver():
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
    drv.set_page_load_timeout(60)
    try:
        drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    except Exception:
        pass
    return drv


def _shot(drv, name, theme):
    d = os.path.join(ART, theme)
    os.makedirs(d, exist_ok=True)
    drv.save_screenshot(os.path.join(d, name + '.png'))
    print('saved', theme, name)


def _body(drv):
    return drv.execute_script('return document.body.textContent || ""')


def login(drv):
    drv.get(BASE + '/login')
    WebDriverWait(drv, 25).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)
    uname = WebDriverWait(drv, 10).until(EC.presence_of_element_located((By.ID, 'username')))
    uname.send_keys('接线测试_admin')
    drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    drv.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]").click()
    try:
        WebDriverWait(drv, 25).until(lambda d: '/login' not in d.current_url)
    except Exception:
        pass
    time.sleep(2)
    print('login URL:', drv.current_url)
    return drv.current_url


def js_click(drv, el):
    drv.execute_script('arguments[0].click()', el)


def set_select_by_label(drv, label_text, option_text):
    lab = drv.find_element(By.XPATH,
        "//div[@role='dialog']//label[normalize-space(.)='%s']" % label_text)
    trig = lab.find_element(By.XPATH, '..').find_element(By.CSS_SELECTOR, "[data-slot='select-trigger']")
    js_click(drv, trig)
    time.sleep(0.8)
    opt = WebDriverWait(drv, 8).until(
        EC.presence_of_element_located((By.XPATH,
            "//div[@data-slot='select-item']//*[normalize-space(.)='%s']" % option_text)))
    js_click(drv, opt)
    time.sleep(0.6)


def open_api_edit_new(drv):
    btn = WebDriverWait(drv, 15).until(
        EC.element_to_be_clickable((By.XPATH, "//button[contains(normalize-space(.), '新增 API')]")))
    js_click(drv, btn)
    WebDriverWait(drv, 10).until(EC.presence_of_element_located((By.ID, 'api-name')))


def open_api_edit_existing(drv, name):
    span = WebDriverWait(drv, 15).until(
        EC.presence_of_element_located((By.XPATH, "//span[normalize-space(.)='%s']" % name)))
    card = span.find_element(By.XPATH, "./ancestor::div[contains(@class,'rounded-xl')][1]")
    more = card.find_element(By.XPATH, ".//button[@aria-label='更多操作']")
    js_click(drv, more)
    time.sleep(0.6)
    edit = WebDriverWait(drv, 8).until(
        EC.element_to_be_clickable((By.XPATH, "//*[@data-slot='dropdown-menu-item' and normalize-space(.)='编辑']")))
    js_click(drv, edit)
    WebDriverWait(drv, 10).until(EC.presence_of_element_located((By.ID, 'api-name')))


def select_api_card(drv, name):
    chk = WebDriverWait(drv, 15).until(
        EC.presence_of_element_located((By.XPATH, "//button[@aria-label='选择 API %s']" % name)))
    js_click(drv, chk)
    time.sleep(0.6)


def start_test_flow(drv):
    start_btn = WebDriverWait(drv, 15).until(
        EC.element_to_be_clickable((By.XPATH, "//button[contains(normalize-space(.), '开始测试')]")))
    js_click(drv, start_btn)
    try:
        go = WebDriverWait(drv, 12).until(
            EC.presence_of_element_located((By.XPATH, "//div[@role='dialog']//button[contains(normalize-space(.), '开始测试')]")))
    except Exception:
        toasts = [e.text for e in drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
        print('start-test dialog not opened; toasts:', json.dumps(toasts, ensure_ascii=False)[:300])
        return False
    time.sleep(1)
    js_click(drv, go)
    time.sleep(4)
    return True


def read_fetch_log(drv):
    try:
        return drv.execute_script('return window.__fetchLog || []')
    except Exception:
        return None


def set_theme(drv, mode):
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', '%s');" % mode)


def get_dialog_device_type_value(drv):
    return drv.execute_script(
        "const ls = Array.from(document.querySelectorAll('div[role=dialog] label'));"
        "const l = ls.find(x => x.textContent.trim() === '设备类型');"
        "if (!l) return 'NO_LABEL';"
        "const f = l.parentElement;"
        "const tv = f.querySelector('[data-slot=select-value]');"
        "return tv ? tv.textContent.trim() : 'NO_VALUE';")


def main():
    os.makedirs(ART, exist_ok=True)
    drv = _driver()
    try:
        login(drv)
        drv.execute_script(
            "localStorage.setItem('iatp:algorithm:v1', JSON.stringify({state:{algorithmId:'voice_llm'},version:0}));")

        # ===== 浅色：新增 API（Realtime WS） =====
        drv.get(BASE + '/start-test?step=1')
        WebDriverWait(drv, 25).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(4)
        print('step1 url:', drv.current_url)
        print('body has 被测 API:', '被测 API' in _body(drv))

        open_api_edit_new(drv)
        time.sleep(1.5)
        _shot(drv, '01_api_edit_light', 'light')
        # 打开设备类型下拉（关键交互单独截）
        lab = drv.find_element(By.XPATH, "//div[@role='dialog']//label[normalize-space(.)='设备类型']")
        trig = lab.find_element(By.XPATH, '..').find_element(By.CSS_SELECTOR, "[data-slot='select-trigger']")
        js_click(drv, trig)
        time.sleep(0.8)
        _shot(drv, '02_device_type_dropdown_light', 'light')
        # 选择 Realtime WS
        opt = WebDriverWait(drv, 8).until(
            EC.presence_of_element_located((By.XPATH,
                "//div[@data-slot='select-item']//*[normalize-space(.)='Realtime WS']")))
        js_click(drv, opt)
        time.sleep(0.5)

        # 填名称 + 端点 + 保存
        name_in = drv.find_element(By.ID, 'api-name')
        name_in.clear()
        name_in.send_keys(API_NAME)
        add = WebDriverWait(drv, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(normalize-space(.), '添加端点')]")))
        js_click(drv, add)
        ep = WebDriverWait(drv, 10).until(
            EC.presence_of_element_located((By.XPATH, "//input[@aria-label='端点 URL']")))
        ep.send_keys('wss://realtime.example.com/ws')
        save_btn = WebDriverWait(drv, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//div[@role='dialog']//button[contains(normalize-space(.), '保存')]")))
        js_click(drv, save_btn)
        time.sleep(2.5)

        try:
            WebDriverWait(drv, 15).until(
                lambda d: any('API 已保存' in (e.text or '') for e in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')))
            print('API save toast OK')
        except Exception:
            print('WARN no save toast; body snippet:', _body(drv)[:200])
        time.sleep(4)
        body = _body(drv)
        print('API card name present:', API_NAME in body)
        print('API card Realtime WS badge:', 'Realtime WS' in body)
        print('API card 在线:', '在线' in body)

        select_api_card(drv, API_NAME)
        started = start_test_flow(drv)
        print('launch dialog started:', started)

        # ===== fetch log =====
        log = read_fetch_log(drv)
        parsed_bodies = []
        if log:
            print('=== POST /tasks captured:', len(log))
            for item in log:
                b = item.get('body')
                try:
                    parsed_bodies.append(json.loads(b))
                except Exception:
                    parsed_bodies.append(None)
                print('POST', item.get('url'))
        else:
            print('=== POST /tasks captured: 0')
        for i, pb in enumerate(parsed_bodies):
            if isinstance(pb, dict):
                print('-- task body[%d] name: %r' % (i, pb.get('name')))
                cd = pb.get('case_devices')
                print('-- case_devices count:', len(cd) if isinstance(cd, list) else cd)
                if isinstance(cd, list):
                    types = {}
                    for item in cd:
                        dt = item.get('device_type')
                        types[dt] = types.get(dt, 0) + 1
                    print('-- case_devices device_type counts:', json.dumps(types, ensure_ascii=False))
                    if cd:
                        print('-- first entry:', json.dumps(cd[0], ensure_ascii=False))
                tm = pb.get('target_modes')
                print('-- target_modes:', json.dumps(tm, ensure_ascii=False)[:300] if tm else None)
                print('-- has deprecated execution_mode:', 'execution_mode' in pb, '| serial_first:', 'serial_first' in pb)
        with open(os.path.join(ART, 'post_tasks_bodies.json'), 'w', encoding='utf-8') as f:
            json.dump(parsed_bodies, f, ensure_ascii=False, indent=2)

        # ===== 深色：编辑弹窗（回显 deviceType） =====
        set_theme(drv, 'dark')
        drv.get(BASE + '/start-test?step=1')
        WebDriverWait(drv, 25).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(5)
        try:
            open_api_edit_existing(drv, API_NAME)
            time.sleep(1.5)
            _shot(drv, '03_api_edit_dark', 'dark')
            val = get_dialog_device_type_value(drv)
            print('edit dialog deviceType value (dark):', val)
            _shot(drv, '04_device_type_value_dark', 'dark')
        except Exception as e:
            print('dark edit open failed:', e)
            _shot(drv, '03_dark_error', 'dark')

        errs = drv.execute_script('return (window.__iatpErrors || []).slice()')
        print('console.error count:', len(errs))
        for e in errs[:10]:
            print('  ERR:', e[:250])
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
