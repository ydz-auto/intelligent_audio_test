# -*- coding: utf-8 -*-
"""INT-1486 脚本 A2：步骤一用例/分组核对 + 步骤二资源/参数 + API 编辑弹窗 + API 健康检查弹窗。"""
import json, os, time, re
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

FETCH_PATCH = r"""
window.__fetchLog = [];
const __origFetch = window.fetch;
window.fetch = function(input, init) {
  let url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = (init && init.method) || (input && input.method) || 'GET';
  const entry = { url: String(url), method: method, status: null,
                  reqBody: init && init.body ? String(init.body).slice(0, 8000) : null, resBody: null };
  window.__fetchLog.push(entry);
  return __origFetch.apply(this, arguments).then(async function(res) {
    entry.status = res.status;
    try { entry.resBody = (await res.clone().text()).slice(0, 4000); } catch (e) {}
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
        with urllib.request.urlopen(r, timeout=180) as resp:
            return resp.status, json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')[:400]


def _driver():
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
    return drv


def login(drv):
    drv.get(BASE + '/login')
    WebDriverWait(drv, 25).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)
    try:
        u = WebDriverWait(drv, 10).until(lambda d: d.find_element(By.ID, 'username') if d.find_elements(By.ID, 'username') else False)
        u.send_keys('接线测试_admin')
        drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
        drv.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]").click()
        WebDriverWait(drv, 25).until(lambda d: '/login' not in d.current_url)
    except Exception:
        pass
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


def fetch_log(drv):
    return drv.execute_script('return window.__fetchLog || []')


def print_new_log(drv, start, label, only=None):
    log = fetch_log(drv)
    for it in log[start:]:
        if only and not any(k in it['url'] for k in only):
            continue
        print(label, it['method'], it['status'], it['url'])
        if it.get('reqBody'):
            print('   REQ', it['reqBody'][:1400])
        if it.get('resBody') and it['method'] != 'GET':
            print('   RES', it['resBody'][:400])
    return len(log)


def main():
    token = open(TOKEN_FILE).read().strip()
    drv = _driver()
    try:
        print('LOGIN:', login(drv))
        _, g = api_req('GET', '/api/v1/groups?page=1&per_page=200', token)
        _, tc = api_req('GET', '/api/v1/testcases?page=1&per_page=1', token)
        _, dv = api_req('GET', '/api/v1/test-devices?per_page=1000', token)
        _, ap = api_req('GET', '/api/v1/apis?per_page=1000', token)
        _, labs = api_req('GET', '/api/v1/laboratories', token)
        gd = g.get('data', g); tcd = tc.get('data', tc); dvd = dv.get('data', dv); apd = ap.get('data', ap)
        api_groups = gd.get('items', [])
        api_devices = dvd.get('items', [])
        api_apis = apd.get('items', [])
        print('API groups=', len(api_groups), 'cases total=', tcd.get('total'),
              'devices=', len(api_devices), 'apis=', len(api_apis), 'labs=', labs.get('data', {}).get('total'))
        print('API group counts:', json.dumps([{'n': x['name'], 'c': x.get('test_case_count')} for x in api_groups], ensure_ascii=False))
        print('API devices:', json.dumps([{'id': x['id'], 'n': x['name'], 's': x.get('status')} for x in api_devices], ensure_ascii=False))
        print('API apis:', json.dumps([{'id': x['id'], 'n': x['name'], 's': x.get('status')} for x in api_apis], ensure_ascii=False))
        my_dev = next((x for x in api_devices if x['name'].startswith('接线测试_INT1486_设备')), None)
        my_api = next((x for x in api_apis if x['name'].startswith('接线测试_INT1486_APIX')), None)
        print('MY_DEVICE', json.dumps(my_dev, ensure_ascii=False)[:200])
        print('MY_API', json.dumps(my_api, ensure_ascii=False)[:200])

        drv.get(BASE + '/start-test')
        wait_text(drv, '按分组', 60)
        time.sleep(10)

        # ---------- 步骤一 ----------
        txt = body_text(drv)
        for _ in range(6):
            if '个分组 · 加载更多' not in txt:
                break
            btn = drv.find_elements(By.XPATH, "//button[contains(normalize-space(.), '加载更多')]")
            if not btn:
                break
            js_click(drv, btn[0]); time.sleep(2.5); txt = body_text(drv)
        m = re.search(r'已显示\s*(\d+)\s*/\s*(\d+)\s*个分组', txt)
        print('STEP1 pagination text:', m.group(0) if m else [ln for ln in txt.splitlines() if '分组' in ln][:3])
        groups_ui = drv.execute_script("""
          return Array.from(document.querySelectorAll('[aria-label^="全选分组 "]')).map(function(cb) {
            const row = cb.parentElement.parentElement;
            const badge = row ? row.querySelector('.font-mono') : null;
            return { name: (cb.getAttribute('aria-label') || '').replace('全选分组 ', ''), count: badge ? badge.textContent.trim() : '' };
          });
        """)
        print('STEP1 UI groups=', len(groups_ui))
        ui_map = {x['name']: x['count'] for x in groups_ui}
        mismatch = []
        for grp in api_groups:
            ui = ui_map.get(grp['name'])
            expected = f"{grp.get('test_case_count')} 条"
            if ui != expected:
                mismatch.append((grp['name'], ui, expected))
        print('STEP1 group count mismatches:', mismatch)
        shot(drv, 'A_step1_groups_light.png')

        span = drv.find_elements(By.XPATH, "//span[normalize-space()='话轮接管']")
        js_click(drv, span[0]); time.sleep(4)
        boxes = [e for e in drv.find_elements(By.CSS_SELECTOR, '[aria-label^="选择 "]')]
        picked = []
        for b in boxes[:2]:
            picked.append(b.get_attribute('aria-label'))
            js_click(drv, b); time.sleep(0.5)
        print('STEP1 picked:', json.dumps(picked, ensure_ascii=False))
        time.sleep(1)
        print('STEP1 summary:', [ln for ln in body_text(drv).splitlines() if '已选' in ln or '手动勾选' in ln])
        shot(drv, 'A_step1_selected_light.png')

        inp = drv.find_element(By.CSS_SELECTOR, 'input[placeholder="搜索用例名称或描述"]')
        inp.send_keys(Keys.CONTROL, 'a'); inp.send_keys(Keys.DELETE); inp.send_keys('zzz_no_such_case_1486')
        time.sleep(3)
        t = body_text(drv)
        print('STEP1 search empty state:', '没有找到符合条件的测试用例' in t)
        shot(drv, 'A_step1_search_empty_light.png')
        inp = drv.find_element(By.CSS_SELECTOR, 'input[placeholder="搜索用例名称或描述"]')
        inp.send_keys(Keys.CONTROL, 'a'); inp.send_keys(Keys.DELETE); time.sleep(3)

        # ---------- 步骤二 ----------
        nxt = drv.find_elements(By.XPATH, "//button[normalize-space(.)='下一步']")
        js_click(drv, nxt[0]); time.sleep(5)
        wait_text(drv, '执行参数', 40); time.sleep(2)
        t = body_text(drv)
        print('STEP2 counts:', [ln for ln in t.splitlines() if '在线可执行设备' in ln or '可执行 API' in ln or ln.startswith('共 ')])
        trig = drv.find_elements(By.XPATH, "//button[@role='combobox'][contains(normalize-space(.), '全部实验室')]")
        lab_opts = []
        if trig:
            js_click(drv, trig[0]); time.sleep(1.5)
            lab_opts = [e.text for e in drv.find_elements(By.CSS_SELECTOR, '[role="option"]') if e.is_displayed()]
            drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE); time.sleep(0.5)
        print('STEP2 lab dropdown options:', json.dumps(lab_opts, ensure_ascii=False), '(API /laboratories total=',
              labs.get('data', {}).get('total'), ')')
        shot(drv, 'A_step2_resources_light.png')

        if my_dev:
            cb = drv.find_elements(By.CSS_SELECTOR, f'[aria-label="选择设备 {my_dev["name"]}"]')
            if cb:
                js_click(drv, cb[0]); time.sleep(2)
        print('STEP2 summary after device:', [ln for ln in body_text(drv).splitlines() if '台设备' in ln and 'API' in ln][:2])
        radios = drv.find_elements(By.CSS_SELECTOR, '[role="radio"]')
        print('STEP2 mode radios=', [r.text for r in radios])
        serial = [r for r in radios if r.text.strip() == '串行']
        if serial:
            js_click(drv, serial[0]); time.sleep(1.5)
        print('STEP2 diagram serial:', '串行目标' in body_text(drv))
        for label, val in [('测试轮数', '2'), ('超时时间', '90'), ('重试次数', '1'), ('并发任务数', '2')]:
            ins = drv.find_elements(By.XPATH, f"//label[normalize-space()='{label}']/following::input[1]")
            if ins:
                ins[0].send_keys(Keys.CONTROL, 'a'); ins[0].send_keys(Keys.DELETE); ins[0].send_keys(val)
        time.sleep(1)
        shot(drv, 'A_step2_selected_light.png')

        # ---------- API 新增弹窗 ----------
        mark = len(fetch_log(drv))
        add = drv.find_elements(By.XPATH, "//button[normalize-space(.)='新增 API']")
        js_click(drv, add[0]); time.sleep(2)
        print('MODAL api-edit new title:', '新增 API' in body_text(drv))
        js_click(drv, drv.find_elements(By.XPATH, "//div[@role='dialog']//button[@type='submit']")[0]); time.sleep(1.5)
        print('MODAL api-edit empty-name validation:', '请输入必填项' in body_text(drv))
        shot(drv, 'A_api_edit_validation_light.png')
        name = f'接线测试_INT1486_API_{str(int(time.time()))[-6:]}'
        drv.find_element(By.ID, 'api-name').send_keys(name)
        alg = drv.find_elements(By.XPATH, "//div[@role='dialog']//label[normalize-space(.)='关联算法 *']/following::button[@role='combobox'][1]")
        if alg:
            js_click(drv, alg[0]); time.sleep(1)
            opts = [e for e in drv.find_elements(By.CSS_SELECTOR, '[role="option"]') if e.is_displayed()]
            print('MODAL api-edit algorithm options=', [e.text for e in opts])
            if opts:
                js_click(drv, opts[0]); time.sleep(0.8)
        js_click(drv, drv.find_elements(By.XPATH, "//div[@role='dialog']//button[contains(normalize-space(.), '添加端点')]")[0]); time.sleep(1)
        drv.find_element(By.CSS_SELECTOR, 'input[aria-label="端点 URL"]').send_keys('https://example.test/probe1486')
        oc = drv.find_element(By.ID, 'other-config'); oc.send_keys('{bad json')
        js_click(drv, drv.find_elements(By.XPATH, "//div[@role='dialog']//button[@type='submit']")[0]); time.sleep(1.5)
        print('MODAL api-edit invalid-json validation:', 'JSON 格式不正确' in body_text(drv))
        oc = drv.find_element(By.ID, 'other-config'); oc.send_keys(Keys.CONTROL, 'a'); oc.send_keys(Keys.DELETE); time.sleep(0.5)
        js_click(drv, drv.find_elements(By.XPATH, "//div[@role='dialog']//button[@type='submit']")[0]); time.sleep(3.5)
        print('MODAL api-edit closed:', not drv.find_elements(By.XPATH, "//div[@role='dialog']"))
        print_new_log(drv, mark, 'API-CRUD', only=['/apis'])
        st, ap2 = api_req('GET', '/api/v1/apis?per_page=1000', token)
        created = [x for x in ap2.get('data', ap2).get('items', []) if x['name'] == name]
        print('READBACK created api:', json.dumps(created, ensure_ascii=False)[:700])
        created_id = created[0]['id'] if created else None

        if created_id is not None:
            mark = len(fetch_log(drv))
            more = drv.find_elements(By.XPATH, f"//button[@aria-label='更多操作']")
            # 最后一台 API 卡通常是新建的（按创建顺序）
            js_click(drv, more[-1]); time.sleep(1)
            ed = drv.find_elements(By.XPATH, "//*[@role='menuitem'][contains(normalize-space(.), '编辑')]")
            js_click(drv, ed[0]); time.sleep(2)
            print('MODAL api-edit edit title:', '编辑 API' in body_text(drv))
            val = drv.find_element(By.ID, 'api-name').get_attribute('value')
            print('MODAL api-edit prefill name match:', val == name, val)
            epv = drv.find_elements(By.CSS_SELECTOR, 'input[aria-label="端点 URL"]')
            print('MODAL api-edit prefill endpoint:', epv[0].get_attribute('value') if epv else None)
            shot(drv, 'A_api_edit_existing_light.png')
            name2 = name + '_改'
            nm = drv.find_element(By.ID, 'api-name'); nm.send_keys(Keys.CONTROL, 'a'); nm.send_keys(Keys.DELETE); nm.send_keys(name2)
            js_click(drv, drv.find_elements(By.XPATH, "//div[@role='dialog']//button[@type='submit']")[0]); time.sleep(3.5)
            print_new_log(drv, mark, 'API-UPDATE', only=['/apis'])
            st, ap3 = api_req('GET', '/api/v1/apis?per_page=1000', token)
            print('READBACK updated api:', json.dumps(
                [{'id': x['id'], 'name': x['name'], 'status': x.get('status')} for x in ap3.get('data', ap3).get('items', [])
                 if x['id'] == created_id], ensure_ascii=False))

        # ---------- API 健康检查 ----------
        if my_api:
            mark = len(fetch_log(drv))
            btn = drv.find_elements(By.CSS_SELECTOR, f'[aria-label="连接测试 {my_api["name"]}"]')
            if btn:
                js_click(drv, btn[0]); time.sleep(8)
                t = body_text(drv)
                print('MODAL api-health open:', '连接测试结果' in t)
                idx = t.find('连接测试结果')
                print('MODAL api-health body:', t[idx:idx + 400].replace('\n', ' | '))
                shot(drv, 'A_api_health_light.png')
                print_new_log(drv, mark, 'API-HEALTH', only=['/health'])
            else:
                print('MODAL api-health: button not found')

        print('CREATED_API_ID_UI', created_id)
        print('MY_DEVICE_ID', my_dev['id'] if my_dev else None)
        print('MY_API_ID', my_api['id'] if my_api else None)
        print('TOKEN_OK', bool(token))
        print('DONE A2')
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
