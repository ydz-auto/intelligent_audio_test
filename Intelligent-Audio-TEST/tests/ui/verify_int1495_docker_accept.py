# -*- coding: utf-8 -*-
"""INT-1495 验收（测试工程师独立复测；docker 真实栈 后端 15000 / 旁路前端 15495）。

旁路容器 iat-react-int1495-verify 由本卡交付分支 agent/react-b/int-1495 构建（600a…），
nginx /api/ → api_gateway:5000（容器网络 intelligent-audio-test_default），
与 15173（wiring/react 旧镜像，无本卡修复）构成 A/B 对照。

覆盖：
  P2-1 实验室管理：入口解禁 + 真实 /laboratories CRUD + mock 移除
  P2-2 安装/卸载应用：请求体 params.file_path / params.package_name
  P2-3 离线设备「删除」不再禁用
  P3-1 设备表单「端口」已移除
  P3-2 扫描结果行展示连接方式（真实扫描 0 行时用合成响应，标注 synthetic）
  P2-4（补充门禁项）告警面板历史统计图表不得静默展示 mock

测试数据：全部「接线测试_INT1495V_」前缀，脚本末尾删除并复核零残留。
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

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15495')
GATEWAY = os.environ.get('DOCKER_GATEWAY', 'http://127.0.0.1:15000')
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1495_accept')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

SUF = time.strftime('%H%M%S')
LAB_NAME = f'接线测试_INT1495V_实验室_{SUF}'
LAB_CODE = f'JX1495V{SUF}'
LAB_NAME2 = LAB_NAME + '_改名'
LAB_BUILDING = '研发中心验收楼'
LAB_FLOOR = '5 层'
LAB_ROOM = '501'
LAB_DESC = 'INT-1495 验收自建，验收后删除'
DEVICE_NAME = f'接线测试_INT1495V_测试设备_{SUF}'
DEVICE_SERIAL = f'JX1495V{SUF}'

_FAILURES = []
_COMPARE = {}
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
                cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
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


def _driver(tag='int1495_accept'):
    profile = os.path.join(os.environ.get('TEMP', '.'), tag + '_chrome')
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
    drv.execute_script(FETCH_PROBE_JS)


def _reqlog(drv):
    return drv.execute_script('return window.__reqlog || []')


def _network(drv, needle):
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
    return [{'url': u, 'method': m, 'status': resp.get(rid), 'postData': post}
            for rid, (u, m, post) in reqs.items() if needle in u]


def _page_fetch(drv, path, method='GET', body=None):
    return drv.execute_async_script("""
        const done = arguments[arguments.length - 1];
        const init = {method: arguments[1], headers: {}};
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


def _evidence(drv, name, shot=True):
    d = os.path.join(ARTIFACTS, name)
    os.makedirs(d, exist_ok=True)
    try:
        if shot:
            drv.save_screenshot(os.path.join(d, 'screenshot.png'))
        with open(os.path.join(d, 'page_source.html'), 'w', encoding='utf-8') as f:
            f.write(drv.page_source)
        with open(os.path.join(d, 'text.txt'), 'w', encoding='utf-8') as f:
            f.write(_body_text(drv))
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
    return (el.get_attribute('data-disabled') not in (None, 'false', 'False')
            or el.get_attribute('aria-disabled') == 'true')


def _row_actions_button(drv, name_part=''):
    elems = drv.find_elements(By.XPATH, "//button[starts-with(@aria-label,'操作 ')]")
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
    def find(d):
        els = d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')
        txt = ' '.join((e.text or '') for e in els).strip()
        return txt or False
    try:
        return WebDriverWait(drv, timeout).until(find)
    except Exception:
        return ''


# ------------------------- steps -------------------------

def step_preflight(drv):
    _goto(drv, '/devices/test')
    _wait_text(drv, '设备管理', 25)
    h = _health()
    _COMPARE['health'] = h
    _check('旁路前端 :15495 可用（本卡分支构建）', True)
    _check('后端 /health database=intelligent_audio_test',
           h.get('database') == 'intelligent_audio_test', detail=json.dumps(h, ensure_ascii=False))
    st, d = _api(drv, '/api/v1/test-devices?page=1&per_page=1000')
    _check('基线 GET /test-devices 200', st == 200, detail=str(st))
    st2, d2 = _api(drv, '/api/v1/laboratories?page=1&per_page=1000')
    items = (d2.get('data') or {}).get('items', []) if isinstance(d2, dict) else []
    _COMPARE['labs_baseline'] = items
    _check('基线 GET /laboratories 200', st2 == 200, detail=f'total={len(items)}')


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
    _wait_text(drv, '管理物理实验室及其资源归属', 20)
    _check('P2-1 实验室管理弹窗可达', '实验室管理' in _body_text(drv))
    time.sleep(2.0)
    net = [r for r in _reqlog(drv)
           if r['method'] == 'GET' and r['url'].startswith('/api/v1/laboratories')]
    _COMPARE['labs_get'] = net
    _check('P2-1 弹窗加载触发真实 GET /laboratories', bool(net),
           detail=json.dumps(net, ensure_ascii=False)[:400])
    _check('P2-1 GET /laboratories 200', bool(net) and net[-1].get('status') == 200,
           detail=json.dumps(net[-1] if net else {}, ensure_ascii=False)[:300])
    _evidence(drv, 'p21_lab_dialog_light')


def step_lab_crud(drv):
    _fill(drv, 'lab-name', LAB_NAME)
    _fill(drv, 'lab-code', LAB_CODE)
    _fill(drv, 'lab-building', LAB_BUILDING)
    _fill(drv, 'lab-floor', LAB_FLOOR)
    _fill(drv, 'lab-room', LAB_ROOM)
    _fill(drv, 'lab-desc', LAB_DESC)
    drv.execute_script('window.__reqlog = []')
    _js_click(drv, drv.find_element(By.XPATH, "//button[normalize-space(.)='新建实验室']"))
    _wait_text(drv, LAB_NAME, 90)
    time.sleep(1.5)
    posts = [r for r in _reqlog(drv)
             if r['method'] == 'POST' and r['url'].endswith('/laboratories')]
    _COMPARE['lab_posts'] = posts
    _check('P2-1 新建发起真实 POST /laboratories 2xx',
           bool(posts) and (posts[0].get('status') or 0) < 300,
           detail=json.dumps(posts, ensure_ascii=False)[:400])
    st, d = _api(drv, '/api/v1/laboratories?page=1&per_page=1000')
    items = (d.get('data') or {}).get('items', []) if isinstance(d, dict) else []
    lab = next((x for x in items if x.get('code') == LAB_CODE), None)
    _check('P2-1 新建实验室落库（GET 回读）', lab is not None,
           detail=json.dumps(lab, ensure_ascii=False)[:400])
    if lab:
        _check('P2-1 新建回读字段一致',
               all([lab.get('name') == LAB_NAME, lab.get('building') == LAB_BUILDING,
                    lab.get('floor') == LAB_FLOOR, lab.get('room_number') == LAB_ROOM,
                    lab.get('description') == LAB_DESC, lab.get('status') == 'active']),
               detail=json.dumps(lab, ensure_ascii=False)[:400])
    _COMPARE['lab_created'] = lab
    _evidence(drv, 'p21_lab_created_light')

    _js_click(drv, drv.find_element(By.XPATH, f"//button[@aria-label='编辑实验室 {LAB_NAME}']"))
    time.sleep(1.0)
    echo = {k: drv.find_element(By.ID, k).get_attribute('value')
            for k in ['lab-name', 'lab-code', 'lab-building', 'lab-floor', 'lab-room', 'lab-desc']}
    _check('P2-1 编辑回显全部字段',
           echo['lab-name'] == LAB_NAME and echo['lab-code'] == LAB_CODE
           and echo['lab-building'] == LAB_BUILDING and echo['lab-floor'] == LAB_FLOOR
           and echo['lab-room'] == LAB_ROOM and echo['lab-desc'] == LAB_DESC,
           detail=json.dumps(echo, ensure_ascii=False)[:400])
    _fill(drv, 'lab-name', LAB_NAME2)
    _fill(drv, 'lab-floor', '6 层')
    _select_option(drv, drv.find_element(By.ID, 'lab-status'), '维护中')
    drv.execute_script('window.__reqlog = []')
    _js_click(drv, drv.find_element(By.XPATH, "//button[normalize-space(.)='保存修改']"))
    _wait_text(drv, LAB_NAME2, 90)
    time.sleep(1.5)
    puts = [r for r in _reqlog(drv) if r['method'] == 'PUT' and '/laboratories/' in r['url']]
    _COMPARE['lab_puts'] = puts
    _check('P2-1 编辑发起真实 PUT /laboratories/{id}',
           bool(puts) and (puts[0].get('status') or 0) < 300,
           detail=json.dumps(puts, ensure_ascii=False)[:400])
    st, d = _api(drv, '/api/v1/laboratories?page=1&per_page=1000')
    items = (d.get('data') or {}).get('items', []) if isinstance(d, dict) else []
    lab2 = next((x for x in items if x.get('code') == LAB_CODE), None)
    _check('P2-1 编辑保存回读（名称/楼层/状态）',
           bool(lab2) and lab2.get('name') == LAB_NAME2 and lab2.get('floor') == '6 层'
           and lab2.get('status') == 'maintenance',
           detail=json.dumps(lab2, ensure_ascii=False)[:400])
    _COMPARE['lab_updated'] = lab2
    _evidence(drv, 'p21_lab_updated_light')
    return lab


def step_lab_delete(drv, lab):
    if not lab:
        _check('P2-1 删除：无自建实验室可删（前置失败）', False)
        return
    drv.execute_script('window.__reqlog = []')
    _js_click(drv, drv.find_element(By.XPATH, f"//button[@aria-label='删除实验室 {LAB_NAME2}']"))
    time.sleep(1.0)
    _click_button_text(drv, '删除')
    WebDriverWait(drv, 90).until(lambda d: LAB_NAME2 not in _body_text(d))
    time.sleep(1.5)
    dels = [r for r in _reqlog(drv) if r['method'] == 'DELETE' and '/laboratories/' in r['url']]
    _COMPARE['lab_deletes'] = dels
    _check('P2-1 删除发起真实 DELETE /laboratories/{id}',
           bool(dels) and (dels[0].get('status') or 0) < 300,
           detail=json.dumps(dels, ensure_ascii=False)[:300])
    st, d = _api(drv, '/api/v1/laboratories?page=1&per_page=1000')
    items = (d.get('data') or {}).get('items', []) if isinstance(d, dict) else []
    _check('P2-1 删除后 GET 回读零残留',
           all(x.get('code') != LAB_CODE for x in items), detail=str([x.get('code') for x in items]))


def step_device_delete_enabled(drv, device_name):
    _goto(drv, '/devices/test')
    _wait_text(drv, device_name, 25)
    time.sleep(1.5)
    btn = _row_actions_button(drv, device_name)
    _check('P2-3 命中自建离线设备行操作菜单', btn is not None,
           detail=(btn.get_attribute('aria-label') if btn else ''))
    if not btn:
        return
    _js_click(drv, btn)
    item = _menu_item(drv, '删除')
    _check('P2-3 离线设备「删除」菜单项未禁用', not _item_disabled(item),
           detail=f'data-disabled={item.get_attribute("data-disabled")} '
                  f'aria-disabled={item.get_attribute("aria-disabled")}')
    _js_click(drv, item)
    _wait_text(drv, '删除设备', 10)
    _check('P2-3 离线设备删除确认弹窗可达', '确定要删除' in _body_text(drv))
    _evidence(drv, 'p23_offline_delete_confirm_light')
    _click_button_text(drv, '取消')
    time.sleep(0.8)


def step_port_removed(drv):
    _click_button_text(drv, '添加测试设备')
    _wait_text(drv, '连接方式', 12)
    time.sleep(0.8)
    labels = [e.text or '' for e in drv.find_elements(By.TAG_NAME, 'label')]
    _check('P3-1 设备表单无「端口」输入', not any('端口' in t for t in labels),
           detail=str(labels)[:300])
    trig = drv.find_element(
        By.XPATH, "//label[contains(normalize-space(.),'连接方式')]/following-sibling::button[@role='combobox']")
    _check('P3-1 连接方式下拉可选远程', _select_option(drv, trig, '远程连接'))
    time.sleep(0.6)
    has_ip = len(drv.find_elements(By.XPATH, "//input[@placeholder='192.168.x.x']")) > 0
    labels2 = [e.text or '' for e in drv.find_elements(By.TAG_NAME, 'label')]
    _check('P3-1 远程连接下仅 IP 地址（无端口）',
           has_ip and not any('端口' in t for t in labels2), detail=str(labels2)[:300])
    _evidence(drv, 'p31_drawer_remote_no_port_light')
    _click_button_text(drv, '取消')
    time.sleep(0.8)


def step_install_request(drv, device_id, device_name):
    st, _ = _api(drv, f'/api/v1/test-devices/{device_id}', 'PUT', {'status': 'online'})
    _check('P2-2 前置：自建测试设备置在线', st == 200, detail=str(st))
    _goto(drv, '/devices/test')
    _wait_text(drv, device_name, 25)
    time.sleep(2)
    btn = _row_actions_button(drv, device_name)
    _check('P2-2 行操作菜单命中自建设备', btn is not None)
    if not btn:
        return
    _js_click(drv, btn)
    item = _menu_item(drv, '安装应用')
    _check('P2-2 在线设备「安装应用」可用', not _item_disabled(item))
    _js_click(drv, item)
    _wait_text(drv, '应用安装包路径', 12)
    _fill(drv, 'op-file-path', '/sdcard/jx1495v.apk')
    _fill(drv, 'op-package', 'com.jx.int1495v')
    drv.execute_script('window.__reqlog = []')
    _drain_logs(drv)
    _click_button_text(drv, '执行安装')
    toast_text = _toast_text(drv, 20)
    _evidence(drv, 'p22_install_request_light')
    time.sleep(1.0)
    logs = [r for r in _reqlog(drv) if 'install-app' in r['url']]
    _COMPARE['install_req'] = logs
    _check('P2-2 安装发起真实 POST /test-devices/{id}/install-app', bool(logs),
           detail=json.dumps(logs, ensure_ascii=False)[:500])
    body = logs[0]['body'] if logs else None
    try:
        parsed = json.loads(body or '{}')
    except Exception:
        parsed = {}
    _check('P2-2 安装请求体 params.file_path',
           (parsed.get('params') or {}).get('file_path') == '/sdcard/jx1495v.apk', detail=str(body))
    _check('P2-2 安装请求体 params.package_name',
           (parsed.get('params') or {}).get('package_name') == 'com.jx.int1495v', detail=str(body))
    status_code = logs[0].get('status') if logs else None
    resp = logs[0].get('respText') if logs else ''
    try:
        backend_msg = (json.loads(resp or '{}') or {}).get('message') or ''
    except Exception:
        backend_msg = ''
    if status_code and status_code < 300:
        _check('P2-2 安装 toast 与真实请求一致（成功）', '已发起安装' in toast_text, detail=toast_text)
    else:
        hint = backend_msg.split(' (code=')[0] if backend_msg else '命令执行失败'
        _check('P2-2 安装失败 toast 呈现后端真实文案（非「已发起」假成功）',
               bool(hint) and hint in toast_text, detail=f'hint={hint!r} toast={toast_text!r}')

    time.sleep(1.0)
    btn = _row_actions_button(drv, device_name)
    _js_click(drv, btn)
    item = _menu_item(drv, '卸载应用')
    _js_click(drv, item)
    _wait_text(drv, '应用包名', 12)
    _fill(drv, 'op-uninstall-package', 'com.jx.int1495v')
    drv.execute_script('window.__reqlog = []')
    _click_button_text(drv, '执行卸载')
    toast_text = _toast_text(drv, 20)
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
           detail=json.dumps(logs, ensure_ascii=False)[:500])
    _check('P2-2 卸载请求体 params.package_name',
           (parsed.get('params') or {}).get('package_name') == 'com.jx.int1495v', detail=str(body))
    _check('P2-2 卸载请求体不带 file_path',
           'file_path' not in (parsed.get('params') or {}), detail=str(body))


def step_scan_connection(drv):
    _goto(drv, '/devices/test')
    _wait_text(drv, '设备管理', 20)
    _open_header_more(drv)
    _js_click(drv, _menu_item(drv, '扫描设备'))
    _wait_text(drv, '扫描测试设备', 12)
    time.sleep(8)  # 自动扫描
    dialog_text = drv.find_element(By.XPATH, "//*[@role='dialog']").text or ''
    _evidence(drv, 'p32_scan_dialog_real')
    if 'USB连接' in dialog_text or '远程连接' in dialog_text:
        _check('P3-2 真实扫描行展示连接方式', True, detail=dialog_text[-200:])
        return
    print('[INFO] 真实扫描 0 行（ADB 无设备）→ 合成扫描响应验证渲染（synthetic，标注）')
    drv.execute_script("""
        const syn = {success:true, code:0, message:'Success', data:[
          {serial:'JX1495V-USB', model:'INT1495V Model', system:'Android', status:'online',
           name:'Android INT1495V Model', type:'phone', system_version:'13',
           app_name:'Default App', app_version:'1.0.0', ip:''},
          {serial:'192.168.1.20:5555', model:'INT1495V Remote', system:'Android', status:'online',
           name:'Android INT1495V Remote', type:'phone', system_version:'13',
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
    """)
    btn = None
    for b in drv.find_elements(By.TAG_NAME, 'button'):
        if (b.text or '').strip() == '开始扫描':
            btn = b
    _check('P3-2 扫描弹窗「开始扫描」可点（非扫描中）',
           btn is not None and btn.get_attribute('disabled') is None)
    if btn:
        _js_click(drv, btn)
    WebDriverWait(drv, 30).until(
        lambda d: 'INT1495V Model' in _body_text(d))
    dialog_text = drv.find_element(By.XPATH, "//*[@role='dialog']").text or ''
    _check('P3-2 扫描行展示 USB连接', 'JX1495V-USB · USB连接' in dialog_text,
           detail=dialog_text[-260:])
    _check('P3-2 扫描行展示 远程连接（host:port 序列号）',
           '192.168.1.20:5555 · 远程连接' in dialog_text, detail=dialog_text[-260:])
    _evidence(drv, 'p32_scan_connection_synthetic')
    _click_button_text(drv, '取消')


def step_p24_alarm_charts(drv):
    """P2-4 补充门禁项：历史监控统计图表不得静默展示 mock 数据。"""
    _goto(drv, '/devices/test')
    _wait_text(drv, '设备管理', 20)
    time.sleep(1.5)
    try:
        trig = drv.find_element(
            By.XPATH, "//button[starts-with(normalize-space(.),'监控告警')]")
    except Exception:
        trig = None
    _check('P2-4 监控告警面板入口可达', trig is not None)
    if trig is None:
        return
    _js_click(drv, trig)
    time.sleep(1.5)
    # 切「历史监控」
    tabs = drv.find_elements(By.XPATH, "//*[@role='tab']")
    hist = next((t for t in tabs if '历史监控' in (t.text or '')), None)
    _check('P2-4 历史监控页签可达', hist is not None)
    if hist is None:
        return
    _js_click(drv, hist)
    time.sleep(1.5)
    drv.execute_script('window.__reqlog = []')
    _drain_logs(drv)
    body = _body_text(drv)
    has_charts = '可用性统计' in body and '性能统计' in body
    _check('P2-4 历史统计图表区渲染', has_charts)
    labeled = any(k in body for k in ('演示数据', '示例数据', '模拟数据', 'MOCK'))
    _check('P2-4 图表区显式标注「演示数据」（不得静默展示假数据）', labeled,
           detail='图表区文案片段：' + body[body.find('统计分析'):body.find('统计分析') + 120]
           if '统计分析' in body else body[-200:])
    metric_calls = [r for r in _reqlog(drv)
                    if any(k in r['url'] for k in ('/monitor', '/metrics', '/stats/history'))]
    _COMPARE['metric_calls'] = metric_calls
    _check('P2-4 图表数据来源不是真实指标端点（无相应请求，说明为本地常量）',
           not metric_calls, detail=json.dumps(metric_calls, ensure_ascii=False)[:300])
    canv = drv.find_elements(By.TAG_NAME, 'canvas')
    _check('P2-4 图表已绘制（canvas 数 > 0，即假数据确实在展示）', len(canv) > 0,
           detail=f'canvas={len(canv)}')
    _evidence(drv, 'p24_alarm_history_charts')


def step_screenshots(drv):
    _set_theme(drv, 'dark')
    _goto(drv, '/devices/test')
    _wait_text(drv, '设备管理', 20)
    time.sleep(1.5)
    _evidence(drv, 'devices_page_dark')
    _open_header_more(drv)
    _js_click(drv, _menu_item(drv, '实验室管理'))
    _wait_text(drv, '管理物理实验室及其资源归属', 20)
    time.sleep(2.0)
    _evidence(drv, 'lab_dialog_dark')
    _click_button_text(drv, '关闭')
    _set_theme(drv, 'light')
    _goto(drv, '/devices/test')
    _wait_text(drv, '设备管理', 20)
    time.sleep(1.5)
    _evidence(drv, 'devices_page_light')


def step_network_snapshot(drv):
    rows = []
    for k in ('labs_get', 'lab_posts', 'lab_puts', 'lab_deletes', 'install_req', 'uninstall_req'):
        rows.extend(_COMPARE.get(k) or [])
    if not rows:
        rows = [{'url': 'no captured request', 'method': '', 'status': '', 'body': ''}]
    html_rows = ''.join(
        f"<tr><td>{r.get('method','')}</td><td class='u'>{r.get('url','')}</td>"
        f"<td>{r.get('status','')}</td>"
        f"<td class='b'>{json.dumps(r.get('body') or r.get('postData'), ensure_ascii=False)}</td></tr>"
        for r in rows)
    html = f"""<!doctype html><meta charset="utf-8"><style>
    body{{font-family:Consolas,monospace;background:#0f1720;color:#e6edf3;padding:16px}}
    h3{{font-family:system-ui;margin:0 0 12px}}
    table{{border-collapse:collapse;width:100%;font-size:12px}}
    th,td{{border:1px solid #2d3b4a;padding:6px 8px;vertical-align:top;text-align:left}}
    th{{background:#1b2836}} .u{{color:#7cc4ff;word-break:break-all}}
    .b{{color:#a5d6a7;word-break:break-all;max-width:520px}}</style>
    <h3>INT-1495 验收 Network 证据（docker 真实栈 15000 / 旁路前端 15495）</h3>
    <table><tr><th>Method</th><th>URL</th><th>Status</th><th>Body / postData</th></tr>{html_rows}</table>"""
    path = os.path.join(ARTIFACTS, 'network_int1495_accept.html')
    os.makedirs(ARTIFACTS, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)
    drv.get('file:///' + path.replace('\\', '/'))
    time.sleep(1.2)
    drv.save_screenshot(os.path.join(ARTIFACTS, 'network_evidence.png'))
    _goto(drv, '/devices/test')
    _wait_text(drv, '设备管理', 20)


def step_cleanup(drv, device_id, lab):
    if lab:
        st, _ = _api(drv, f"/api/v1/laboratories/{lab['id']}", 'DELETE')
        print('[INFO] cleanup lab DELETE', lab['id'], st)
    if device_id:
        st, _ = _api(drv, f'/api/v1/test-devices/{device_id}', 'DELETE')
        print('[INFO] cleanup device DELETE', device_id, st)
    st, d = _api(drv, '/api/v1/laboratories?page=1&per_page=1000')
    codes = [x.get('code') for x in ((d.get('data') or {}).get('items', []) if isinstance(d, dict) else [])]
    _check('清理：本 run 实验室零残留', LAB_CODE not in codes, detail=str(codes))
    st, d = _api(drv, '/api/v1/test-devices?page=1&per_page=1000')
    names = [x.get('name') for x in ((d.get('data') or {}).get('items', []) if isinstance(d, dict) else [])]
    _check('清理：本 run 测试设备零残留', DEVICE_NAME not in names,
           detail=str([n for n in names if 'INT1495' in str(n)]))
    # 历史 run 残留（实现者交付评论自述已删；实测仍有 JX1495LAB，一并清理）
    for x in ((d.get('data') or {}).get('items', []) if isinstance(d, dict) else []):
        if str(x.get('name') or '').startswith('接线测试_INT1495'):
            st2, _ = _api(drv, f"/api/v1/test-devices/{x['id']}", 'DELETE')
            print('[INFO] cleanup legacy device', x.get('name'), st2)
    st, d = _api(drv, '/api/v1/laboratories?page=1&per_page=1000')
    for x in ((d.get('data') or {}).get('items', []) if isinstance(d, dict) else []):
        if str(x.get('code') or '').startswith('JX1495'):
            st2, _ = _api(drv, f"/api/v1/laboratories/{x['id']}", 'DELETE')
            print('[INFO] cleanup legacy lab', x.get('code'), st2)
    st, d = _api(drv, '/api/v1/laboratories?page=1&per_page=1000')
    codes = [x.get('code') for x in ((d.get('data') or {}).get('items', []) if isinstance(d, dict) else [])]
    _check('清理：JX1495* 实验室零残留', not [c for c in codes if str(c).startswith('JX1495')],
           detail=str(codes))


def main():
    os.makedirs(ARTIFACTS, exist_ok=True)
    drv = _driver()
    lab = None
    try:
        step_preflight(drv)
        # 自建测试设备（P2-2/P2-3 载体，默认 offline）
        st, d = _api(drv, '/api/v1/test-devices', 'POST', {
            'name': DEVICE_NAME, 'model': 'INT1495V-M', 'type': 'physical', 'system': 'Android',
            'system_version': '13', 'app_name': 'INT1495V App', 'app_version': '1.0.0',
            'status': 'offline', 'serial_number': DEVICE_SERIAL, 'connection_type': 'usb',
        })
        _check('前置：自建测试设备', st in (200, 201), detail=str(d)[:200])
        st, d = _api(drv, '/api/v1/test-devices?page=1&per_page=1000')
        items = (d.get('data') or {}).get('items', []) if isinstance(d, dict) else []
        dev = next((x for x in items if x.get('name') == DEVICE_NAME), None)
        device_id = dev.get('id') if dev else None
        _check('前置：自建设备可回读', device_id is not None, detail=str(device_id))

        step_lab_entry(drv)
        lab = step_lab_crud(drv)
        step_lab_delete(drv, lab)
        if device_id:
            step_device_delete_enabled(drv, DEVICE_NAME)
        else:
            _check('P2-3 无自建设备，跳过离线删除检查', False)
        step_port_removed(drv)
        if device_id:
            step_install_request(drv, device_id, DEVICE_NAME)
        step_scan_connection(drv)
        step_p24_alarm_charts(drv)
        step_screenshots(drv)
        step_network_snapshot(drv)
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
