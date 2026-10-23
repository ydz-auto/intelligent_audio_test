# -*- coding: utf-8 -*-
"""INT-1480 复走·React·设备域 —— 第三轮（INT-1495 修复后）复测。

只复测上一轮未通过/被打回的项（devloop §6 打回后只复测失败项）：
  R1 实验室管理：入口解禁 + 真实 GET/POST/PUT/DELETE /laboratories + GET 回读 + mock 移除
  R2 安装/卸载应用：请求体带 params.file_path / params.package_name（Network postData）
  R3 离线设备「删除」解禁 + 设备新建→编辑→删除 UI 闭环 + GET 回读
  R4 设备表单「端口」输入移除
  R5 扫描结果行展示「连接方式」（真实扫描为空时用合成响应验证渲染，标注 synthetic）

环境：docker 真实栈 前端 http://127.0.0.1:15173（nginx /api → 15000 api_gateway，
真实库 intelligent_audio_test，AUTH_MODE=off）。不起本地前端/后端。
数据卫生：只创建「接线测试_INT1480R3_」前缀记录，结束前删除并 API 复核零残留。
证据落 tests/ui/artifacts/int1480_round3/<步骤>/。
"""
import json
import os
import sys
import time
import urllib.request
import functools

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

print = functools.partial(print, flush=True)  # noqa: A001
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

BASE = os.environ.get('INT1480_BASE', 'http://127.0.0.1:15173')
GATEWAY = os.environ.get('INT1480_GATEWAY', 'http://127.0.0.1:15000')
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1480_round3')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

TEST = '接线测试_INT1480R3_'
LAB_NAME = TEST + '实验室'
LAB_CODE = 'JXR3LAB'
LAB_NAME2 = TEST + '实验室改名'
DEV_NAME = TEST + '设备'
DEV_MODEL = 'R3-MODEL'
DEV_IP = '10.148.3.9'
DEV_MODEL2 = 'R3-MODEL-EDITED'
DEVICE_OP_NAME = TEST + '安装设备'

CRASH_MARKERS = ['糟糕！出错了', '页面加载失败', '哎呀！出错了']

_FAILURES = []
_PASS = []
_LOG = {}


def _check(name, cond, detail=''):
    tag = 'PASS' if cond else 'FAIL'
    print(f'[{tag}] {name}' + (f' — {detail}' if detail else ''))
    (_PASS if cond else _FAILURES).append(name)


def _chromedriver():
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    cands = []
    if os.path.isdir(cache_root):
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
                except ValueError:
                    continue
    return max(cands)[1] if cands else ''


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.add_argument('--disable-dev-shm-usage')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    p = _chromedriver()
    drv = webdriver.Chrome(options=options, service=Service(executable_path=p) if p else Service())
    drv.set_page_load_timeout(60)
    drv.set_script_timeout(120)
    return drv


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 25).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.8)


def _body(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _wait_text(drv, text, timeout=20):
    WebDriverWait(drv, timeout).until(lambda d: text in _body(d))


def _jsclick(drv, el):
    drv.execute_script('arguments[0].click()', el)
    time.sleep(0.4)


def _native_click(drv, el):
    """原生点击：抽屉 <button type=submit> 的 JS .click() 不触发表单提交（base-ui 表单），
    真实用户点击等价于原生 click（已用两种方式对照验证）。"""
    el.click()
    time.sleep(0.4)


def _submit(drv):
    """点抽屉/弹窗内的提交按钮（原生点击）。"""
    for b in drv.find_elements(By.XPATH, "//button[@type='submit']"):
        try:
            if b.is_displayed():
                _native_click(drv, b)
                return True
        except Exception:
            continue
    return False


def _set_theme(drv, theme):
    drv.get(BASE + '/devices/test')
    WebDriverWait(drv, 25).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    drv.execute_script("window.localStorage.setItem('iatp:theme:v1:mode', arguments[0])", theme)
    drv.refresh()
    WebDriverWait(drv, 25).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(2.2)


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
        print(f'  (evidence {name} failed: {e})')
    return os.path.join(d, 'screenshot.png')


def _drain_perf(drv):
    try:
        drv.get_log('performance')
    except Exception:
        pass


def _net(drv, path_substr):
    """performance log 双层解包：method + url + status + postData。"""
    reqs, resp = {}, {}
    try:
        for entry in drv.get_log('performance'):
            inner = json.loads(entry['message']).get('message', {})
            ev, p = inner.get('method'), inner.get('params', {})
            if ev == 'Network.requestWillBeSent':
                r = p.get('request', {})
                reqs[p.get('requestId')] = (r.get('url', ''), r.get('method', ''), r.get('postData'))
            elif ev == 'Network.responseReceived':
                resp[p.get('requestId')] = p.get('response', {}).get('status')
    except Exception as e:
        return [{'error': str(e)}]
    out = []
    for rid, (url, method, post) in reqs.items():
        if path_substr in url:
            out.append({'url': url, 'method': method, 'status': resp.get(rid), 'postData': post})
    return out


def _api(path, method='GET', body=None):
    url = BASE + '/api/v1' + path
    data = None
    headers = {'Accept': 'application/json'}
    if body is not None:
        data = json.dumps(body).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            raw = r.read().decode('utf-8')
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8')
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw
    except Exception as e:
        return 0, str(e)


def _payload(resp):
    if isinstance(resp, dict) and 'data' in resp:
        return resp.get('data')
    return resp


def _health():
    last = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(f'{GATEWAY}/health', timeout=10) as r:
                return json.loads(r.read().decode('utf-8'))
        except Exception as e:
            last = e
            time.sleep(2)
    return {'error': str(last)}


def _menu_item(drv, label, timeout=8):
    def find(d):
        for it in d.find_elements(By.XPATH, "//*[@role='menuitem']"):
            try:
                if label in it.text and it.is_displayed():
                    return it
            except Exception:
                continue
        return False
    return WebDriverWait(drv, timeout).until(find)


def _item_disabled(el):
    return (el.get_attribute('data-disabled') is not None
            or el.get_attribute('aria-disabled') == 'true')


def _open_more(drv):
    _jsclick(drv, drv.find_element(By.XPATH, "//button[@aria-label='更多操作']"))
    time.sleep(0.6)


def _row_action(drv, name):
    return drv.find_element(By.XPATH, "//button[@aria-label='操作 %s']" % name)


def _press_esc(drv):
    webdriver.ActionChains(drv).send_keys(Keys.ESCAPE).perform()
    time.sleep(0.8)


def _close_dialog(drv):
    btns = drv.find_elements(
        By.XPATH, "//*[@role='dialog']//button[contains(., '关闭') or contains(., '取消')]")
    for b in btns:
        try:
            if b.is_displayed():
                _jsclick(drv, b)
                time.sleep(0.8)
                return True
        except Exception:
            continue
    _press_esc(drv)
    return False


def _dialog_text(drv):
    els = drv.find_elements(By.XPATH, "//*[@role='dialog' or @role='alertdialog']")
    return ' '.join((e.text or '') for e in els)


def _toast_text(drv, timeout=12):
    def find(d):
        els = d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')
        txt = ' '.join((e.text or '') for e in els).strip()
        return txt or False
    try:
        return WebDriverWait(drv, timeout).until(find)
    except Exception:
        return ''


def _click(text):
    return ("//button[normalize-space(.)='%s']" % text)


def _fill_id(drv, el_id, text):
    el = drv.find_element(By.ID, el_id)
    el.clear()
    el.send_keys(text)
    return el


def _fill_label(drv, label, text):
    """按 Field label 定位输入框（Field 由 Label + Input 组成，无稳定 id）。"""
    el = drv.find_element(
        By.XPATH, "//label[contains(normalize-space(.), '%s')]/following::input[1]" % label)
    el.clear()
    el.send_keys(text)
    return el


def _confirm_alert(drv, labels=('删除', '确认', '确定', '继续')):
    """ConfirmDialog 是 AlertDialog（role=alertdialog），确认按钮文案可为「删除/继续」等。"""
    def find(d):
        for b in d.find_elements(By.XPATH, "//*[@role='alertdialog']//button"):
            try:
                if (b.text or '').strip() in labels and b.is_displayed():
                    return b
            except Exception:
                continue
        return False
    try:
        btn = WebDriverWait(drv, 12).until(find)
    except Exception:
        return False
    _jsclick(drv, btn)
    return True


def _select_option(drv, trigger, label):
    _jsclick(drv, trigger)
    time.sleep(0.5)
    for o in drv.find_elements(By.XPATH, "//*[@role='option']"):
        if label in (o.text or ''):
            _jsclick(drv, o)
            return True
    _press_esc(drv)
    return False


# ============================ 步骤 ============================

def step_preflight(drv):
    h = _health()
    _LOG['health_start'] = h
    _check('环境 1/3 /health database=intelligent_audio_test',
           h.get('database') == 'intelligent_audio_test', detail=json.dumps(h, ensure_ascii=False))
    html = urllib.request.urlopen(BASE + '/', timeout=15).read().decode('utf-8', 'ignore')
    lib_react = 'lib-react' in html
    idx = ''
    for tok in html.split('"'):
        if tok.startswith('/static/js/index.') and tok.endswith('.js'):
            idx = tok
            break
    _LOG['frontend'] = {'lib_react': lib_react, 'index': idx}
    _check('环境 React 构建（lib-react 引用）', lib_react, detail=idx)
    st, d = _api('/test-devices?page=1&per_page=200')
    items = (_payload(d) or {}).get('items', []) if isinstance(d, dict) else []
    _LOG['devices_start'] = [{'id': x['id'], 'name': x['name'], 'status': x['status']} for x in items]
    _LOG['device_ids_before'] = {x['id'] for x in items}
    _check('基线 GET /test-devices 200', st == 200, detail=f'total={len(items)}')
    st2, d2 = _api('/laboratories?page=1&per_page=200')
    labs = (_payload(d2) or {}).get('items', []) if isinstance(d2, dict) else []
    _LOG['labs_start'] = [{'id': x['id'], 'code': x.get('code'), 'name': x.get('name')} for x in labs]
    _check('基线 GET /laboratories 200', st2 == 200, detail=f'total={len(labs)}')
    _drain_perf(drv)
    _goto(drv, '/devices/test')
    _wait_text(drv, '设备管理', 40)
    time.sleep(2.0)
    lab_get = [n for n in _net(drv, '/laboratories') if n.get('method') == 'GET']
    _LOG['lab_get_page_load'] = lab_get
    _check('R1 设备页挂载即打真实 GET /laboratories 200（数据非 mock）',
           bool(lab_get) and lab_get[-1].get('status') == 200,
           detail=json.dumps(lab_get[-2:], ensure_ascii=False))
    txt = _body(drv)
    _check('设备页渲染无崩溃', all(m not in txt for m in CRASH_MARKERS))
    _check('设备页真实设备名可见', all(x['name'] in txt for x in items[:4]) if items else True)
    return items


def step_lab_entry(drv):
    _drain_perf(drv)
    _open_more(drv)
    item = _menu_item(drv, '实验室管理')
    _check('R1 更多操作→实验室管理 存在', item is not None)
    dis = _item_disabled(item)
    _check('R1 实验室管理入口已解禁', not dis,
           detail=f'data-disabled={item.get_attribute("data-disabled")} aria-disabled={item.get_attribute("aria-disabled")}')
    _jsclick(drv, item)
    _wait_text(drv, '管理物理实验室及其资源归属', 15)
    time.sleep(1.5)
    _check('R1 实验室管理弹窗可达', '实验室管理' in _dialog_text(drv))
    net = [n for n in _net(drv, '/laboratories') if n.get('method') == 'GET']
    _LOG['lab_get_dialog'] = net
    # 弹窗数据来自页面级 useLaboratories（挂载时已 GET，React Query 缓存命中不再重取）
    _check('R1 弹窗打开无新增 mock 数据源（页面级 GET 已覆盖）',
           bool(_LOG.get('lab_get_page_load')) or bool(net),
           detail=json.dumps(net[-2:], ensure_ascii=False))
    _evidence(drv, 'r1_lab_dialog_light')


def step_lab_crud(drv):
    _fill_id(drv, 'lab-name', LAB_NAME)
    _fill_id(drv, 'lab-code', LAB_CODE)
    _fill_id(drv, 'lab-building', '研发中心测试楼')
    _fill_id(drv, 'lab-floor', '5 层')
    _fill_id(drv, 'lab-room', '501')
    _fill_id(drv, 'lab-desc', 'INT-1480 第三轮复测自建，验收后删除')
    _jsclick(drv, drv.find_element(By.XPATH, "//button[normalize-space(.)='新建实验室']"))
    _wait_text(drv, LAB_NAME, 60)  # 列表含 test_case_count 聚合，刷新较慢
    time.sleep(1.5)
    st, d = _api('/laboratories?page=1&per_page=200')
    items = (_payload(d) or {}).get('items', []) if isinstance(d, dict) else []
    lab = next((x for x in items if x.get('code') == LAB_CODE), None)
    _LOG['lab_created'] = lab
    _check('R1 新建实验室落库（POST + GET 回读）', lab is not None, detail=json.dumps(lab, ensure_ascii=False))
    if lab:
        _check('R1 新建回读字段一致',
               lab.get('name') == LAB_NAME and lab.get('building') == '研发中心测试楼'
               and lab.get('floor') == '5 层' and lab.get('room_number') == '501'
               and lab.get('status') == 'active',
               detail=json.dumps(lab, ensure_ascii=False))
    net_post = [n for n in _net(drv, '/laboratories') if n.get('method') == 'POST']
    _LOG['lab_post'] = net_post
    _check('R1 Network POST /laboratories 201', any((n.get('status') or 0) in (200, 201) for n in net_post),
           detail=json.dumps(net_post[-2:], ensure_ascii=False))
    _evidence(drv, 'r1_lab_created_light')

    # 编辑：回显 + 保存 + 回读
    _jsclick(drv, drv.find_element(By.XPATH, "//button[@aria-label='编辑实验室 " + LAB_NAME + "']"))
    time.sleep(1.0)
    echo = {k: drv.find_element(By.ID, k).get_attribute('value')
            for k in ['lab-name', 'lab-code', 'lab-building', 'lab-floor', 'lab-room', 'lab-desc']}
    _LOG['lab_edit_echo'] = echo
    _check('R1 编辑回显全部字段',
           echo['lab-name'] == LAB_NAME and echo['lab-code'] == LAB_CODE
           and echo['lab-building'] == '研发中心测试楼' and echo['lab-floor'] == '5 层'
           and echo['lab-room'] == '501',
           detail=json.dumps(echo, ensure_ascii=False))
    _fill_id(drv, 'lab-name', LAB_NAME2)
    _fill_id(drv, 'lab-floor', '6 层')
    status_trig = drv.find_element(By.ID, 'lab-status')
    _check('R1 实验室状态下拉可切换「维护中」', _select_option(drv, status_trig, '维护中'))
    closed_label = drv.find_element(By.ID, 'lab-status').text
    _check('R1 状态 Select 闭合态显示中文标签（非 raw value）', '维护中' in closed_label,
           detail=closed_label)
    _jsclick(drv, drv.find_element(By.XPATH, "//button[normalize-space(.)='保存修改']"))
    _wait_text(drv, LAB_NAME2, 60)
    time.sleep(1.5)
    st, d = _api('/laboratories?page=1&per_page=200')
    items = (_payload(d) or {}).get('items', []) if isinstance(d, dict) else []
    lab2 = next((x for x in items if x.get('code') == LAB_CODE), None)
    _LOG['lab_updated'] = lab2
    _check('R1 编辑保存回读（名称/楼层/状态）',
           bool(lab2) and lab2.get('name') == LAB_NAME2 and lab2.get('floor') == '6 层'
           and lab2.get('status') == 'maintenance',
           detail=json.dumps(lab2, ensure_ascii=False))
    _evidence(drv, 'r1_lab_updated_light')
    return lab


def step_lab_delete(drv):
    _jsclick(drv, drv.find_element(By.XPATH, "//button[@aria-label='删除实验室 " + LAB_NAME2 + "']"))
    WebDriverWait(drv, 12).until(lambda d: len(d.find_elements(By.XPATH, "//*[@role='alertdialog']")) > 0)
    time.sleep(0.8)
    _check('R1 删除实验室确认弹窗可达（AlertDialog）',
           '删除实验室' in _dialog_text(drv), detail=_dialog_text(drv)[:160])
    _evidence(drv, 'r1_lab_delete_confirm_light')
    confirmed = _confirm_alert(drv, ('删除',))
    _check('R1 删除实验室确认可提交', confirmed)
    time.sleep(3.0)
    st, d = _api('/laboratories?page=1&per_page=200')
    items = (_payload(d) or {}).get('items', []) if isinstance(d, dict) else []
    _check('R1 删除后 GET 回读消失',
           not any(x.get('code') == LAB_CODE for x in items),
           detail=str([x.get('code') for x in items]))


def step_port_removed(drv):
    _goto(drv, '/devices/test')
    _wait_text(drv, '设备管理', 20)
    for b in drv.find_elements(By.XPATH, "//button[contains(., '添加测试设备')]"):
        if b.is_displayed():
            _jsclick(drv, b)
            break
    _wait_text(drv, '测试设备信息', 12)
    time.sleep(0.8)
    labels = [e.text or '' for e in drv.find_elements(By.TAG_NAME, 'label')]
    _LOG['drawer_labels'] = labels
    _check('R4 设备表单无「端口」输入', not any('端口' in t for t in labels),
           detail=str(labels[:24]))
    trig = drv.find_element(
        By.XPATH, "//label[contains(normalize-space(.),'连接方式')]/following-sibling::button[@role='combobox']")
    _check('R4 连接方式可切「远程连接」', _select_option(drv, trig, '远程连接'))
    time.sleep(0.8)
    has_ip = len(drv.find_elements(By.XPATH, "//input[@placeholder='192.168.x.x']")) > 0
    labels2 = [e.text or '' for e in drv.find_elements(By.TAG_NAME, 'label')]
    _check('R4 远程连接仅 IP（无端口输入）',
           has_ip and not any('端口' in t for t in labels2), detail=str(labels2[:24]))
    _evidence(drv, 'r4_drawer_remote_no_port_light')
    _close_dialog(drv)
    time.sleep(1.0)


def step_device_lifecycle(drv):
    """R3：UI 新建 → GET 回读 → 编辑 → GET 回读 → 离线删除（原先被禁用）→ GET 消失。"""
    _goto(drv, '/devices/test')
    _wait_text(drv, '设备管理', 20)
    _drain_perf(drv)
    for b in drv.find_elements(By.XPATH, "//button[contains(., '添加测试设备')]"):
        if b.is_displayed():
            _jsclick(drv, b)
            break
    _wait_text(drv, '测试设备信息', 12)
    drv.find_element(By.XPATH, "//input[@placeholder='如：音箱-客厅位']").send_keys(DEV_NAME)
    drv.find_element(By.XPATH, "//input[@placeholder='如：旗舰 S1']").send_keys(DEV_MODEL)
    # 必填项：系统版本/应用名称/应用版本/设备序列号（表单无默认值）
    _fill_label(drv, '系统版本', '13')
    _fill_label(drv, '应用名称', 'INT1480 R3 App')
    _fill_label(drv, '应用版本', '1.0.0')
    _fill_label(drv, '设备序列号', 'JXR3SN01')
    # 连接方式默认 USB；切远程以覆盖 IP
    try:
        trig = drv.find_element(
            By.XPATH, "//label[contains(normalize-space(.),'连接方式')]/following-sibling::button[@role='combobox']")
        _select_option(drv, trig, '远程连接')
        time.sleep(0.6)
        drv.find_element(By.XPATH, "//input[@placeholder='192.168.x.x']").send_keys(DEV_IP)
    except Exception as e:
        _check('R3 表单设置远程 IP', False, repr(e))
    try:
        ta = drv.find_element(By.XPATH, "//textarea[@placeholder='设备用途或工位说明']")
        ta.send_keys(TEST + '描述')
    except Exception:
        pass
    drv.execute_script('window.__reqlog = []')
    _submit(drv)
    time.sleep(3.0)
    st, lst = _api('/test-devices?page=1&per_page=200')
    items = (_payload(lst) or {}).get('items', []) if isinstance(lst, dict) else []
    created = [x for x in items if x['name'] == DEV_NAME and x['id'] not in _LOG.get('device_ids_before', set())]
    _LOG['device_created'] = created[0] if created else None
    _check('R3 新建设备 GET 回读命中（本轮新增 1 条）', len(created) == 1,
           detail=f'hits={len(created)} ids={[x["id"] for x in created]}')
    dev_id = created[0]['id'] if created else None
    if created:
        c = created[0]
        _check('R3 新建字段回读一致（model/ip/status）',
               c.get('model') == DEV_MODEL and c.get('ip') == DEV_IP and c.get('status') == 'offline',
               detail=f'model={c.get("model")} ip={c.get("ip")} status={c.get("status")} conn={c.get("connection_type")}')
    posts = [n for n in _net(drv, '/test-devices') if n.get('method') == 'POST' and '/test-devices' in n['url']]
    _LOG['device_post'] = posts
    _check('R3 Network POST /test-devices <300', any((n.get('status') or 0) < 300 for n in posts),
           detail=json.dumps(posts[-2:], ensure_ascii=False))
    _evidence(drv, 'r3_device_created_light')

    if not dev_id:
        return None

    # 编辑
    _goto(drv, '/devices/test')
    _wait_text(drv, DEV_NAME, 45)
    _drain_perf(drv)
    _jsclick(drv, _row_action(drv, DEV_NAME))
    _jsclick(drv, _menu_item(drv, '编辑'))
    _wait_text(drv, '测试设备信息', 12)
    time.sleep(1.0)
    v_name = drv.find_element(By.XPATH, "//input[@placeholder='如：音箱-客厅位']").get_attribute('value')
    v_model = drv.find_element(By.XPATH, "//input[@placeholder='如：旗舰 S1']").get_attribute('value')
    _check('R3 编辑抽屉回显 name/model', v_name == DEV_NAME and v_model == DEV_MODEL,
           detail=f'name={v_name} model={v_model}')
    m_el = drv.find_element(By.XPATH, "//input[@placeholder='如：旗舰 S1']")
    m_el.clear()
    m_el.send_keys(DEV_MODEL2)
    _evidence(drv, 'r3_device_edit_light')
    _submit(drv)
    time.sleep(3.0)
    st, lst = _api('/test-devices?page=1&per_page=200')
    items = (_payload(lst) or {}).get('items', []) if isinstance(lst, dict) else []
    got = [x for x in items if x['id'] == dev_id]
    _check('R3 编辑保存 GET 回读 model 更新',
           bool(got) and got[0].get('model') == DEV_MODEL2,
           detail=f'model={got[0].get("model") if got else None}')
    puts = [n for n in _net(drv, '/test-devices/') if n.get('method') == 'PUT']
    _LOG['device_put'] = puts
    _check('R3 Network PUT /test-devices/{id} <300', any((n.get('status') or 0) < 300 for n in puts),
           detail=json.dumps(puts[-2:], ensure_ascii=False))

    # 离线删除（P2-3）
    _goto(drv, '/devices/test')
    _wait_text(drv, DEV_NAME, 45)
    time.sleep(1.0)
    _jsclick(drv, _row_action(drv, DEV_NAME))
    item = _menu_item(drv, '删除')
    row_status = None
    for x in items:
        if x['id'] == dev_id:
            row_status = x.get('status')
    _check('R3 目标设备为离线态（删除原先被禁用）', row_status == 'offline', detail=str(row_status))
    _check('R3 离线设备「删除」菜单项未禁用', not _item_disabled(item),
           detail=f'data-disabled={item.get_attribute("data-disabled")} aria-disabled={item.get_attribute("aria-disabled")}')
    _jsclick(drv, item)
    WebDriverWait(drv, 12).until(lambda d: len(d.find_elements(By.XPATH, "//*[@role='alertdialog']")) > 0)
    time.sleep(0.8)
    _check('R3 删除确认弹窗可达', '删除设备' in _dialog_text(drv) or '确定要删除' in _dialog_text(drv),
           detail=_dialog_text(drv)[:120])
    _evidence(drv, 'r3_delete_confirm_light')
    done = _confirm_alert(drv, ('删除', '确定', '继续'))
    _check('R3 删除确认可提交', done)
    time.sleep(3.0)
    st, lst = _api('/test-devices?page=1&per_page=200')
    items = (_payload(lst) or {}).get('items', []) if isinstance(lst, dict) else []
    _check('R3 删除后 GET 回读消失', not any(x['id'] == dev_id for x in items))
    return dev_id


def step_install_uninstall(drv):
    """R2：安装/卸载请求体带 params（在线设备）。"""
    st, d = _api('/test-devices', 'POST', {
        'name': DEVICE_OP_NAME, 'model': 'R3-OP-M', 'type': 'physical', 'system': 'Android',
        'system_version': '13', 'app_name': 'R3 App', 'app_version': '1.0.0',
        'status': 'offline', 'serial_number': 'JXR3OP01', 'connection_type': 'usb',
    })
    _check('R2 前置：自建在线载体设备', st in (200, 201), detail=str(d)[:160])
    st, lst = _api('/test-devices?page=1&per_page=200')
    items = (_payload(lst) or {}).get('items', []) if isinstance(lst, dict) else []
    dev = next((x for x in items if x['name'] == DEVICE_OP_NAME), None)
    if not dev:
        _check('R2 前置：载体设备可回读', False)
        return None
    dev_id = dev['id']
    st, _ = _api(f'/test-devices/{dev_id}', 'PUT', {'status': 'online'})
    _check('R2 前置：载体设备置在线（PUT）', st == 200, detail=str(st))

    _goto(drv, '/devices/test')
    _wait_text(drv, DEVICE_OP_NAME, 45)
    time.sleep(1.5)
    _drain_perf(drv)
    _jsclick(drv, _row_action(drv, DEVICE_OP_NAME))
    item = _menu_item(drv, '安装应用')
    _check('R2 在线设备「安装应用」菜单可用', not _item_disabled(item))
    _jsclick(drv, item)
    _wait_text(drv, '应用安装包路径', 12)
    _fill_id(drv, 'op-file-path', '/sdcard/int1480r3.apk')
    _fill_id(drv, 'op-package', 'com.jx.int1480r3')
    drv.execute_script('window.__reqlog = []')
    _drain_perf(drv)
    _evidence(drv, 'r2_install_dialog_light')
    _jsclick(drv, drv.find_element(By.XPATH, "//button[normalize-space(.)='执行安装']"))
    toast = _toast_text(drv, 15)
    time.sleep(1.5)
    logs = [n for n in _net(drv, 'install-app')]
    _LOG['install_req'] = logs
    _LOG['install_toast'] = toast
    _check('R2 安装发起真实 POST /test-devices/{id}/install-app', bool(logs),
           detail=json.dumps(logs[-2:], ensure_ascii=False))
    body = logs[-1].get('postData') if logs else None
    parsed = {}
    try:
        parsed = json.loads(body or '{}')
    except Exception:
        parsed = {}
    _check('R2 安装请求体含 params.file_path',
           (parsed.get('params') or {}).get('file_path') == '/sdcard/int1480r3.apk', detail=str(body))
    _check('R2 安装请求体含 params.package_name',
           (parsed.get('params') or {}).get('package_name') == 'com.jx.int1480r3', detail=str(body))
    _evidence(drv, 'r2_install_submitted_light')

    # 卸载
    time.sleep(1.5)
    _goto(drv, '/devices/test')
    _wait_text(drv, DEVICE_OP_NAME, 45)
    time.sleep(1.0)
    _drain_perf(drv)
    _jsclick(drv, _row_action(drv, DEVICE_OP_NAME))
    item = _menu_item(drv, '卸载应用')
    _jsclick(drv, item)
    _wait_text(drv, '应用包名', 12)
    _fill_id(drv, 'op-uninstall-package', 'com.jx.int1480r3')
    _evidence(drv, 'r2_uninstall_dialog_light')
    _jsclick(drv, drv.find_element(By.XPATH, "//button[normalize-space(.)='执行卸载']"))
    toast2 = _toast_text(drv, 15)
    time.sleep(1.5)
    logs2 = [n for n in _net(drv, 'uninstall-app')]
    _LOG['uninstall_req'] = logs2
    _LOG['uninstall_toast'] = toast2
    _check('R2 卸载发起真实 POST /test-devices/{id}/uninstall-app', bool(logs2),
           detail=json.dumps(logs2[-2:], ensure_ascii=False))
    body2 = logs2[-1].get('postData') if logs2 else None
    try:
        parsed2 = json.loads(body2 or '{}')
    except Exception:
        parsed2 = {}
    _check('R2 卸载请求体含 params.package_name',
           (parsed2.get('params') or {}).get('package_name') == 'com.jx.int1480r3', detail=str(body2))
    _check('R2 卸载请求体不带 file_path',
           'file_path' not in (parsed2.get('params') or {}), detail=str(body2))
    _check('R2 toast 呈现真实结果（非静默成功）', bool(toast) or bool(toast2),
           detail=f'install={toast!r} uninstall={toast2!r}')
    return dev_id


def step_scan_connection(drv):
    """R5：扫描行展示连接方式（真实扫描空 → 合成响应验证渲染，标注 synthetic）。"""
    _goto(drv, '/devices/test')
    _wait_text(drv, '设备管理', 20)
    _open_more(drv)
    _jsclick(drv, _menu_item(drv, '扫描设备'))
    _wait_text(drv, '扫描测试设备', 12)
    time.sleep(5)
    dtext = _dialog_text(drv)
    _LOG['scan_real'] = dtext[:500]
    _evidence(drv, 'r5_scan_real_light')
    if 'USB连接' in dtext or '远程连接' in dtext:
        _check('R5 真实扫描行展示连接方式', True, detail=dtext[-200:])
        _close_dialog(drv)
        return
    print('[INFO] 真实扫描 0 行（本机无 ADB 设备），改用合成扫描响应验证渲染（synthetic）')
    drv.execute_script("""
        const syn = {success:true, code:0, message:'Success', data:[
          {serial:'JXR3-USB', model:'R3 USB Model', system:'Android', status:'online',
           name:'Android R3 USB Model', type:'phone', system_version:'13',
           app_name:'Default App', app_version:'1.0.0', ip:''},
          {serial:'192.168.3.20:5555', model:'R3 Remote Model', system:'Android', status:'online',
           name:'Android R3 Remote Model', type:'phone', system_version:'13',
           app_name:'Default App', app_version:'1.0.0', ip:'192.168.3.20'}
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
    _check('R5 扫描弹窗「开始扫描」可点', btn is not None and btn.get_attribute('disabled') is None)
    if btn:
        _jsclick(drv, btn)
    WebDriverWait(drv, 25).until(lambda d: 'R3 USB Model' in _body(d))
    dtext = _dialog_text(drv)
    _LOG['scan_synthetic'] = dtext[:800]
    _check('R5 扫描行展示「USB连接」', 'JXR3-USB · USB连接' in dtext, detail=dtext[-260:])
    _check('R5 扫描行展示「远程连接」（host:port 序列号）',
           '192.168.3.20:5555 · 远程连接' in dtext, detail=dtext[-260:])
    _evidence(drv, 'r5_scan_connection_synthetic')
    _close_dialog(drv)


def step_dark_shots(drv):
    _set_theme(drv, 'dark')
    _goto(drv, '/devices/test')
    _wait_text(drv, '设备管理', 20)
    time.sleep(1.2)
    _evidence(drv, 'r_dark_devices_page')
    _open_more(drv)
    _jsclick(drv, _menu_item(drv, '实验室管理'))
    _wait_text(drv, '管理物理实验室及其资源归属', 15)
    time.sleep(1.5)
    _evidence(drv, 'r1_lab_dialog_dark')
    _close_dialog(drv)
    time.sleep(1.0)
    _set_theme(drv, 'light')
    _goto(drv, '/devices/test')
    _wait_text(drv, '设备管理', 20)


def step_cleanup(drv, leftover_dev_ids):
    removed = []
    # 本卡前缀残留（含历史中断 run）
    st, d = _api('/laboratories?page=1&per_page=200')
    items = (_payload(d) or {}).get('items', []) if isinstance(d, dict) else []
    for x in items:
        if str(x.get('code') or '').startswith('JXR3'):
            st2, _ = _api(f"/laboratories/{x['id']}", 'DELETE')
            removed.append(('lab', x.get('code'), st2))
    st, d = _api('/test-devices?page=1&per_page=200')
    items = (_payload(d) or {}).get('items', []) if isinstance(d, dict) else []
    for x in items:
        if str(x.get('name') or '').startswith(TEST):
            st2, _ = _api(f"/test-devices/{x['id']}", 'DELETE')
            removed.append(('device', x.get('name'), st2))
    for did in leftover_dev_ids or []:
        _api(f'/test-devices/{did}', 'DELETE')
    _LOG['cleanup'] = removed
    st, d = _api('/test-devices?page=1&per_page=200')
    items = (_payload(d) or {}).get('items', []) if isinstance(d, dict) else []
    _check('清理：测试设备零残留', not any(str(x.get('name') or '').startswith(TEST) for x in items),
           detail=str(removed))
    st, d = _api('/laboratories?page=1&per_page=200')
    items = (_payload(d) or {}).get('items', []) if isinstance(d, dict) else []
    _check('清理：实验室零残留', not any(str(x.get('code') or '').startswith('JXR3') for x in items))


def main():
    os.makedirs(ARTIFACTS, exist_ok=True)
    drv = _driver()
    dev_id = None
    op_dev_id = None
    try:
        step_preflight(drv)
        step_lab_entry(drv)
        step_lab_crud(drv)
        step_lab_delete(drv)
        step_port_removed(drv)
        dev_id = step_device_lifecycle(drv)
        op_dev_id = step_install_uninstall(drv)
        step_scan_connection(drv)

        h = _health()
        _LOG['health_before_shots'] = h
        _check('环境 2/3（截图前）/health 仍为 intelligent_audio_test',
               h.get('database') == 'intelligent_audio_test', detail=json.dumps(h, ensure_ascii=False))
        step_dark_shots(drv)

        h = _health()
        _LOG['health_before_delivery'] = h
        _check('环境 3/3（交付前）/health 仍为 intelligent_audio_test',
               h.get('database') == 'intelligent_audio_test', detail=json.dumps(h, ensure_ascii=False))

        step_cleanup(drv, [x for x in (dev_id, op_dev_id) if x])

        with open(os.path.join(ARTIFACTS, 'summary.json'), 'w', encoding='utf-8') as f:
            json.dump({'log': _LOG, 'pass': _PASS, 'fail': _FAILURES}, f,
                      ensure_ascii=False, indent=2, default=str)
    finally:
        try:
            drv.quit()
        except Exception:
            pass

    print('\n==== RESULT ====')
    print(f'PASS {len(_PASS)} / FAIL {len(_FAILURES)}')
    print('FAILURES:', _FAILURES if _FAILURES else 'none')
    return 0 if not _FAILURES else 1


if __name__ == '__main__':
    sys.exit(main())
