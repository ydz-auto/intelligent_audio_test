# -*- coding: utf-8 -*-
"""INT-1486 脚本 B：任务命名弹窗提交 + 步骤三用例详情弹窗 + 任务回读。"""
import json, os, time
import urllib.request
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

BASE = 'http://localhost:15173'
API = 'http://127.0.0.1:15000'
TOKEN_FILE = 'tests/ui/artifacts/int1486/token.txt'
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = 'tests/ui/artifacts/int1486'
os.makedirs(ART, exist_ok=True)
TASK_NAME = f'接线测试_INT1486_任务_{str(int(time.time()))[-6:]}'

FETCH_PATCH = r"""
window.__fetchLog = [];
const __origFetch = window.fetch;
window.fetch = function(input, init) {
  let url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = (init && init.method) || (input && input.method) || 'GET';
  const entry = { url: String(url), method: method, status: null,
                  reqBody: init && init.body ? String(init.body).slice(0, 12000) : null, resBody: null };
  window.__fetchLog.push(entry);
  return __origFetch.apply(this, arguments).then(async function(res) {
    entry.status = res.status;
    try { entry.resBody = (await res.clone().text()).slice(0, 3000); } catch (e) {}
    return res;
  }).catch(function(e) { entry.status = 'ERR ' + e; throw e; });
};
"""


def api_req(method, path, token, body=None):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    r = urllib.request.Request(API + path, data=data, method=method,
                               headers={'Authorization': 'Bearer ' + token,
                                        'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            return resp.status, json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')[:400]


def _driver(token):
    o = Options(); o.binary_location = CHROME_BINARY
    for a in ['--headless=new', '--window-size=1600,1000', '--disable-gpu', '--no-sandbox', '--lang=zh-CN',
              '--disable-dev-shm-usage', '--no-first-run', '--no-default-browser-check']:
        o.add_argument(a)
    import winreg
    major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    path = ''
    if major and os.path.isdir(cache):
        for v in os.listdir(cache):
            exe = os.path.join(cache, v, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    if int([x for x in v.split('.') if x.isdigit()][0]) == major:
                        path = exe
                except (ValueError, IndexError):
                    continue
    drv = webdriver.Chrome(options=o, service=Service(executable_path=path) if path else Service())
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
        'source': "try{localStorage.setItem('iatp:auth:token:v1', %s)}catch(e){}" % json.dumps(token)})
    return drv


def login(drv):
    drv.get(BASE + '/login')
    WebDriverWait(drv, 25).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)
    if drv.find_elements(By.ID, 'username'):
        drv.find_element(By.ID, 'username').send_keys('接线测试_admin')
        drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
        drv.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]").click()
        WebDriverWait(drv, 25).until(lambda d: '/login' not in d.current_url)
    time.sleep(2)
    return drv.current_url


def js_click(drv, el):
    drv.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)


def body_text(drv):
    return drv.execute_script('return document.body.innerText') or ''


def wait_text(drv, text, timeout=40):
    WebDriverWait(drv, timeout).until(lambda d: text in body_text(d))
    return True


def shot(drv, name):
    drv.save_screenshot(os.path.join(ART, name))
    print('SHOT', name)


def log_since(drv, start):
    log = drv.execute_script('return window.__fetchLog || []')
    for it in log[start:]:
        if '/tasks' in it['url']:
            print('TASK-REQ', it['method'], it['status'], it['url'])
            if it['method'] == 'POST' and it.get('reqBody'):
                print('   BODY', it['reqBody'][:3000])
            if it.get('resBody'):
                print('   RES', it['resBody'][:400])
    return len(log)


def main():
    token = open(TOKEN_FILE).read().strip()
    drv = _driver(token)
    try:
        drv.get(BASE + '/start-test')
        time.sleep(3)
        print('URL after token inject:', drv.current_url)
        st, dv = api_req('GET', '/api/v1/test-devices?per_page=1000', token)
        st, ap = api_req('GET', '/api/v1/apis?per_page=1000', token)
        devs = dv['data']['items']
        apis = ap['data']['items']
        my_dev = next((x for x in devs if x['name'].startswith('接线测试_INT1486_设备')), None)
        my_api = next((x for x in apis if x['name'].startswith('接线测试_INT1486_APIX')), None)
        print('MY_DEVICE', json.dumps(my_dev, ensure_ascii=False)[:150])
        print('MY_API', json.dumps(my_api, ensure_ascii=False)[:150])

        drv.get(BASE + '/start-test')
        wait_text(drv, '按分组', 60)
        # 用例列表按分组聚合（首屏拉 /testcases 可能 20~30s）
        for _ in range(30):
            if drv.find_elements(By.CSS_SELECTOR, '[aria-label^="全选分组 "]'):
                break
            time.sleep(2)
        print('group checkboxes ready=', len(drv.find_elements(By.CSS_SELECTOR, '[aria-label^="全选分组 "]')))
        time.sleep(2)
        # 选 2 条用例
        span = drv.find_elements(By.XPATH, "//span[normalize-space()='话轮接管']")
        if not span:
            span = drv.find_elements(By.XPATH, "//span[contains(@class,'font-medium') and contains(@class,'truncate')]")
        print('group headers found=', len(span), 'body empty-state:', '没有找到符合条件的测试用例' in body_text(drv))
        js_click(drv, span[0]); time.sleep(3)
        boxes = drv.find_elements(By.CSS_SELECTOR, '[aria-label^="选择 "]')
        for b in boxes[:2]:
            js_click(drv, b); time.sleep(0.4)
        print('STEP1 summary:', [ln for ln in body_text(drv).splitlines() if '已选' in ln][:1])
        shot(drv, 'B_step1_light.png')
        js_click(drv, drv.find_elements(By.XPATH, "//button[normalize-space(.)='下一步']")[0]); time.sleep(5)
        wait_text(drv, '执行参数', 40); time.sleep(2)
        # 选设备 + API
        if my_dev:
            cb = drv.find_elements(By.CSS_SELECTOR, f'[aria-label="选择设备 {my_dev["name"]}"]')
            if cb:
                js_click(drv, cb[0]); time.sleep(1.5)
        if my_api:
            cb = drv.find_elements(By.CSS_SELECTOR, f'[aria-label="选择 API {my_api["name"]}"]')
            if cb:
                js_click(drv, cb[0]); time.sleep(1.5)
        print('STEP2 summary:', [ln for ln in body_text(drv).splitlines() if '个资源' in ln or ('台设备' in ln and 'API' in ln)][:3])
        shot(drv, 'B_step2_selected_light.png')

        mark = len(drv.execute_script('return window.__fetchLog || []'))
        # 开始测试 → 任务命名弹窗
        start = drv.find_elements(By.XPATH, "//button[normalize-space(.)='开始测试']")
        print('START buttons=', len(start))
        js_click(drv, start[-1]); time.sleep(2.5)
        t = body_text(drv)
        print('MODAL task-name open:', '任务名称' in t and '开头描述' not in t, '| has 请输入一个描述性:', '请输入一个描述性的任务名称' in t)
        ti = drv.find_elements(By.CSS_SELECTOR, 'input#task-name')
        print('MODAL task-name default:', ti[0].get_attribute('value') if ti else None)
        print('MODAL task-name summary line:', [ln for ln in t.splitlines() if '条 ·' in ln][:2])
        shot(drv, 'B_task_name_light.png')
        # 清空 → 校验/禁用
        if ti:
            ti[0].send_keys(Keys.CONTROL, 'a'); ti[0].send_keys(Keys.DELETE); time.sleep(1)
            submit = drv.find_elements(By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='开始测试']")
            print('MODAL task-name empty submit disabled:', submit[0].get_attribute('disabled') is not None if submit else 'no-btn')
            # 取消
            cancel = drv.find_elements(By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='取消']")
            if cancel:
                js_click(drv, cancel[0]); time.sleep(1.5)
            print('MODAL task-name closed by cancel:', not drv.find_elements(By.XPATH, "//div[@role='dialog']"))
            # 重开 → 默认名恢复
            js_click(drv, drv.find_elements(By.XPATH, "//button[normalize-space(.)='开始测试']")[-1]); time.sleep(2)
            ti = drv.find_elements(By.CSS_SELECTOR, 'input#task-name')
            print('MODAL task-name reopened default:', ti[0].get_attribute('value') if ti else None)
            ti[0].send_keys(Keys.CONTROL, 'a'); ti[0].send_keys(Keys.DELETE); ti[0].send_keys(TASK_NAME)
            time.sleep(0.8)
            shot(drv, 'B_task_name_filled_light.png')
            mark = len(drv.execute_script('return window.__fetchLog || []'))
            js_click(drv, drv.find_elements(By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='开始测试']")[0])
            time.sleep(12)
        print('AFTER SUBMIT url:', drv.current_url)
        print('AFTER SUBMIT body has 执行测试:', '执行测试' in body_text(drv))
        log_since(drv, mark)
        shot(drv, 'B_step3_executing_light.png')

        # 任务回读
        st, tl = api_req('GET', '/api/v1/tasks?page=1&per_page=50&keyword=' + urllib.parse.quote(TASK_NAME), token)
        items = (tl.get('data', tl) or {}).get('items', []) if isinstance(tl, dict) else []
        task = next((x for x in items if x.get('name') == TASK_NAME), None)
        print('READBACK task:', json.dumps(task, ensure_ascii=False)[:800] if task else 'NOT FOUND in list')
        if not task:
            st, tl2 = api_req('GET', '/api/v1/tasks?page=1&per_page=10', token)
            d2 = tl2.get('data', tl2) if isinstance(tl2, dict) else {}
            items2 = d2.get('items', []) if isinstance(d2, dict) else []
            print('TASKS list head:', json.dumps(items2[:3], ensure_ascii=False)[:800])

        # 步骤三用例详情弹窗
        time.sleep(5)
        names = [e for e in drv.find_elements(By.TAG_NAME, 'button') if '测试用例_' in (e.text or '')]
        print('STEP3 case buttons=', len(names))
        if names:
            js_click(drv, names[0]); time.sleep(5)
            t = body_text(drv)
            print('MODAL case-detail open:', any(k in t for k in ['执行结果', '执行日志', '轮次']))
            idx = max(t.find('执行结果'), t.find('执行日志'))
            print('MODAL case-detail body:', t[max(0, idx - 200):idx + 500].replace('\n', ' | '))
            shot(drv, 'B_case_detail_light.png')
            # Esc 关闭
            drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE); time.sleep(1.5)
            print('MODAL case-detail closed by Esc:', not any('执行日志' in (x.text or '') for x in drv.find_elements(By.CSS_SELECTOR, 'div[role="dialog"]')))

        # 任务页可见
        drv.get(BASE + '/tasks/daily')
        time.sleep(6)
        print('TASKS page has task:', TASK_NAME in body_text(drv))
        shot(drv, 'B_tasks_page_light.png')
        print('TASK_NAME', TASK_NAME)
        print('DONE B')
    finally:
        drv.quit()


if __name__ == '__main__':
    import urllib.parse
    main()
