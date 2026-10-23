# -*- coding: utf-8 -*-
"""INT-1495【修复·React·设备域】交付实测（React 接线 / 真实库栈）。

覆盖修复项：
  P2-1 实验室管理：入口解禁 + GET/POST/PUT/DELETE /laboratories 真实闭环 + mock 移除
  P2-2 安装/卸载应用：请求体带 params.file_path / params.package_name（Network 证据）
  P2-3 离线设备「删除」不再禁用
  P3-1 设备表单「端口」输入已移除（后端无 port 契约）
  P3-2 扫描结果行展示连接方式（真实扫描为空时用合成扫描响应验证渲染，标注 synthetic）

环境：dev server :5355（/api 代理 → 真实库栈网关 127.0.0.1:5700，AUTH_MODE=dev 登录）
测试数据：全部带「接线测试_INT1495_」前缀，脚本末尾删除并 API 复核零残留。
"""
import functools
import json
import os
import shutil
import sys
import time
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:5355')
GATEWAY = os.environ.get('REAL_GATEWAY', 'http://127.0.0.1:5700')
USER = '接线测试_admin'
PASSWORD = 'JieXianTest@2026'
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1495')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

LAB_NAME = '接线测试_INT1495_实验室'
LAB_CODE = 'JX1495LAB'
LAB_NAME2 = '接线测试_INT1495_实验室_改名'
LAB_BUILDING = '研发中心测试楼'
LAB_FLOOR = '5 层'
LAB_ROOM = '501'
LAB_DESC = 'INT-1495 设备域修复走查自建，验收后删除'
DEVICE_NAME = '接线测试_INT1495_测试设备'
DEVICE_SERIAL = 'JX1495SN01'

_FAILURES = []
_COMPARE = {}  # Network 证据汇总
print = functools.partial(print, flush=True)  # noqa: A001
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass


def _check(name, cond, detail=''):
    tag = 'PASS' if cond else 'FAIL'
    print(f'[{tag}] {name}' + (f' — {detail}' if detail else ''))
    if not cond:
        _FAILURES.append(name)


def _chromedriver():
    root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    cands = []
    if os.path.isdir(root):
        for ver in os.listdir(root):
            exe = os.path.join(root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
                except ValueError:
                    continue
    return max(cands)[1] if cands else ''


FETCH_PROBE_JS = """
    if (window.__reqlogInstalled) { window.__reqlog = []; }
    else {
      window.__reqlogInstalled = true;
      window.__reqlog = [];
      const of = window.fetch;
      window.fetch = function (input, init) {
        init = init || {};
        const url = typeof input === 'string' ? input : ((input && input.url) || '');
        const rec = {url: url, method: (init.method || 'GET').toUpperCase(),
                     body: typeof init.body === 'string' ? init.body : null};
        window.__reqlog.push(rec);
        return of.apply(this, arguments).then(function (r) {
          rec.status = r.status;
          try { r.clone().text().then(function (t) { rec.respText = t; }); } catch (e) {}
          return r;
        });
      };
    }
"""


def _driver():
    profile = os.path.join(os.environ.get('TEMP', '.'), 'int1495_chrome')
    shutil.rmtree(profile, ignore_errors=True)
    o = Options()
    o.binary_location = CHROME_BINARY
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1050')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--user-data-dir=' + profile)
    o.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    p = _chromedriver()
    d = webdriver.Chrome(options=o, service=Service(executable_path=p) if p else Service())
    d.set_page_load_timeout(45)
    d.set_script_timeout(180)
    # 注入到每个新文档：跨导航保留真实请求打点（Chrome 155 无 Network.setRequestInterception）
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PROBE_JS})
    return d


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 25).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _wait_text(drv, text, timeout=15):
    WebDriverWait(drv, timeout).until(
        lambda d: text in d.execute_script('return document.body.textContent || ""'))


def _js_click(drv, el):
    drv.execute_script('arguments[0].click()', el)
    time.sleep(0.5)


def _drain_logs(drv):
    try:
        drv.get_log('browser')
        drv.get_log('performance')
    except Exception:
        pass


def _install_fetch_probe(drv):
    """CDP 已对每个新文档注入打点；此处兜底（CDP 未生效时手动装）并清空本轮记录。"""
    drv.execute_script("""
        if (window.__reqlogInstalled) { window.__reqlog = []; return; }
        window.__reqlogInstalled = true;
        window.__reqlog = [];
        const of = window.fetch;
        window.fetch = function (input, init) {
          init = init || {};
          const url = typeof input === 'string' ? input : ((input && input.url) || '');
          const rec = {url: url, method: (init.method || 'GET').toUpperCase(),
                       body: typeof init.body === 'string' ? init.body : null};
          window.__reqlog.push(rec);
          return of.apply(this, arguments).then(function (r) {
            rec.status = r.status;
            try { r.clone().text().then(function (t) { rec.respText = t; }); } catch (e) {}
            return r;
          });
        };
    """)


def _reqlog(drv):
    return drv.execute_script('return window.__reqlog || []')


def _network(drv, needle):
    """performance log：method + url + status + postData（双层解包）。"""
    reqs, resp = {}, {}
    try:
        for entry in drv.get_log('performance'):
            inner = json.loads(entry['message']).get('message', {})
            ev, p = inner.get('method'), inner.get('params', {})
            if ev == 'Network.requestWillBeSent':
                r = p.get('request', {})
                reqs[p.get('requestId')] = (r.get('url', ''), r.get('method', ''),
                                            r.get('postData'))
            elif ev == 'Network.responseReceived':
                resp[p.get('requestId')] = p.get('response', {}).get('status')
    except Exception as e:
        return [{'error': str(e)}]
    out = []
    for rid, (url, method, post) in reqs.items():
        if needle in url:
            out.append({'url': url, 'method': method, 'status': resp.get(rid), 'postData': post})
    return out


def _page_fetch(drv, path, method='GET', body=None):
    return drv.execute_async_script("""
        const done = arguments[arguments.length - 1];
        const init = {method: arguments[1], headers: {}};
        const t = localStorage.getItem('iatp:auth:token:v1');
        if (t) init.headers['Authorization'] = 'Bearer ' + t;
        if (arguments[2] != null) {
          init.headers['Content-Type'] = 'application/json';
          init.body = JSON.stringify(arguments[2]);
        }
        fetch(arguments[0], init).then(async r => done({status: r.status, text: await r.text()}))
          .catch(e => done({status: 0, text: String(e)}));
    """, path, method, body)


def _api(drv, path, method='GET', body=None):
    r = _page_fetch(drv, path, method, body)
    try:
        return r['status'], json.loads(r['text'])
    except Exception:
        return r['status'], r['text']


def _health():
    try:
        with urllib.request.urlopen(f'{GATEWAY}/health', timeout=8) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception as e:
        return {'error': str(e)}


def _evidence(drv, name):
    d = os.path.join(ARTIFACTS, name)
    os.makedirs(d, exist_ok=True)
    try:
        drv.save_screenshot(os.path.join(d, 'screenshot.png'))
        with open(os.path.join(d, 'page_source.html'), 'w', encoding='utf-8') as f:
            f.write(drv.page_source)
        with open(os.path.join(d, 'console.log'), 'w', encoding='utf-8') as f:
            for entry in drv.get_log('browser'):
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except Exception as e:
        print('evidence error', name, e)
    return os.path.join(d, 'screenshot.png')


def _set_theme(drv, theme):
    drv.execute_script(
        "window.localStorage.setItem('iatp:theme:v1:mode', arguments[0])", theme)
    drv.refresh()
    WebDriverWait(drv, 25).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(2.0)
    _install_fetch_probe(drv)


def _open_header_more(drv):
    btn = drv.find_element(By.XPATH, "//button[@aria-label='更多操作']")
    _js_click(drv, btn)


def _menu_item(drv, label, timeout=10):
    def find(d):
        for it in d.find_elements(By.XPATH, "//*[@role='menuitem']"):
            if label in (it.text or ''):
                return it
        return False
    return WebDriverWait(drv, timeout).until(find)


def _item_disabled(el):
    return (el.get_attribute('data-disabled') is not None
            or el.get_attribute('aria-disabled') == 'true')


def _row_actions_button(drv, name_part=''):
    xp = f"//button[starts-with(@aria-label,'操作 ')]"
    elems = drv.find_elements(By.XPATH, xp)
    if name_part:
        for e in elems:
            if name_part in (e.get_attribute('aria-label') or ''):
                return e
    return elems[0] if elems else None


def _select_option(drv, trigger, label):
    _js_click(drv, trigger)
    time.sleep(0.5)
    for o in drv.find_elements(By.XPATH, "//*[@role='option']"):
        if label in (o.text or ''):
            _js_click(drv, o)
            return True
    return False


def _fill(drv, el_id, text):
    el = drv.find_element(By.ID, el_id)
    el.clear()
    el.send_keys(text)
    return el


def _click_button_text(drv, text, scope=None):
    root = scope or drv
    for b in root.find_elements(By.TAG_NAME, 'button'):
        if (b.text or '').strip() == text:
            _js_click(drv, b)
            return b
    return None


def _toast_text(drv, timeout=12):
    """sonner toast 文案（data-sonner-toast；默认 4s 自动消失，需及时读取）。"""
    def find(d):
        els = d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')
        txt = ' '.join((e.text or '') for e in els).strip()
        return txt or False
    try:
        return WebDriverWait(drv, timeout).until(find)
    except Exception:
        return ''


def _login(drv):
    _goto(drv, '/login')
    _wait_text(drv, '用户名或电子邮件', 20)
    _fill(drv, 'username', USER)
    _fill(drv, 'password', PASSWORD)
    _click_button_text(drv, '登 录')
    WebDriverWait(drv, 25).until(lambda d: '/login' not in d.current_url)
    time.sleep(2.5)
    _install_fetch_probe(drv)
    ok = drv.execute_script("return Boolean(localStorage.getItem('iatp:auth:token:v1'))")
    _check('登录真实库栈（AUTH_MODE=dev）', bool(ok), detail=drv.current_url)
    return ok


# ------------------------- 各步骤 -------------------------

def step_preflight(drv):
    h = _health()
    _COMPARE['health_start'] = h
    _check('真实库栈 /health database=intelligent_audio_test',
           h.get('database') == 'intelligent_audio_test', detail=json.dumps(h, ensure_ascii=False))
    st, d = _api(drv, '/api/v1/test-devices?page=1&per_page=1000')
    _COMPARE['devices_total_start'] = (d.get('data') or {}).get('total') if isinstance(d, dict) else d
    st2, d2 = _api(drv, '/api/v1/laboratories?page=1&per_page=1000')
    _COMPARE['labs_total_start'] = (d2.get('data') or {}).get('total') if isinstance(d2, dict) else d2
    _check('基线：GET /test-devices 200', st == 200, detail=str(_COMPARE['devices_total_start']))
    _check('基线：GET /laboratories 200（真实空列表）', st2 == 200,
           detail=f'total={_COMPARE["labs_total_start"]}')


def step_lab_entry(drv):
    _goto(drv, '/devices/test')
    _wait_text(drv, '设备管理', 25)
    _drain_logs(drv)
    _open_header_more(drv)
    item = _menu_item(drv, '实验室管理')
    _check('P2-1 更多操作→实验室管理 存在', item is not None)
    _check('P2-1 实验室管理入口不再禁用', not _item_disabled(item),
           detail=f'data-disabled={item.get_attribute("data-disabled")}')
    _js_click(drv, item)
    _wait_text(drv, '管理物理实验室及其资源归属', 15)
    _check('P2-1 实验室管理弹窗可达', '实验室管理' in _body_text(drv))
    time.sleep(1.5)
    net = [r for r in _reqlog(drv)
           if r['method'] == 'GET' and r['url'].startswith('/api/v1/laboratories')]
    _COMPARE['labs_get'] = net
    _check('P2-1 页面/弹窗加载触发真实 GET /laboratories', bool(net),
           detail=json.dumps(net, ensure_ascii=False))
    _check('P2-1 GET /laboratories 返回 200', bool(net) and net[-1].get('status') == 200,
           detail=json.dumps(net[-1] if net else {}, ensure_ascii=False))
    _evidence(drv, 'p21_lab_dialog_open_light')


def step_lab_crud(drv):
    # 新建
    _fill(drv, 'lab-name', LAB_NAME)
    _fill(drv, 'lab-code', LAB_CODE)
    _fill(drv, 'lab-building', LAB_BUILDING)
    _fill(drv, 'lab-floor', LAB_FLOOR)
    _fill(drv, 'lab-room', LAB_ROOM)
    _fill(drv, 'lab-desc', LAB_DESC)
    _js_click(drv, drv.find_element(By.XPATH, "//button[normalize-space(.)='新建实验室']"))
    # 真实库实验室列表含 test_case_count gRPC 聚合，刷新约 15s（本 run 实测），等待放宽
    _wait_text(drv, LAB_NAME, 60)
    time.sleep(1.5)
    st, d = _api(drv, '/api/v1/laboratories?page=1&per_page=1000')
    items = (d.get('data') or {}).get('items', []) if isinstance(d, dict) else []
    lab = next((x for x in items if x.get('code') == LAB_CODE), None)
    _check('P2-1 新建实验室落库（GET 回读）', lab is not None, detail=json.dumps(lab, ensure_ascii=False))
    if lab:
        _check('P2-1 新建回读字段一致',
               all([lab.get('name') == LAB_NAME, lab.get('building') == LAB_BUILDING,
                    lab.get('floor') == LAB_FLOOR, lab.get('room_number') == LAB_ROOM,
                    lab.get('description') == LAB_DESC, lab.get('status') == 'active']),
               detail=json.dumps(lab, ensure_ascii=False))
    _COMPARE['lab_created'] = lab
    _COMPARE['lab_posts'] = [r for r in _reqlog(drv)
                             if r['method'] == 'POST' and r['url'].endswith('/laboratories')]
    _evidence(drv, 'p21_lab_created_light')

    # 编辑：先核对回显
    _js_click(drv, drv.find_element(By.XPATH, f"//button[@aria-label='编辑实验室 {LAB_NAME}']"))
    time.sleep(0.8)
    echo = {k: drv.find_element(By.ID, k).get_attribute('value')
            for k in ['lab-name', 'lab-code', 'lab-building', 'lab-floor', 'lab-room', 'lab-desc']}
    _check('P2-1 编辑回显全部字段',
           echo['lab-name'] == LAB_NAME and echo['lab-code'] == LAB_CODE
           and echo['lab-building'] == LAB_BUILDING and echo['lab-floor'] == LAB_FLOOR
           and echo['lab-room'] == LAB_ROOM and echo['lab-desc'] == LAB_DESC,
           detail=json.dumps(echo, ensure_ascii=False))
    _fill(drv, 'lab-name', LAB_NAME2)
    _fill(drv, 'lab-floor', '6 层')
    _select_option(drv, drv.find_element(By.ID, 'lab-status'), '维护中')
    _js_click(drv, drv.find_element(By.XPATH, "//button[normalize-space(.)='保存修改']"))
    _wait_text(drv, LAB_NAME2, 60)
    time.sleep(1.5)
    st, d = _api(drv, '/api/v1/laboratories?page=1&per_page=1000')
    items = (d.get('data') or {}).get('items', []) if isinstance(d, dict) else []
    lab2 = next((x for x in items if x.get('code') == LAB_CODE), None)
    _check('P2-1 编辑保存回读（名称/楼层/状态）',
           bool(lab2) and lab2.get('name') == LAB_NAME2 and lab2.get('floor') == '6 层'
           and lab2.get('status') == 'maintenance',
           detail=json.dumps(lab2, ensure_ascii=False))
    _COMPARE['lab_updated'] = lab2
    _COMPARE['lab_posts'] = _COMPARE.get('lab_posts', []) + [
        r for r in _reqlog(drv) if r['method'] == 'PUT' and '/laboratories/' in r['url']]
    _wait_text(drv, LAB_NAME2, 10)
    _evidence(drv, 'p21_lab_updated_light')
    return lab


def step_device_delete_enabled(drv):
    """P2-3：离线设备行「删除」不再禁用（点开确认后取消，不动真实记录）。"""
    _goto(drv, '/devices/test')
    _wait_text(drv, '设备管理', 20)
    time.sleep(1.5)
    btn = _row_actions_button(drv)
    _check('P2-3 存在设备行操作菜单', btn is not None)
    if not btn:
        return
    _check('P2-3 目标行为离线设备',
           '接线测试_INT1495' in (btn.get_attribute('aria-label') or '')
           or '离线' in _body_text(drv), detail=btn.get_attribute('aria-label'))
    _js_click(drv, btn)
    item = _menu_item(drv, '删除')
    _check('P2-3 离线设备「删除」菜单项未禁用', not _item_disabled(item),
           detail=f'data-disabled={item.get_attribute("data-disabled")} aria-disabled={item.get_attribute("aria-disabled")}')
    _js_click(drv, item)
    _wait_text(drv, '删除设备', 10)
    _check('P2-3 删除确认弹窗可达', '确定要删除' in _body_text(drv))
    _evidence(drv, 'p23_delete_confirm_light')
    _click_button_text(drv, '取消')
    time.sleep(0.6)


def step_port_removed(drv):
    """P3-1：表单无「端口」输入；远程连接仅有 IP。"""
    _click_button_text(drv, '添加测试设备')
    _wait_text(drv, '连接方式', 10)
    time.sleep(0.8)
    labels = [e.text or '' for e in drv.find_elements(By.TAG_NAME, 'label')]
    _check('P3-1 设备表单无「端口」输入', not any('端口' in t for t in labels),
           detail=f'labels={labels[:20]}')
    trig = drv.find_element(
        By.XPATH, "//label[contains(normalize-space(.),'连接方式')]/following-sibling::button[@role='combobox']")
    _check('P3-1 连接方式下拉可选远程', _select_option(drv, trig, '远程连接'))
    time.sleep(0.6)
    has_ip = len(drv.find_elements(By.XPATH, "//input[@placeholder='192.168.x.x']")) > 0
    labels2 = [e.text or '' for e in drv.find_elements(By.TAG_NAME, 'label')]
    _check('P3-1 远程连接下仅 IP 地址（无端口）',
           has_ip and not any('端口' in t for t in labels2), detail=f'labels={labels2[:20]}')
    _evidence(drv, 'p31_drawer_remote_no_port_light')
    _click_button_text(drv, '取消')
    time.sleep(0.8)


def step_install_request(drv, device_id):
    """P2-2：安装/卸载请求体带 params。"""
    # 置为在线（后端 PUT 真实落库），让菜单项可用
    st, _ = _api(drv, f'/api/v1/test-devices/{device_id}', 'PUT', {'status': 'online'})
    _check('P2-2 前置：测试设备置在线（PUT status=online）', st == 200, detail=str(st))
    _goto(drv, '/devices/test')
    _wait_text(drv, DEVICE_NAME, 20)
    time.sleep(2)
    btn = _row_actions_button(drv, DEVICE_NAME)
    _check('P2-2 行操作菜单命中自建设备', btn is not None)
    _js_click(drv, btn)
    item = _menu_item(drv, '安装应用')
    _check('P2-2 在线设备「安装应用」可用', not _item_disabled(item))
    _js_click(drv, item)
    _wait_text(drv, '应用安装包路径', 10)
    _fill(drv, 'op-file-path', '/sdcard/jx1495.apk')
    _fill(drv, 'op-package', 'com.jx.int1495')
    drv.execute_script('window.__reqlog = []')
    _drain_logs(drv)
    _click_button_text(drv, '执行安装')
    toast_text = _toast_text(drv, 15)
    _evidence(drv, 'p22_install_request_light')
    time.sleep(1.0)
    logs = [r for r in _reqlog(drv) if 'install-app' in r['url']]
    _COMPARE['install_req'] = logs
    body = logs[0]['body'] if logs else None
    _check('P2-2 安装发起真实 POST /test-devices/{id}/install-app', bool(logs),
           detail=json.dumps(logs, ensure_ascii=False))
    try:
        parsed = json.loads(body or '{}')
    except Exception:
        parsed = {}
    _check('P2-2 安装请求体含 params.file_path',
           (parsed.get('params') or {}).get('file_path') == '/sdcard/jx1495.apk', detail=str(body))
    _check('P2-2 安装请求体含 params.package_name',
           (parsed.get('params') or {}).get('package_name') == 'com.jx.int1495', detail=str(body))
    # toast 与真实响应一致：2xx → 发起安装文案；4xx → 后端 message 原样呈现
    resp = logs[0].get('respText') if logs else ''
    status_code = logs[0].get('status') if logs else None
    backend_msg = ''
    try:
        backend_msg = (json.loads(resp or '{}') or {}).get('message') or ''
    except Exception:
        backend_msg = ''
    if status_code and status_code < 300:
        _check('P2-2 安装 toast 与真实请求一致（成功）', '已发起安装' in toast_text,
               detail=toast_text)
    else:
        hint = backend_msg.split(' (code=')[0] if backend_msg else '命令执行失败'
        _check('P2-2 安装 toast 与真实请求一致（呈现后端失败文案）',
               bool(hint) and hint in toast_text, detail=f'hint={hint!r} toast={toast_text!r}')
    _COMPARE['install_resp'] = resp

    # 卸载
    time.sleep(1.0)
    btn = _row_actions_button(drv, DEVICE_NAME)
    _js_click(drv, btn)
    item = _menu_item(drv, '卸载应用')
    _js_click(drv, item)
    _wait_text(drv, '应用包名', 10)
    _fill(drv, 'op-uninstall-package', 'com.jx.int1495')
    drv.execute_script('window.__reqlog = []')
    _click_button_text(drv, '执行卸载')
    toast_text = _toast_text(drv, 15)
    _evidence(drv, 'p22_uninstall_request_light')
    time.sleep(1.0)
    logs = [r for r in _reqlog(drv) if 'uninstall-app' in r['url']]
    _COMPARE['uninstall_req'] = logs
    body = logs[0]['body'] if logs else None
    try:
        parsed = json.loads(body or '{}')
    except Exception:
        parsed = {}
    _check('P2-2 卸载发起真实 POST /test-devices/{id}/uninstall-app', bool(logs),
           detail=json.dumps(logs, ensure_ascii=False))
    _check('P2-2 卸载请求体含 params.package_name',
           (parsed.get('params') or {}).get('package_name') == 'com.jx.int1495', detail=str(body))
    _check('P2-2 卸载请求体不带 file_path',
           'file_path' not in (parsed.get('params') or {}), detail=str(body))
    resp = logs[0].get('respText') if logs else ''
    try:
        backend_msg = (json.loads(resp or '{}') or {}).get('message') or ''
    except Exception:
        backend_msg = ''
    hint = backend_msg.split(' (code=')[0] if backend_msg else '命令执行失败'
    _check('P2-2 卸载 toast 呈现真实后端结果',
           ('已发起卸载' in toast_text) or (bool(hint) and hint in toast_text),
           detail=f'hint={hint!r} toast={toast_text!r}')


def _open_scan_dialog(drv):
    _goto(drv, '/devices/test')
    _wait_text(drv, '设备管理', 20)
    _open_header_more(drv)
    _js_click(drv, _menu_item(drv, '扫描设备'))
    _wait_text(drv, '扫描测试设备', 10)
    time.sleep(5)  # 自动扫描 + 进度条走完


def step_scan_connection(drv):
    """P3-2：扫描行展示连接方式。真实扫描为空时用合成响应验证渲染（标注）。"""
    _open_scan_dialog(drv)
    dialog = drv.find_element(By.XPATH, "//*[@role='dialog']")
    dialog_text = dialog.text or ''
    _evidence(drv, 'p32_scan_dialog_real_empty')
    if 'USB连接' in dialog_text or '远程连接' in dialog_text:
        _check('P3-2 真实扫描行展示连接方式', True, detail=dialog_text[-200:])
        return
    print('[INFO] 真实扫描 0 行（本机 ADB 无设备，后端返回空列表），改用合成扫描响应验证渲染')
    # 合成响应（仅验证渲染，不改源码/不落库）
    drv.execute_script("""
        const syn = {success:true, code:0, message:'Success', data:[
          {serial:'JX1495-USB', model:'INT1495 Model', system:'Android', status:'online',
           name:'Android INT1495 Model', type:'phone', system_version:'13',
           app_name:'Default App', app_version:'1.0.0', ip:''},
          {serial:'192.168.1.20:5555', model:'INT1495 Remote', system:'Android', status:'online',
           name:'Android INT1495 Remote', type:'phone', system_version:'13',
           app_name:'Default App', app_version:'1.0.0', ip:'192.168.1.20'}
        ]};
        const of = window.fetch;
        window.fetch = function (input, init) {
          const url = typeof input === 'string' ? input : ((input && input.url) || '');
          if (url.indexOf('/test-devices/scan') >= 0) {
            return Promise.resolve(new Response(JSON.stringify(syn),
              {status: 200, headers: {'Content-Type': 'application/json'}}));
          }
          return of.apply(this, arguments);
        };
        window.__synthScan = true;
    """)
    btn = None
    for b in drv.find_elements(By.TAG_NAME, 'button'):
        if (b.text or '').strip() == '开始扫描':
            btn = b
    _check('P3-2 扫描弹窗「开始扫描」可点（非扫描中）',
           btn is not None and btn.get_attribute('disabled') is None)
    if btn:
        _js_click(drv, btn)
    WebDriverWait(drv, 25).until(
        lambda d: 'INT1495 Model' in d.execute_script('return document.body.textContent || ""'))
    dialog_text = drv.find_element(By.XPATH, "//*[@role='dialog']").text or ''
    _check('P3-2 扫描行展示 USB连接', 'JX1495-USB · USB连接' in dialog_text,
           detail=dialog_text[-260:])
    _check('P3-2 扫描行展示 远程连接（host:port 序列号）',
           '192.168.1.20:5555 · 远程连接' in dialog_text, detail=dialog_text[-260:])
    _evidence(drv, 'p32_scan_connection_synthetic')
    _click_button_text(drv, '取消')


def step_screenshots_dark(drv):
    _set_theme(drv, 'dark')
    _goto(drv, '/devices/test')
    _wait_text(drv, '设备管理', 20)
    time.sleep(1.5)
    _evidence(drv, 'devices_page_dark')
    _open_header_more(drv)
    _js_click(drv, _menu_item(drv, '实验室管理'))
    _wait_text(drv, '管理物理实验室及其资源归属', 15)
    time.sleep(1.5)
    _evidence(drv, 'p21_lab_dialog_dark')
    _click_button_text(drv, '关闭')
    _set_theme(drv, 'light')
    _goto(drv, '/devices/test')
    _wait_text(drv, '设备管理', 20)
    time.sleep(1.5)
    _evidence(drv, 'devices_page_light')


def step_network_snapshot(drv):
    """把本 run 捕获的真实请求渲染成表并截图（Network 证据）。"""
    rows = []
    for k in ('labs_get', 'install_req', 'uninstall_req'):
        for r in _COMPARE.get(k) or []:
            rows.append(r)
    for r in _COMPARE.get('lab_posts') or []:
        rows.append(r)
    if not rows:
        rows = [{'url': 'no captured request', 'method': '', 'status': '', 'body': ''}]
    html_rows = ''.join(
        f"<tr><td>{r.get('method','')}</td><td class='u'>{r.get('url','')}</td>"
        f"<td>{r.get('status','')}</td><td class='b'>{json.dumps(r.get('body') or r.get('postData'), ensure_ascii=False)}</td></tr>"
        for r in rows)
    html = f"""<!doctype html><meta charset="utf-8"><style>
    body{{font-family:Consolas,monospace;background:#0f1720;color:#e6edf3;padding:16px}}
    h3{{font-family:system-ui;margin:0 0 12px}}
    table{{border-collapse:collapse;width:100%;font-size:12px}}
    th,td{{border:1px solid #2d3b4a;padding:6px 8px;vertical-align:top;text-align:left}}
    th{{background:#1b2836}} .u{{color:#7cc4ff;word-break:break-all}}
    .b{{color:#a5d6a7;word-break:break-all;max-width:520px}}</style>
    <h3>INT-1495 Network 证据（真实库栈 5700，dev server 5355 代理）</h3>
    <table><tr><th>Method</th><th>URL</th><th>Status</th><th>Body / postData</th></tr>{html_rows}</table>"""
    path = os.path.join(ARTIFACTS, 'network_int1495.html')
    os.makedirs(ARTIFACTS, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)
    drv.get('file:///' + path.replace('\\', '/'))
    time.sleep(1.2)
    drv.save_screenshot(os.path.join(ARTIFACTS, 'p_network_evidence.png'))
    # 回到应用域（file:// 下无法再发 /api 请求，清理步骤要用应用域 fetch）
    _goto(drv, '/devices/test')
    _wait_text(drv, '设备管理', 20)


def step_cleanup(drv, device_id, lab):
    """删除本 run 自建数据并复核零残留。"""
    if lab:
        st, _ = _api(drv, f"/api/v1/laboratories/{lab['id']}", 'DELETE')
        _check('清理：DELETE /laboratories/{id}', st in (200, 204), detail=str(st))
    if device_id:
        st, _ = _api(drv, f'/api/v1/test-devices/{device_id}', 'DELETE')
        _check('清理：DELETE /test-devices/{id}', st in (200, 204), detail=str(st))
    st, d = _api(drv, '/api/v1/laboratories?page=1&per_page=1000')
    codes = [x.get('code') for x in ((d.get('data') or {}).get('items', []) if isinstance(d, dict) else [])]
    _check('清理：实验室零残留', LAB_CODE not in codes, detail=str(codes))
    st, d = _api(drv, '/api/v1/test-devices?page=1&per_page=1000')
    names = [x.get('name') for x in ((d.get('data') or {}).get('items', []) if isinstance(d, dict) else [])]
    _check('清理：测试设备零残留', DEVICE_NAME not in names, detail=str(names))


def _purge_leftovers(drv):
    """清理本卡历次中断 run 的自建数据（代码/名称带 INT1495 前缀）。"""
    removed = []
    st, d = _api(drv, '/api/v1/laboratories?page=1&per_page=200')
    items = (d.get('data') or {}).get('items', []) if isinstance(d, dict) else []
    for x in items:
        if str(x.get('code') or '').startswith('JX1495'):
            st2, _ = _api(drv, f"/api/v1/laboratories/{x['id']}", 'DELETE')
            removed.append(('lab', x.get('code'), st2))
    st, d = _api(drv, '/api/v1/test-devices?page=1&per_page=1000')
    items = (d.get('data') or {}).get('items', []) if isinstance(d, dict) else []
    for x in items:
        if str(x.get('name') or '').startswith('接线测试_INT1495'):
            st2, _ = _api(drv, f"/api/v1/test-devices/{x['id']}", 'DELETE')
            removed.append(('device', x.get('name'), st2))
    if removed:
        print('[INFO] 清理历史自建数据:', removed)
    return removed


def main():
    os.makedirs(ARTIFACTS, exist_ok=True)
    drv = _driver()
    lab = None
    device_id = None
    try:
        if not _login(drv):
            return 1
        _purge_leftovers(drv)
        step_preflight(drv)

        # 自建测试设备（P2-2/P2-3 载体）
        st, d = _api(drv, '/api/v1/test-devices', 'POST', {
            'name': DEVICE_NAME, 'model': 'INT1495-M', 'type': 'physical', 'system': 'Android',
            'system_version': '13', 'app_name': 'INT1495 App', 'app_version': '1.0.0',
            'status': 'offline', 'serial_number': DEVICE_SERIAL, 'connection_type': 'usb',
        })
        _check('前置：自建测试设备（接线测试_INT1495_）', st in (200, 201), detail=str(d)[:200])
        st, d = _api(drv, '/api/v1/test-devices?page=1&per_page=1000')
        items = (d.get('data') or {}).get('items', []) if isinstance(d, dict) else []
        dev = next((x for x in items if x.get('name') == DEVICE_NAME), None)
        device_id = dev.get('id') if dev else None
        _check('前置：自建设备可回读', device_id is not None, detail=str(device_id))

        step_lab_entry(drv)
        lab = step_lab_crud(drv)
        step_device_delete_enabled(drv)
        step_port_removed(drv)
        if device_id:
            step_install_request(drv, device_id)
        step_scan_connection(drv)

        # 第二次库名核对（截图前）
        h = _health()
        _COMPARE['health_before_shots'] = h
        _check('截图前 /health 仍为 intelligent_audio_test',
               h.get('database') == 'intelligent_audio_test', detail=json.dumps(h, ensure_ascii=False))
        step_screenshots_dark(drv)
        step_network_snapshot(drv)

        # 第三次库名核对（交付前）
        h = _health()
        _COMPARE['health_before_delivery'] = h
        _check('交付前 /health 仍为 intelligent_audio_test',
               h.get('database') == 'intelligent_audio_test', detail=json.dumps(h, ensure_ascii=False))

        step_cleanup(drv, device_id, lab)
        with open(os.path.join(ARTIFACTS, 'summary.json'), 'w', encoding='utf-8') as f:
            json.dump(_COMPARE, f, ensure_ascii=False, indent=2, default=str)
    finally:
        try:
            drv.quit()
        except Exception:
            pass

    print('\n==== RESULT ====')
    print('FAILURES:', _FAILURES if _FAILURES else 'none')
    return 0 if not _FAILURES else 1


if __name__ == '__main__':
    sys.exit(main())
