# -*- coding: utf-8 -*-
"""INT-1433 验收（测试工程师）：REACT 建任务接入 case_devices（websocket_api Realtime
路由前置 + API/设备混跑 + 无 case_devices 零回归）。

环境：dev server 5333（临时 rsbuild 配置：/api/v1/apis → 契约 mock 5460，其余 → 真实库栈 5700）。
真实库栈 database=intelligent_audio_test（登录 接线测试_admin / JieXianTest@2026）。

验证点：
1. API 卡协议徽章按 deriveApiTargetDeviceType（显式 deviceType / 端点协议派生）——
   WS(9001)=Realtime WS、HTTP(9002)=HTTP API、AUTO-WS(9003,无显式 deviceType,wss 端点)=Realtime WS。
2. API 编辑弹窗「设备类型」select（自动/HTTP API/Realtime WS）+ auto 派生提示。
3. 选 websocket_api API + 用例建任务 → POST /tasks 请求体 case_devices 含
   {device_type:'websocket_api', device_id:'9001'}，逐用例展开。
4. 混跑（WS API + HTTP API + 物理设备）→ case_devices 同时含 physical/http_api/websocket_api。
5. 附图：浅色 + 深色。

写数据纪律：mock API 与任务名带「接线测试_INT1433_」前缀，run 结束前停 mock、清任务。
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
os.makedirs(ART, exist_ok=True)
SUFFIX = int(time.time())

# mock 合约里的三枚 API（见 mock_int1433_apis.py）
WS_API_NAME = '接线测试_INT1433_WS_mock'
HTTP_API_NAME = '接线测试_INT1433_HTTP_mock'
AUTO_WS_API_NAME = '接线测试_INT1433_AUTO_WS_mock'

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

RESULTS = []


def check(label, ok, detail=''):
    RESULTS.append((label, bool(ok), detail))
    print(('PASS' if ok else 'FAIL'), label, detail if detail else '')


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


def _body(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _shot(drv, name, theme='light'):
    d = os.path.join(ART, theme)
    os.makedirs(d, exist_ok=True)
    drv.save_screenshot(os.path.join(d, name + '.png'))
    print('saved', theme, name)


def js_click(drv, el):
    drv.execute_script('arguments[0].click()', el)


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
    check('登录跳转离开 /login', '/login' not in drv.current_url, drv.current_url)


def set_algorithm(drv):
    drv.execute_script(
        "localStorage.setItem('iatp:algorithm:v1', JSON.stringify({state:{algorithmId:'voice_llm'},version:0}));")


def set_theme(drv, mode):
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', '%s');" % mode)


def goto_step1(drv):
    drv.get(BASE + '/start-test?step=1')
    WebDriverWait(drv, 25).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(5)
    print('step1 url:', drv.current_url)


def api_card_badge(drv, api_name):
    """返回该 API 卡上类型徽章文本（Realtime WS / HTTP API）。"""
    try:
        span = WebDriverWait(drv, 10).until(
            EC.presence_of_element_located((By.XPATH, "//span[normalize-space(.)='%s']" % api_name)))
        card = span.find_element(By.XPATH, "./ancestor::div[contains(@class,'rounded-xl')][1]")
        return card.text
    except Exception:
        return None


def select_api_card(drv, api_name):
    chk = WebDriverWait(drv, 15).until(
        EC.presence_of_element_located(
            (By.XPATH, "//span[@role='checkbox' and @aria-label='选择 API %s']" % api_name)))
    js_click(drv, chk)
    time.sleep(0.6)


def select_device_card(drv, dev_name):
    chk = WebDriverWait(drv, 15).until(
        EC.presence_of_element_located(
            (By.XPATH, "//span[@role='checkbox' and @aria-label='选择设备 %s']" % dev_name)))
    js_click(drv, chk)
    time.sleep(0.6)


def open_api_edit_new(drv):
    btn = WebDriverWait(drv, 15).until(
        EC.element_to_be_clickable((By.XPATH, "//button[contains(normalize-space(.), '新增 API')]")))
    js_click(drv, btn)
    WebDriverWait(drv, 10).until(EC.presence_of_element_located((By.ID, 'api-name')))


def open_api_edit_existing(drv, api_name):
    span = WebDriverWait(drv, 15).until(
        EC.presence_of_element_located((By.XPATH, "//span[normalize-space(.)='%s']" % api_name)))
    card = span.find_element(By.XPATH, "./ancestor::div[contains(@class,'rounded-xl')][1]")
    more = card.find_element(By.XPATH, ".//button[@aria-label='更多操作']")
    js_click(drv, more)
    time.sleep(0.6)
    edit = WebDriverWait(drv, 8).until(
        EC.element_to_be_clickable((By.XPATH, "//*[@data-slot='dropdown-menu-item' and normalize-space(.)='编辑']")))
    js_click(drv, edit)
    WebDriverWait(drv, 10).until(EC.presence_of_element_located((By.ID, 'api-name')))


def dialog_device_type_value(drv):
    return drv.execute_script(
        "const ls = Array.from(document.querySelectorAll('div[role=dialog] label'));"
        "const l = ls.find(x => x.textContent.trim() === '设备类型');"
        "if (!l) return 'NO_LABEL';"
        "const f = l.parentElement;"
        "const tv = f.querySelector('[data-slot=select-value]');"
        "return tv ? tv.textContent.trim() : 'NO_VALUE';")


def dialog_device_type_hint(drv):
    return drv.execute_script(
        "const ls = Array.from(document.querySelectorAll('div[role=dialog] label'));"
        "const l = ls.find(x => x.textContent.trim() === '设备类型');"
        "if (!l) return 'NO_LABEL';"
        "const f = l.parentElement;"
        "const p = f.querySelector('p.text-muted-foreground');"
        "return p ? p.textContent.trim() : '';")


def start_test(drv, task_name=None):
    """点击底部开始测试 → 任务名称弹窗 → 填写任务名 → 开始测试。返回 True 若提交成功。"""
    try:
        footer_btn = WebDriverWait(drv, 15).until(
            EC.element_to_be_clickable((By.XPATH,
                "//button[contains(normalize-space(.), '开始测试') and not(ancestor::div[@role='dialog'])]")))
        js_click(drv, footer_btn)
    except Exception:
        print('footer 开始测试 not found; body:', _body(drv)[:200])
        return False
    try:
        name_in = WebDriverWait(drv, 12).until(
            EC.presence_of_element_located((By.XPATH,
                "//div[@role='dialog']//input[@id='task-name']")))
        if task_name:
            name_in.clear()
            name_in.send_keys(task_name)
    except Exception:
        print('task-name dialog not opened')
        toasts = [e.text for e in drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
        print('toasts:', json.dumps(toasts, ensure_ascii=False)[:300])
        return False
    try:
        go = WebDriverWait(drv, 12).until(
            EC.presence_of_element_located((By.XPATH,
                "//div[@role='dialog']//button[contains(normalize-space(.), '开始测试')]")))
    except Exception:
        toasts = [e.text for e in drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
        print('start-test dialog submit btn not found; toasts:', json.dumps(toasts, ensure_ascii=False)[:300])
        return False
    time.sleep(1)
    js_click(drv, go)
    time.sleep(5)
    return True


def read_fetch_log(drv):
    try:
        return drv.execute_script('return window.__fetchLog || []')
    except Exception:
        return None


def parse_task_bodies(drv):
    log = read_fetch_log(drv) or []
    bodies = []
    for item in log:
        b = item.get('body')
        try:
            bodies.append(json.loads(b))
        except Exception:
            bodies.append(None)
    return bodies


def device_test_name():
    """读取刚插入的真实库在线测试设备名（接线测试_INT1433_dev_*）。"""
    import urllib.request
    with urllib.request.urlopen('http://127.0.0.1:5700/health', timeout=8) as resp:
        health = json.loads(resp.read().decode())
    assert health.get('database') == 'intelligent_audio_test', '连到非主库，停！'
    import psycopg2
    conn = psycopg2.connect(host='localhost', port=15432, dbname='intelligent_audio_test',
                            user='intelligent_audio_test', password='intelligent_audio_test666')
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM devices WHERE name LIKE '接线测试_INT1433_dev_%%' AND deleted=false ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    conn.close()
    return row


def main():
    drv = _driver()
    try:
        login(drv)
        set_algorithm(drv)
        goto_step1(drv)

        # ===== 验证点 1：API 卡徽章（deriveApiTargetDeviceType） =====
        card_ws = api_card_badge(drv, WS_API_NAME)
        card_http = api_card_badge(drv, HTTP_API_NAME)
        card_auto = api_card_badge(drv, AUTO_WS_API_NAME)
        check('API 卡 WS(9001) 显示 Realtime WS 徽章', card_ws and 'Realtime WS' in card_ws, str(card_ws)[:120])
        check('API 卡 HTTP(9002) 显示 HTTP API 徽章', card_http and 'HTTP API' in card_http, str(card_http)[:120])
        check('API 卡 AUTO-WS(9003,无显式 deviceType,wss 端点) 派生 Realtime WS 徽章',
              card_auto and 'Realtime WS' in card_auto, str(card_auto)[:120])
        check('API 卡均在在线态', all(c and '在线' in c for c in [card_ws, card_http, card_auto]))
        _shot(drv, '01_api_cards_light', 'light')

        # ===== 验证点 2：API 编辑弹窗设备类型 select + auto 派生提示 =====
        open_api_edit_new(drv)
        time.sleep(1.5)
        _shot(drv, '02_api_edit_new_light', 'light')
        # 默认 auto：无端点 → 提示「未配置端点时缺省为 HTTP API」
        hint0 = dialog_device_type_hint(drv)
        dt_val = dialog_device_type_value(drv)
        check('编辑弹窗设备类型表单值=auto（缺省）', dt_val == 'auto', dt_val)
        # 已知 base-ui 怪癖（INT-922 发现）：闭合态显示原始 value 而非 label
        check('设备类型 select 闭合态显示选项名（非原始值）', dt_val in ('自动（按端点协议派生）', 'HTTP API', 'Realtime WS'),
              '闭合态显示: %r（应显示选项名，如「自动（按端点协议派生）」）' % dt_val)
        check('auto 无端点提示缺省 HTTP API', '缺省为 HTTP API' in hint0, hint0)
        # 填 wss 端点 → 提示「将按端点协议派生为：Realtime WS」
        name_in = drv.find_element(By.ID, 'api-name')
        name_in.send_keys('接线测试_INT1433_edit_%d' % SUFFIX)
        add = WebDriverWait(drv, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(normalize-space(.), '添加端点')]")))
        js_click(drv, add)
        ep = WebDriverWait(drv, 10).until(
            EC.presence_of_element_located((By.XPATH, "//input[@aria-label='端点 URL']")))
        ep.send_keys('wss://edit.example.com/ws')
        time.sleep(0.8)
        hint1 = dialog_device_type_hint(drv)
        check('auto+wss 端点提示派生为 Realtime WS', 'Realtime WS' in hint1, hint1)
        _shot(drv, '03_api_edit_wss_hint_light', 'light')
        # 关闭弹窗（取消）
        cancel = WebDriverWait(drv, 8).until(
            EC.element_to_be_clickable((By.XPATH, "//div[@role='dialog']//button[contains(normalize-space(.), '取消')]")))
        js_click(drv, cancel)
        time.sleep(1)

        # ===== 验证点 3：选 websocket_api API 建任务 → case_devices websocket_api =====
        select_api_card(drv, WS_API_NAME)
        started = start_test(drv, task_name='接线测试_INT1433_WS_%d' % SUFFIX)
        check('启动流程（WS API 单目标）打开任务名称弹窗并提交', started)
        bodies = parse_task_bodies(drv)
        ws_body = next((b for b in bodies if isinstance(b, dict) and b.get('case_devices')), None)
        if ws_body:
            cd = ws_body['case_devices']
            case_ids = ws_body.get('case_ids') or []
            types = {}
            for item in cd:
                types[item.get('device_type')] = types.get(item.get('device_type'), 0) + 1
            check('单 WS 目标：case_devices 全部 device_type=websocket_api',
                  all(item.get('device_type') == 'websocket_api' for item in cd), json.dumps(types, ensure_ascii=False))
            check('单 WS 目标：device_id=9001（API 自身 id 字符串化）',
                  all(item.get('device_id') == '9001' for item in cd),
                  str(cd[0]) if cd else 'EMPTY')
            check('单 WS 目标：case_devices 逐用例展开（数量==case_ids 数量）', len(cd) == len(case_ids),
                  'cd=%d case_ids=%d' % (len(cd), len(case_ids)))
            check('单 WS 目标：字段名与网关契约 TaskCaseDeviceAssignment 一致',
                  all(set(item.keys()) == {'case_id', 'device_type', 'device_id'} for item in cd),
                  str(cd[0]) if cd else 'EMPTY')
        else:
            check('单 WS 目标：捕获到 POST /tasks 请求体', False, json.dumps(bodies, ensure_ascii=False)[:200])
        print('POST /tasks captured:', len(bodies))

        # ===== 验证点 4：混跑 WS + HTTP + 物理设备 =====
        dev_row = device_test_name()
        check('真实库存在接线测试_INT1433 在线设备', dev_row is not None, str(dev_row))
        dev_id, dev_name = dev_row if dev_row else (None, 'NO_DEV')
        goto_step1(drv)
        time.sleep(4)
        select_api_card(drv, WS_API_NAME)
        select_api_card(drv, HTTP_API_NAME)
        select_api_card(drv, AUTO_WS_API_NAME)
        if dev_name != 'NO_DEV':
            select_device_card(drv, dev_name)
        _shot(drv, '04_mixed_selection_light', 'light')
        started2 = start_test(drv, task_name='接线测试_INT1433_mix_%d' % SUFFIX)
        check('混跑流程提交任务名称弹窗', started2)
        bodies2 = parse_task_bodies(drv)
        mix_body = next((b for b in bodies2 if isinstance(b, dict) and b.get('case_devices')), None)
        if mix_body:
            cd = mix_body['case_devices']
            types = {}
            dev_ids = {}
            for item in cd:
                t = item.get('device_type')
                types[t] = types.get(t, 0) + 1
                dev_ids.setdefault(t, set()).add(item.get('device_id'))
            check('混跑：case_devices 含 websocket_api / http_api / physical 三值',
                  types.get('websocket_api') and types.get('http_api') and types.get('physical'),
                  json.dumps(types, ensure_ascii=False))
            check('混跑：websocket_api 含显式 WS(9001) 与 AUTO-WS(9003) 派生目标',
                  dev_ids.get('websocket_api') == {'9001', '9003'},
                  str(sorted(dev_ids.get('websocket_api', []))))
            check('混跑：http_api 目标 device_id=9002', dev_ids.get('http_api') == {'9002'},
                  str(sorted(dev_ids.get('http_api', []))))
            check('混跑：AUTO-WS(9003) 按端点协议派生 websocket_api',
                  '9003' in dev_ids.get('websocket_api', set()),
                  str(sorted(dev_ids.get('websocket_api', []))))
            check('混跑：physical 目标 device_id=真实设备 id(%s)' % dev_id,
                  dev_ids.get('physical') == {str(dev_id)}, str(sorted(dev_ids.get('physical', []))))
        else:
            check('混跑：捕获到 POST /tasks 请求体', False, json.dumps(bodies2, ensure_ascii=False)[:300])

        # ===== 验证点 5：深色截图 + 已有 API 编辑回显 =====
        set_theme(drv, 'dark')
        goto_step1(drv)
        time.sleep(4)
        _shot(drv, '05_api_cards_dark', 'dark')
        try:
            open_api_edit_existing(drv, WS_API_NAME)
            time.sleep(1.5)
            val = dialog_device_type_value(drv)
            check('深色已有 API 编辑：deviceType 表单值=websocket_api（显式回填）', val == 'websocket_api', val)
            check('深色已有 API 编辑：deviceType 闭合态显示「Realtime WS」', val == 'Realtime WS',
                  '闭合态显示 %r（应显示 Realtime WS）' % val)
            _shot(drv, '06_api_edit_ws_dark', 'dark')
        except Exception as e:
            print('dark edit open failed:', e)
            check('深色已有 API 编辑弹窗打开', False, str(e)[:200])

        # 切回浅色
        set_theme(drv, 'light')

        errs = drv.execute_script('return (window.__iatpErrors || []).slice()')
        print('console.error count:', len(errs))
        for e in errs[:8]:
            print('  ERR:', e[:220])
        with open(os.path.join(ART, 'post_tasks_bodies.json'), 'w', encoding='utf-8') as f:
            json.dump(parse_task_bodies(drv), f, ensure_ascii=False, indent=2)
    finally:
        drv.quit()

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print('=' * 30)
    print('SUMMARY: %d/%d passed' % (passed, total))
    for label, ok, detail in RESULTS:
        if not ok:
            print('FAILED:', label, '|', detail)
    with open(os.path.join(ART, 'summary.txt'), 'w', encoding='utf-8') as f:
        for label, ok, detail in RESULTS:
            f.write('%s\t%s\t%s\n' % ('PASS' if ok else 'FAIL', label, detail))
    if passed != total:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
