# -*- coding: utf-8 -*-
"""INT-1486 脚本 C（续验）：任务命名真实提交+回读、case-detail-dialog、api-health-dialog、
API 编辑回填+改名回读、执行模式串行 / 网络参数请求体、四窗深色截图。

环境：前端 docker 15173（React），后端 docker 真实库 15000。
"""
import json, os, sys, time, traceback, urllib.parse, urllib.request
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

BASE = 'http://localhost:15173'
API = 'http://127.0.0.1:15000'
ART = 'tests/ui/artifacts/int1486'
TOKEN_FILE = os.path.join(ART, 'token.txt')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
os.makedirs(ART, exist_ok=True)
SUFFIX = str(int(time.time()))[-6:]
TASK_NAME = f'接线测试_INT1486_任务_{SUFFIX}'
API_NAME = f'接线测试_INT1486_APIXC_{SUFFIX}'
API_NAME2 = API_NAME + '_改'
API_HEALTH_NAME = f'接线测试_INT1486_HC_{SUFFIX}'
DEVICE_NAME = 'pura90gpt'

FETCH_PATCH = r"""
window.__fetchLog = [];
const __origFetch = window.fetch;
window.fetch = function(input, init) {
  let url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = (init && init.method) || (input && input.method) || 'GET';
  const entry = { url: String(url), method: method, status: null,
                  reqBody: init && init.body ? String(init.body).slice(0, 20000) : null, resBody: null };
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
            raw = resp.read().decode('utf-8')
            try:
                return resp.status, json.loads(raw)
            except Exception:
                return resp.status, raw[:500]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')[:500]


def make_driver(token):
    o = Options(); o.binary_location = CHROME_BINARY
    for a in ['--headless=new', '--window-size=1680,1050', '--disable-gpu', '--no-sandbox', '--lang=zh-CN',
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
    d = webdriver.Chrome(options=o, service=Service(executable_path=path) if path else Service())
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
        'source': "try{localStorage.setItem('iatp:auth:token:v1', %s)}catch(e){}" % json.dumps(token)})
    return d


def js_click(d, el):
    d.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)


def text(d):
    return d.execute_script('return document.body.innerText') or ''


def wait_text(d, s, timeout=60):
    WebDriverWait(d, timeout).until(lambda x: s in text(x))
    return True


def wait_gone(d, s, timeout=30):
    WebDriverWait(d, timeout).until(lambda x: s not in text(x))


def shot(d, name):
    p = os.path.join(ART, name)
    d.save_screenshot(p)
    print('SHOT', name, os.path.getsize(p))


def log_mark(d):
    return len(d.execute_script('return window.__fetchLog || []'))


def log_show(d, mark, keys=('/tasks', '/apis', 'health'), maxn=40):
    entries = d.execute_script('return window.__fetchLog || []')
    out = []
    for it in entries[mark:]:
        if any(k in it['url'] for k in keys):
            out.append(it)
    for it in out[:maxn]:
        print('REQ', it['method'], it['status'], it['url'])
        if it.get('reqBody') and it['method'] != 'GET':
            print('   BODY', it['reqBody'][:4000])
        if it.get('resBody') and it['method'] != 'GET':
            print('   RES ', it['resBody'][:600])
    return out


def dialogs(d):
    return d.find_elements(By.CSS_SELECTOR, '[role="dialog"]')


def dialog_text(d):
    ds = d.find_elements(By.CSS_SELECTOR, '[role="dialog"]')
    return '\n'.join(x.text for x in ds) if ds else ''


def close_dialog(d):
    for _ in range(3):
        try:
            d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        except Exception:
            pass
        time.sleep(1)
        if not dialogs(d):
            return True
    for b in d.find_elements(By.CSS_SELECTOR, '[role="dialog"] button'):
        if (b.get_attribute('aria-label') or '') in ('关闭', 'Close') or (b.text or '').strip() == '关闭':
            js_click(d, b); time.sleep(1)
            break
    return not dialogs(d)


KEYWORD = 'JG0081'


def enter_resources(d):
    """步骤一：用搜索关键字收窄筛选（filter-all 模式，不手动勾选），进入步骤二。"""
    d.get(BASE + '/start-test')
    wait_text(d, '按分组', 90)
    for _ in range(40):
        if d.find_elements(By.CSS_SELECTOR, '[aria-label^="全选分组 "]'):
            break
        time.sleep(2)
    time.sleep(2)
    si = d.find_elements(By.CSS_SELECTOR, "[aria-label='搜索用例']")
    print('search input', len(si))
    if si:
        si[0].send_keys(Keys.CONTROL, 'a'); si[0].send_keys(Keys.DELETE)
        si[0].send_keys(KEYWORD)
        time.sleep(6)
    print('STEP1 summary', [ln for ln in text(d).splitlines() if '未选择用例时' in ln or '已选择' in ln][:3])
    boxes = d.find_elements(By.CSS_SELECTOR, '[aria-label^="选择 "]')
    print('visible case rows', len(boxes))
    js_click(d, d.find_elements(By.XPATH, "//button[normalize-space(.)='下一步']")[0])
    wait_text(d, '执行参数', 60)
    time.sleep(3)


def select_cases(d):
    """手工勾选 2 条用例（用于复现 manual 选择链路）。"""
    for _ in range(40):
        if d.find_elements(By.CSS_SELECTOR, '[aria-label^="全选分组 "]'):
            break
        time.sleep(2)
    time.sleep(2)
    spans = d.find_elements(By.XPATH, "//span[normalize-space()='话轮接管']")
    if spans:
        js_click(d, spans[0]); time.sleep(3)
    for _ in range(20):
        if len(d.find_elements(By.CSS_SELECTOR, '[aria-label^="选择 "]')) >= 3:
            break
        time.sleep(2)
    boxes = d.find_elements(By.CSS_SELECTOR, '[aria-label^="选择 "]')
    print('case checkboxes', len(boxes), [b.get_attribute('aria-label') for b in boxes[:3]])
    for b in boxes[:2]:
        js_click(d, b); time.sleep(0.6)
    print('STEP1 summary', [ln for ln in text(d).splitlines() if '已选' in ln][:2])
    return len(boxes)


def goto_resources(d):
    """从 /start-test 进入步骤二（执行资源）；filter-all 收窄到 KEYWORD。"""
    enter_resources(d)


def find_api_card_button(d, name, aria):
    els = d.find_elements(By.CSS_SELECTOR, f'[aria-label="{aria} {name}"]')
    return els[0] if els else None


def card_of(d, el):
    return d.execute_script('''
      let n = arguments[0];
      while (n && n !== document.body) {
        if (n.getAttribute && n.getAttribute('data-slot') === 'card') return n;
        n = n.parentElement;
      }
      return arguments[0].closest('div.rounded-xl, div[class*="card"], div[class*="border"]') || arguments[0].parentElement;
    ''', el)


def main():
    token = open(TOKEN_FILE).read().strip()
    d = make_driver(token)
    state = {}
    try:
        # ---------- 缺陷复现A：手动勾选用例后「开始测试」恒被拦截 ----------
        d.get(BASE + '/start-test')
        wait_text(d, '按分组', 90)
        select_cases(d)
        js_click(d, d.find_elements(By.XPATH, "//button[normalize-space(.)='下一步']")[0])
        wait_text(d, '执行参数', 60); time.sleep(2)
        dc = d.find_elements(By.CSS_SELECTOR, f'[aria-label="选择设备 {DEVICE_NAME}"]')
        if dc:
            js_click(d, dc[0]); time.sleep(1)
        st0 = d.find_elements(By.XPATH, "//button[normalize-space(.)='开始测试']")
        js_click(d, st0[-1]); time.sleep(2)
        print('MANUAL-SUBMIT dialogs=', len(dialogs(d)),
              'toast=', [ln for ln in text(d).splitlines() if '没有可用的测试用例' in ln][:2])
        shot(d, 'C_defect_manual_submit_light.png')

        # ---------- 步骤一 → 步骤二（filter-all） ----------
        goto_resources(d)
        t = text(d)
        print('STEP2 heading', [ln for ln in t.splitlines() if '台在线可执行设备' in ln or '个可执行 API' in ln][:2])

        # ---------- API 新建（UI 入口观测；算法下拉因 env 缺口为空，保存被必填校验拦） ----------
        mark = log_mark(d)
        js_click(d, d.find_elements(By.XPATH, "//button[normalize-space(.)='新增 API']")[0])
        time.sleep(2)
        name_in = d.find_element(By.ID, 'api-name')
        name_in.send_keys(API_NAME)
        add_ep = d.find_elements(By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='添加端点']")
        print('add endpoint btn', len(add_ep))
        if add_ep:
            js_click(d, add_ep[0]); time.sleep(1)
        urls = d.find_elements(By.CSS_SELECTOR, "input[aria-label='端点 URL']")
        print('endpoint url inputs', len(urls))
        if urls:
            urls[0].send_keys('https://example.test/int1486c')
        # 关联算法 *（必填 Select）：未选时保存被拦（校验）
        algs = d.find_elements(By.XPATH, "//div[@role='dialog']//button[@role='combobox']")
        print('dialog comboboxes', len(algs))
        if algs:
            js_click(d, algs[0]); time.sleep(1.2)
            opts = d.find_elements(By.CSS_SELECTOR, "[role='option']")
            print('algorithm options', [o.text for o in opts][:10])
            if opts:
                js_click(d, opts[0]); time.sleep(1)
        print('CREATE dialog text head:', dialog_text(d)[:300].replace('\n', ' | '))
        shot(d, 'C_api_create_light.png')
        js_click(d, d.find_elements(By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='保存']")[0])
        try:
            wait_gone(d, '新增后列表自动刷新', 12)
        except Exception:
            print('CREATE save blocked; dialog now:', dialog_text(d)[:600].replace('\n', ' | '))
            shot(d, 'C_api_create_blocked.png')
        log_show(d, mark, keys=('/apis',))
        close_dialog(d)
        # 健康检查用第二个自建 API（契约创建即可；健康检查会把 API 置 offline，避免影响任务提交）
        st, hc = api_req('POST', '/api/v1/apis', token, {
            'name': API_HEALTH_NAME, 'description': 'INT-1486 健康检查临时', 'algorithm_type': 'voice_llm',
            'default_max_process': 5,
            'endpoints': [{'endpoint': 'https://example.test/int1486-health', 'name': None, 'max_process': 1,
                           'max_timeout': 30, 'max_audio_duration': 60, 'status': 'online', 'priority': 1,
                           'description': None}]})
        print('CONTRACT create health api', st, json.dumps(hc, ensure_ascii=False)[:200])
        state['health_api_id'] = (hc.get('data') or {}).get('id') if isinstance(hc, dict) else None
        time.sleep(1)
        st, apis = api_req('GET', '/api/v1/apis?per_page=1000', token)
        items = (apis.get('data', apis) or {}).get('items', [])
        mine = next((x for x in reversed(items) if x.get('name') == API_NAME), None)
        print('CREATED api', json.dumps(mine, ensure_ascii=False)[:400])
        state['api_id'] = mine and mine.get('id')

        # ---------- API 编辑回填 + 改名保存 + GET 回读 ----------
        if state['api_id']:
            enter_resources(d)
            cb = find_api_card_button(d, API_NAME, '选择 API')
            print('api card found', cb is not None)
            card = card_of(d, cb)
            more = card.find_elements(By.CSS_SELECTOR, '[aria-label="更多操作"]')
            print('more btn', len(more))
            js_click(d, more[0]); time.sleep(1.5)
            menuitem = d.find_elements(By.XPATH, "//*[@role='menuitem' and normalize-space(.)='编辑']")
            print('edit menu', len(menuitem))
            js_click(d, menuitem[0]); time.sleep(2)
            back_name = d.find_element(By.ID, 'api-name').get_attribute('value')
            back_url = d.find_elements(By.CSS_SELECTOR, "input[aria-label='端点 URL']")
            back_url_v = back_url[0].get_attribute('value') if back_url else None
            print('EDIT backfill name=', repr(back_name), 'url=', repr(back_url_v))
            print('EDIT dialog text head:', dialog_text(d)[:400].replace('\n', ' | '))
            shot(d, 'C_api_edit_backfill_light.png')
            ni = d.find_element(By.ID, 'api-name')
            ni.send_keys(Keys.CONTROL, 'a'); ni.send_keys(Keys.DELETE); ni.send_keys(API_NAME2)
            time.sleep(0.6)
            mark = log_mark(d)
            js_click(d, d.find_elements(By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='保存']")[0])
            wait_gone(d, '修改被测 API 配置', 40)
            log_show(d, mark, keys=('/apis',))
            time.sleep(2)
            st, one = api_req('GET', f"/api/v1/apis/{state['api_id']}", token)
            print('READBACK api GET', st, json.dumps(one, ensure_ascii=False)[:800])
            state['api_name'] = API_NAME2
        else:
            state['api_name'] = API_NAME

        # ---------- 选设备 + API，串行 + 网络参数 ----------
        # 先做健康检查（自建健康检查 API，独立于任务资源，避免把待选 API 置 offline）
        hb = find_api_card_button(d, API_HEALTH_NAME, '连接测试')
        print('health btn', hb is not None)
        if hb:
            mark = log_mark(d)
            js_click(d, hb)
            time.sleep(0.6)
            print('HEALTH testing dialog:', dialog_text(d)[:200].replace('\n', ' | '))
            try:
                WebDriverWait(d, 60).until(lambda x: '重新测试' in dialog_text(x) or not dialogs(x))
            except Exception:
                pass
            print('HEALTH result dialog:', dialog_text(d)[:900].replace('\n', ' | '))
            shot(d, 'C_api_health_light.png')
            log_show(d, mark, keys=('/apis/', 'health'))
            print('HEALTH dialog closed:', close_dialog(d))

        dev_cb = d.find_elements(By.CSS_SELECTOR, f'[aria-label="选择设备 {DEVICE_NAME}"]')
        print('device checkbox', len(dev_cb))
        if dev_cb:
            js_click(d, dev_cb[0]); time.sleep(1.2)
        api_cb = find_api_card_button(d, state['api_name'], '选择 API')
        if api_cb:
            js_click(d, api_cb); time.sleep(1.2)
        print('RES summary', [ln for ln in text(d).splitlines() if '台设备' in ln and 'API' in ln][:3])
        # 逐卡串行
        modes = d.find_elements(By.CSS_SELECTOR, f'[aria-label="{DEVICE_NAME} 执行模式"]')
        print('mode control', len(modes))
        if modes:
            serial = modes[0].find_elements(By.XPATH, ".//button[normalize-space(.)='串行'] | .//label[normalize-space(.)='串行'] | .//*[normalize-space(.)='串行']")
            print('serial options', len(serial))
            if serial:
                js_click(d, serial[0]); time.sleep(1.5)
            print('MODE control text:', modes[0].text.replace('\n', '|'))
        print('SERIAL summary', [ln for ln in text(d).splitlines() if '串行' in ln][:4])
        # 示意图
        print('DIAGRAM text:', [ln for ln in text(d).splitlines() if '并行' in ln or '串行' in ln][:8])
        shot(d, 'C_step2_mode_serial_light.png')
        # 网络参数
        print('NETWORK block text:', [ln for ln in text(d).splitlines() if '网络配置' in ln or '当前：' in ln][:3])
        net = d.find_elements(By.XPATH, "//h4[normalize-space()='网络配置']/following-sibling::*//*[@data-slot='select-trigger'] | //h4[normalize-space()='网络配置']/following-sibling::*[self::button]")
        print('network select', len(net))
        if net:
            js_click(d, net[0]); time.sleep(1.2)
            opts = d.find_elements(By.CSS_SELECTOR, "[role='option']")
            print('network options', [o.text for o in opts])
            wifi = [o for o in opts if o.text.strip() == 'Wi-Fi']
            if wifi:
                js_click(d, wifi[0]); time.sleep(1)
        print('network now', [ln for ln in text(d).splitlines() if 'Wi-Fi' in ln][:2])

        # ---------- 任务命名弹窗：默认名 / 取消重开 / 真实提交 ----------
        starts = d.find_elements(By.XPATH, "//button[normalize-space(.)='开始测试']")
        print('start buttons', len(starts), [(s.text or '').strip()[:8] for s in starts])
        js_click(d, starts[-1]); time.sleep(2.5)
        print('after start click dialogs', len(dialogs(d)))
        print('after start click toast/body:', [ln for ln in text(d).splitlines() if '离线' in ln or '不可用' in ln or '请选择' in ln][:4])
        ti = d.find_elements(By.CSS_SELECTOR, 'input#task-name')
        print('TASKNAME default', repr(ti[0].get_attribute('value')) if ti else None)
        print('TASKNAME dialog:', dialog_text(d)[:400].replace('\n', ' | '))
        shot(d, 'C_taskname_light.png')
        if not ti:
            raise RuntimeError('task-name dialog did not open')
        # 清空 → 主钮禁用
        if ti:
            ti[0].send_keys(Keys.CONTROL, 'a'); ti[0].send_keys(Keys.DELETE); time.sleep(0.8)
            sub = d.find_elements(By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='开始测试']")
            print('empty submit disabled', sub[0].get_attribute('disabled') is not None if sub else 'no-btn')
        # 取消 → 重开（INT-1528 期望恢复默认名）
        cancel = d.find_elements(By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='取消']")
        if cancel:
            js_click(d, cancel[0]); time.sleep(1.5)
        print('closed by cancel', not dialogs(d))
        js_click(d, d.find_elements(By.XPATH, "//button[normalize-space(.)='开始测试']")[-1]); time.sleep(1.8)
        ti = d.find_elements(By.CSS_SELECTOR, 'input#task-name')
        print('REOPEN default name', repr(ti[0].get_attribute('value')) if ti else None)
        state['reopen_value'] = ti[0].get_attribute('value') if ti else None
        # 填真实名并提交
        ti[0].send_keys(Keys.CONTROL, 'a'); ti[0].send_keys(Keys.DELETE); ti[0].send_keys(TASK_NAME)
        time.sleep(0.8)
        shot(d, 'C_taskname_filled_light.png')
        mark = log_mark(d)
        js_click(d, d.find_elements(By.XPATH, "//div[@role='dialog']//button[normalize-space(.)='开始测试']")[0])
        time.sleep(15)
        print('AFTER SUBMIT url', d.current_url)
        print('AFTER SUBMIT has 执行', '执行' in text(d))
        log_show(d, mark, keys=('/tasks',))
        md = log_mark(d)
        try:
            WebDriverWait(d, 120).until(lambda x: '测试用例_' in text(x))
        except Exception:
            pass
        print('STEP2 executing body head:', text(d)[:600].replace('\n', ' | '))
        shot(d, 'C_step3_executing_light.png')

        # ---------- 任务回读 ----------
        st, tl = api_req('GET', '/api/v1/tasks?page=1&per_page=50&keyword=' + urllib.parse.quote(TASK_NAME), token)
        items = (tl.get('data', tl) or {}).get('items', []) if isinstance(tl, dict) else []
        task = next((x for x in items if x.get('name') == TASK_NAME), None)
        print('TASK readback', json.dumps(task, ensure_ascii=False)[:900] if task else 'NOT FOUND')
        if task:
            state['task_id'] = task.get('id')
            st, td = api_req('GET', f"/api/v1/tasks/{state['task_id']}", token)
            print('TASK detail GET', st, json.dumps(td, ensure_ascii=False)[:1500])

        # ---------- case-detail-dialog ----------
        names = [e for e in d.find_elements(By.TAG_NAME, 'button') if '测试用例_' in (e.text or '')]
        print('case rows', len(names))
        if names:
            mark = log_mark(d)
            js_click(d, names[0]); time.sleep(4)
            print('CASEDETAIL dialog:', dialog_text(d)[:1200].replace('\n', ' | '))
            shot(d, 'C_case_detail_light.png')
            log_show(d, mark, keys=('/cases/', '/detail'))
            # 关闭按钮
            closed = close_dialog(d)
            print('CASEDETAIL closed', closed)

        # ---------- 任务页可见 ----------
        d.get(BASE + '/tasks/daily'); time.sleep(6)
        print('TASKS page has task', TASK_NAME in text(d))
        shot(d, 'C_tasks_page_light.png')

        # ---------- 深色四窗 ----------
        d.get(BASE + '/start-test')
        wait_text(d, '按分组', 90)
        for _ in range(40):
            if d.find_elements(By.CSS_SELECTOR, '[aria-label^="全选分组 "]'):
                break
            time.sleep(2)
        time.sleep(2)
        # 主题抽屉
        try:
            js_click(d, d.find_element(By.CSS_SELECTOR, "[aria-label='打开主题设置']")); time.sleep(1.5)
            dark = d.find_elements(By.XPATH, "//*[normalize-space(.)='深色']")
            print('dark options', len(dark))
            if dark:
                js_click(d, dark[-1]); time.sleep(2)
            print('theme now', d.execute_script("return localStorage.getItem('iatp:theme:v1:mode')"))
            # 关闭抽屉（Esc）
            d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE); time.sleep(1.2)
        except Exception as e:
            print('THEME switch failed', e)
        # 按筛选进步骤二
        enter_resources(d)
        shot(d, 'C_step2_dark.png')
        # api-edit 深色
        cb = find_api_card_button(d, state['api_name'], '选择 API')
        if cb:
            card = card_of(d, cb)
            more = card.find_elements(By.CSS_SELECTOR, '[aria-label="更多操作"]')
            js_click(d, more[0]); time.sleep(1.2)
            mi = d.find_elements(By.XPATH, "//*[@role='menuitem' and normalize-space(.)='编辑']")
            js_click(d, mi[0]); time.sleep(2)
            shot(d, 'C_api_edit_dark.png')
            print('DARK api-edit dialog', dialog_text(d)[:200].replace('\n', ' | '))
            close_dialog(d)
        # api-health 深色
        hb = find_api_card_button(d, state['api_name'], '连接测试')
        if hb:
            js_click(d, hb)
            try:
                WebDriverWait(d, 60).until(lambda x: '重新测试' in dialog_text(x) or not dialogs(x))
            except Exception:
                pass
            time.sleep(1)
            shot(d, 'C_api_health_dark.png')
            close_dialog(d)
        # task-name 深色
        js_click(d, d.find_elements(By.XPATH, "//button[normalize-space(.)='开始测试']")[-1]); time.sleep(2)
        shot(d, 'C_taskname_dark.png')
        print('DARK taskname value', [x.get_attribute('value') for x in d.find_elements(By.CSS_SELECTOR, 'input#task-name')])
        close_dialog(d)
        # case-detail 深色（任务详情页共用同组件）
        if state.get('task_id'):
            d.get(BASE + f"/tasks/{state['task_id']}")
            time.sleep(6)
            print('task detail url', d.current_url)
            rows = [e for e in d.find_elements(By.TAG_NAME, 'button') if '测试用例_' in (e.text or '')]
            print('task detail rows', len(rows))
            if rows:
                js_click(d, rows[0]); time.sleep(4)
                shot(d, 'C_case_detail_dark.png')
                print('DARK case-detail', dialog_text(d)[:300].replace('\n', ' | '))
                close_dialog(d)

        # ---------- 清理自建数据 ----------
        if state.get('task_id'):
            print('CLEAN task del', api_req('DELETE', f"/api/v1/tasks/{state['task_id']}", token))
            print('CLEAN task purge', api_req('DELETE', f"/api/v1/tasks/{state['task_id']}/purge", token))
        if state.get('api_id'):
            print('CLEAN api del', api_req('DELETE', f"/api/v1/apis/{state['api_id']}", token))
        if state.get('health_api_id'):
            print('CLEAN health api del', api_req('DELETE', f"/api/v1/apis/{state['health_api_id']}", token))
        st, apis = api_req('GET', '/api/v1/apis?per_page=1000', token)
        for it in (apis.get('data', apis) or {}).get('items', []):
            if str(it.get('name') or '').startswith('接线测试_INT1486'):
                print('CLEAN api del', it.get('id'), api_req('DELETE', f"/api/v1/apis/{it['id']}", token))
        st, apis = api_req('GET', '/api/v1/apis?per_page=1000', token)
        print('RESIDUE apis', [(x.get('id'), x.get('name')) for x in (apis.get('data', apis) or {}).get('items', []) if '接线测试_INT1486' in (x.get('name') or '')])
        print('STATE', json.dumps(state, ensure_ascii=False))
    except Exception:
        traceback.print_exc()
        shot(d, 'C_error.png')
    finally:
        d.quit()


if __name__ == '__main__':
    main()
