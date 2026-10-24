# -*- coding: utf-8 -*-
"""INT-1480 第四轮返工实测（前端UX审计 P2-1 / P3-1 / P3-2 修复）。

被验修复：
  P2-1 base-ui Select 闭合态显示原始 value → 补 items（设备抽屉 12 个 Select、告警规则 2 个，
       另自查同域：告警面板筛选项 / 分组类型 / 成员添加 / 关联 SPL / 分页条数）
  P3-1 安装/卸载弹窗关闭后重开残留上次输入 → 每次打开 reset
  P3-2 表头逐字换行（告警规则表 阈值/级别/邮件/启用；测试设备表 提示词）

被测产物：本 run worktree `pnpm build` 的 dist（容器 iat-int1480-verify :15284 静态托管，
          nginx 反代 /api → api_gateway；后端真实库栈 :15000）。
数据卫生：只写「接线测试_INT1480R4_」前缀，脚本末尾删除并 API 复核零残留。

用法：python verify_int1480_round4_fixes.py
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
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:15284')
GATEWAY = os.environ.get('REAL_GATEWAY', 'http://127.0.0.1:15000')
USER = '接线测试_admin'
PASSWORD = 'JieXianTest@2026'
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1480_round4')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

PREFIX = '接线测试_INT1480R4_'
DEV_NAME = PREFIX + '测试设备'
DEV_SERIAL = 'JX1480R4SN01'
RULE_NAME = PREFIX + '规则'

_FAILURES = []
_NET = {}
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


def _driver():
    profile = os.path.join(os.environ.get('TEMP', '.'), 'int1480r4_chrome')
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
    d.set_page_load_timeout(60)
    d.set_script_timeout(180)
    return d


# ------------------------- 基础工具 -------------------------

def _goto(drv, path):
    last = None
    for _ in range(2):
        try:
            drv.get(BASE + path)
            WebDriverWait(drv, 40).until(
                lambda d: d.execute_script('return document.readyState') == 'complete')
            time.sleep(1.5)
            return
        except Exception as e:  # 常驻栈偶发慢响应：重试一次
            last = e
            time.sleep(2)
    raise last


def _wait_text(drv, text, timeout=20):
    WebDriverWait(drv, timeout).until(
        lambda d: text in d.execute_script('return document.body.textContent || ""'))


def _js_click(drv, el):
    drv.execute_script('arguments[0].click()', el)
    time.sleep(0.45)


def _drain_logs(drv):
    try:
        drv.get_log('browser')
        drv.get_log('performance')
    except Exception:
        pass


def _network(drv, needle):
    """performance log（双层解包）：method + url + status + postData。"""
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
            out.append({'url': url, 'method': method,
                        'status': resp.get(rid), 'postData': post})
    return out


def _probe_requests(drv, needle, method=None):
    """页内 fetch 打点（performance log 对慢 POST 偶发丢 responseReceived，以打点为状态来源）。"""
    recs = drv.execute_script('return window.__reqlog || []')
    out = []
    for r in recs:
        if needle in (r.get('url') or '') and (method is None or r.get('method') == method):
            out.append(r)
    return out


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


def _unpack(payload):
    """统一信封 {code,data} 解包。"""
    if isinstance(payload, dict) and 'data' in payload:
        return payload['data']
    return payload


def _items_of(data):
    """列表读模型 → list（dict 取 items；非 list/dict 一律空）。"""
    body = _unpack(data)
    if isinstance(body, dict):
        body = body.get('items')
    return body if isinstance(body, list) else []


def _health():
    try:
        with urllib.request.urlopen(f'{GATEWAY}/health', timeout=10) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception as e:
        return {'error': str(e)}


def _screenshot(drv, name):
    d = os.path.join(ARTIFACTS, name)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, 'screenshot.png')
    drv.save_screenshot(path)
    print(f'  [shot] {path}')
    return path


def _set_theme(drv, theme):
    drv.execute_script(
        "window.localStorage.setItem('iatp:theme:v1:mode', arguments[0])", theme)
    drv.refresh()
    WebDriverWait(drv, 30).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(2.0)


def _toast_text(drv, timeout=15):
    def find(d):
        els = d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')
        txt = ' '.join((e.text or '') for e in els).strip()
        return txt or False
    try:
        return WebDriverWait(drv, timeout).until(find)
    except Exception:
        return ''


def _click_button(drv, text, scope=None):
    root = scope or drv
    for b in root.find_elements(By.TAG_NAME, 'button'):
        try:
            if (b.text or '').strip() == text and b.is_displayed():
                _js_click(drv, b)
                return b
        except Exception:
            continue
    return None


def _click_button_contains(drv, text, scope=None):
    root = scope or drv
    for b in root.find_elements(By.TAG_NAME, 'button'):
        try:
            if text in (b.text or '') and b.is_displayed():
                _js_click(drv, b)
                return b
        except Exception:
            continue
    return None


def _visible_dialog(drv, role='dialog'):
    for d in reversed(drv.find_elements(By.XPATH, f"//*[@role='{role}']")):
        try:
            if d.is_displayed():
                return d
        except Exception:
            continue
    return None


def _label_block(label):
    return f"//div[./label[starts-with(normalize-space(.),'{label}')]]"


def _field_trigger(drv, label):
    els = drv.find_elements(By.XPATH, _label_block(label) + "//*[@data-slot='select-trigger']")
    return els[0] if els else None


def _trigger_text(el):
    vals = el.find_elements(By.CSS_SELECTOR, "[data-slot='select-value']")
    return (vals[0].text or '').strip() if vals else ''


def _select_option(drv, trigger, label):
    _js_click(drv, trigger)
    time.sleep(0.5)
    for o in drv.find_elements(By.XPATH, "//*[@role='option']"):
        try:
            if o.is_displayed() and (o.text or '').strip() == label:
                _js_click(drv, o)
                return True
        except Exception:
            continue
    return False


def _field_input(drv, label):
    els = drv.find_elements(By.XPATH, _label_block(label) + "//input")
    return els[0] if els else None


def _fill(drv, label, text):
    el = _field_input(drv, label)
    assert el is not None, f'input not found: {label}'
    el.clear()
    el.send_keys(text)
    return el


def _menu_item(drv, label, timeout=10):
    def find(d):
        for it in d.find_elements(By.XPATH, "//*[@role='menuitem']"):
            try:
                if it.is_displayed() and label == (it.text or '').strip():
                    return it
            except Exception:
                continue
        return False
    return WebDriverWait(drv, timeout).until(find)


def _open_row_actions(drv, name):
    def find_(d):
        els = d.find_elements(By.XPATH, f"//button[@aria-label='操作 {name}']")
        return els[0] if els else False
    btn = WebDriverWait(drv, 40).until(find_)
    _js_click(drv, btn)


def _wait_header(drv, text, timeout=40):
    def find_(d):
        for th in d.find_elements(By.TAG_NAME, 'th'):
            try:
                if th.is_displayed() and text in (th.text or ''):
                    return th
            except Exception:
                continue
        return False
    return WebDriverWait(drv, timeout).until(find_)


def _attr_value(drv, el, prop='value'):
    return (drv.execute_script('return arguments[0][arguments[1]] || ""', el, prop) or '').strip()


# ------------------------- 页面动作 -------------------------

def _goto_devices(drv):
    _goto(drv, '/devices/test')
    _wait_text(drv, '设备管理', 30)
    time.sleep(1.0)


def _open_drawer(drv):
    _goto_devices(drv)
    btn = _click_button(drv, '添加测试设备')
    assert btn is not None, '添加测试设备 button not found'
    _wait_text(drv, '基本信息', 25)
    WebDriverWait(drv, 25).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, "[data-slot='select-trigger']")) > 0)
    time.sleep(0.8)


def _close_sheet_or_dialog(drv):
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(1.0)


def _open_alarm_rules(drv):
    _goto_devices(drv)
    _wait_text(drv, '监控告警', 40)
    _click_button_contains(drv, '监控告警')
    time.sleep(1.2)
    btn = _click_button(drv, '告警规则')
    assert btn is not None, '告警规则 button not found'
    _wait_text(drv, '监控告警规则', 15)
    time.sleep(0.8)


def _open_operate(drv, name, item='安装应用'):
    for attempt in range(2):
        _goto_devices(drv)
        _open_row_actions(drv, name)
        try:
            mi = _menu_item(drv, item, timeout=12)
        except Exception:
            if attempt:
                raise
            drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            time.sleep(1.0)
            continue
        _js_click(drv, mi)
        time.sleep(1.0)
        return


def _online_test_device(drv):
    """安装/卸载菜单仅在线非 iOS 设备可用；新建设备恒 offline，故借真实在线设备只开弹窗、不提交。"""
    st, data = _api(drv, '/api/v1/test-devices?page=1&per_page=1000')
    for d in _items_of(data):
        system = str(d.get('system') or '')
        if d.get('status') == 'online' and 'ios' not in system.lower():
            return d.get('name')
    return None


# ------------------------- 各步骤 -------------------------

def step_preflight(drv):
    h = _health()
    _check('环境：真实库栈 /health database=intelligent_audio_test',
           h.get('database') == 'intelligent_audio_test', detail=json.dumps(h, ensure_ascii=False))
    try:
        with urllib.request.urlopen(BASE + '/', timeout=10) as r:
            html = r.read().decode('utf-8', 'ignore')
    except Exception as e:
        html = f'error {e}'
    # 被测产物 = 本 run frontend-react/dist：比对 index.html 引用的入口 chunk
    local_index = os.path.join(PROJECT_ROOT, 'frontend-react', 'dist', 'index.html')
    want = ''
    try:
        with open(local_index, encoding='utf-8') as f:
            for part in f.read().split('"'):
                if part.startswith('/static/js/index.'):
                    want = part
                    break
    except Exception:
        pass
    _NET['index_chunk'] = [s for s in html.split('"') if s.startswith('/static/js/index.')][:1]
    _check('被测前端为本 run 构建（入口 chunk 与 dist/index.html 一致）',
           bool(want) and want in html, detail=f'{want} in served html')
    _goto_devices(drv)
    _check('AUTH_MODE 直入 /devices/test 无需登录', '/devices/test' in drv.current_url,
           detail=drv.current_url)

    # 同源自查：分页条数 Select 闭合态（原显示裸 '20'）
    trig = None
    for t in drv.find_elements(
            By.XPATH, "//span[contains(normalize-space(.),'共 ') and contains(normalize-space(.),'条')]"
                      "/following-sibling::*[@data-slot='select-trigger']"):
        try:
            if t.is_displayed():
                trig = t
                break
        except Exception:
            continue
    txt = (trig.text or '').strip() if trig is not None else ''
    _check('P2-1 自查：分页条数 Select 显示「N 条/页」而非裸数字',
           '条/页' in txt, detail=f'实际={txt!r}')


def step_drawer_selects(drv):
    """P2-1 设备新建抽屉：闭合态标签 + 选项数 + 切换后标签。"""
    _open_drawer(drv)

    expect = {
        '设备类型': '真机',
        '设备系统': 'Android',
        '连接方式': 'USB连接',
    }
    got = {}
    for label, want in expect.items():
        trig = _field_trigger(drv, label)
        got[label] = _trigger_text(trig) if trig is not None else '<missing>'
        _check(f'P2-1 抽屉「{label}」闭合态 = {want}', got[label] == want,
               detail=f'实际={got[label]!r}')

    # 选项条数与文案
    trig = _field_trigger(drv, '设备类型')
    _js_click(drv, trig)
    time.sleep(0.6)
    opts = [o.text.strip() for o in drv.find_elements(By.XPATH, "//*[@role='option']")
            if o.is_displayed()]
    _check('P2-1 抽屉「设备类型」选项 3 条且为中文',
           len(opts) == 3 and '真机' in opts and 'HTTP API' in opts,
           detail=str(opts))
    for o in drv.find_elements(By.XPATH, "//*[@role='option']"):
        if o.is_displayed() and (o.text or '').strip() == 'HTTP API':
            _js_click(drv, o)
            break
    time.sleep(0.6)
    _check('P2-1 抽屉「设备类型」切换后闭合态 = HTTP API',
           _trigger_text(_field_trigger(drv, '设备类型')) == 'HTTP API',
           detail=_trigger_text(_field_trigger(drv, '设备类型')))

    # 连接方式切换 → 远程连接 + IP 字段出现
    _select_option(drv, _field_trigger(drv, '连接方式'), '远程连接')
    time.sleep(0.6)
    _check('P2-1 抽屉「连接方式」切换后闭合态 = 远程连接',
           _trigger_text(_field_trigger(drv, '连接方式')) == '远程连接',
           detail=_trigger_text(_field_trigger(drv, '连接方式')))
    _check('连接方式=远程连接 时出现 IP 地址输入',
           _field_input(drv, 'IP 地址') is not None)

    # 高级设置里的优先级（原裸值 5 与 label 相同，补 items 后仍为 5）
    _click_button(drv, '高级设置')
    time.sleep(0.5)
    _check('P2-1 自查：抽屉「优先级」闭合态 = 5',
           _trigger_text(_field_trigger(drv, '优先级')) == '5',
           detail=_trigger_text(_field_trigger(drv, '优先级')))

    # 回到真机 + USB 连接，供后续创建
    _select_option(drv, _field_trigger(drv, '设备类型'), '真机')
    _select_option(drv, _field_trigger(drv, '连接方式'), 'USB连接')
    time.sleep(0.5)

    _screenshot(drv, 'p2_1_drawer_light')
    return got


def step_create_device(drv):
    """真实创建 → GET 回读 → 证明补 items 未影响提交值。

    常驻栈 POST /test-devices 偶发数十秒才返回（后端串 device_service），故不靠 toast，
    以「请求体 + 轮询到新建行 id」为准。
    """
    st0, data0 = _api(drv, '/api/v1/test-devices?page=1&per_page=1000')
    before = {x.get('id') for x in _items_of(data0)}

    _drain_logs(drv)
    drv.execute_script('window.__reqlog = []')
    _fill(drv, '名称', DEV_NAME)
    _fill(drv, '型号', 'JX1480R4M1')
    _fill(drv, '系统版本', '12')
    _fill(drv, '应用名称', 'JXApp')
    _fill(drv, '应用版本', '1.0.0')
    _fill(drv, '设备序列号', DEV_SERIAL)
    _click_button(drv, '保存')

    row = None
    for _ in range(60):  # 最长 150s
        st, data = _api(drv, '/api/v1/test-devices?page=1&per_page=1000')
        items = _items_of(data)
        row = next((x for x in (items or [])
                    if x.get('name') == DEV_NAME and x.get('id') not in before), None)
        if row is not None:
            break
        time.sleep(2.5)
    _NET['readback_create'] = row

    net = _network(drv, '/api/v1/test-devices')
    posts = [n for n in net if n.get('method') == 'POST']
    probe_posts = _probe_requests(drv, '/api/v1/test-devices', 'POST')
    _NET['create'] = {'perf': posts[-1:] if posts else [], 'probe': probe_posts[-1:] if probe_posts else []}
    post = probe_posts[-1] if probe_posts else (posts[-1] if posts else None)
    _check('设备新建：POST /test-devices 请求体带选中值（physical / Android / usb）',
           bool(post) and '"type":"physical"' in (post.get('body') or post.get('postData') or '')
           and '"connection_type":"usb"' in (post.get('body') or post.get('postData') or '')
           and '"system":"Android"' in (post.get('body') or post.get('postData') or ''),
           detail=(post or {}).get('body') or (post or {}).get('postData') or '')
    _check('设备新建：POST 2xx（端点返回 201）',
           bool(post) and post.get('status') is not None and post.get('status') < 300,
           detail=str((post or {}).get('status')))
    _check('设备新建：GET 回读存在且字段一致',
           row is not None
           and row.get('model') == 'JX1480R4M1'
           and row.get('serial_number') == DEV_SERIAL
           and row.get('app_name') == 'JXApp',
           detail=json.dumps(row, ensure_ascii=False)[:700] if row else 'not found')
    return row


def step_operate_reset(drv):
    """P3-1 安装/卸载弹窗：填值 → Esc 取消 → 重开为空。"""
    name = _online_test_device(drv)
    _check('存在在线测试设备用于安装/卸载弹窗', name is not None, detail=str(name))
    _NET['operate_device'] = name
    if name is None:
        return
    _open_operate(drv, name, '安装应用')
    dlg = _visible_dialog(drv)
    _check('操作弹窗「安装应用」打开', dlg is not None)
    fp = drv.find_element(By.ID, 'op-file-path')
    pk = drv.find_element(By.ID, 'op-package')
    fp.send_keys('/sdcard/residue.apk')
    pk.send_keys('com.jx.residue')
    _screenshot(drv, 'p3_1_operate_light')
    _close_sheet_or_dialog(drv)
    _check('安装弹窗 Esc 关闭', _visible_dialog(drv) is None)

    _open_operate(drv, name, '安装应用')
    fp = drv.find_element(By.ID, 'op-file-path')
    pk = drv.find_element(By.ID, 'op-package')
    v1, v2 = _attr_value(drv, fp), _attr_value(drv, pk)
    _check('P3-1 安装弹窗重开后「应用安装包路径」为空', v1 == '', detail=f'实际={v1!r}')
    _check('P3-1 安装弹窗重开后「应用包名」为空', v2 == '', detail=f'实际={v2!r}')
    _close_sheet_or_dialog(drv)

    # 卸载表单同样验证，并走「取消」按钮关闭路径
    _open_operate(drv, name, '卸载应用')
    up = drv.find_element(By.ID, 'op-uninstall-package')
    up.send_keys('com.jx.residue')
    _screenshot(drv, 'p3_1_uninstall_light')
    _click_button(drv, '取消')
    time.sleep(1.0)
    _check('卸载弹窗「取消」关闭', _visible_dialog(drv) is None)
    _open_operate(drv, name, '卸载应用')
    up = drv.find_element(By.ID, 'op-uninstall-package')
    v3 = _attr_value(drv, up)
    _check('P3-1 卸载弹窗重开后「应用包名」为空', v3 == '', detail=f'实际={v3!r}')
    _close_sheet_or_dialog(drv)


def step_alarm_rules(drv):
    """P2-1 告警指标/级别闭合态 + P3-2 表头不竖排 + 真实 CRUD。"""
    _open_alarm_rules(drv)
    trig_metric = drv.find_element(By.XPATH, "//label[@for='rule-metric']/parent::div//*[@data-slot='select-trigger']")
    trig_sev = drv.find_element(By.XPATH, "//label[@for='rule-severity']/parent::div//*[@data-slot='select-trigger']")
    mt, sv = _trigger_text(trig_metric), _trigger_text(trig_sev)
    _check('P2-1 告警规则「告警指标」闭合态 = 离线时长', mt == '离线时长', detail=f'实际={mt!r}')
    _check('P2-1 告警规则「告警级别」闭合态 = 警告', sv == '警告', detail=f'实际={sv!r}')

    # 指标切换后仍显示中文 label
    _select_option(drv, trig_metric, 'CPU 使用率')
    time.sleep(0.5)
    _check('P2-1 告警规则指标切换后闭合态 = CPU 使用率',
           _trigger_text(trig_metric) == 'CPU 使用率',
           detail=_trigger_text(trig_metric))
    _select_option(drv, trig_metric, '离线时长')

    # 真实创建
    _drain_logs(drv)
    drv.find_element(By.ID, 'rule-name').send_keys(RULE_NAME)
    thr = drv.find_element(By.ID, 'rule-threshold')
    thr.clear()
    thr.send_keys('85')
    _click_button(drv, '创建规则')
    toast = _toast_text(drv, 20)
    _check('告警规则创建 toast', '已创建' in toast, detail=toast)
    net = _network(drv, '/api/v1/test-devices/alarm-rules')
    posts = [n for n in net if n.get('method') == 'POST']
    _NET['rule_create'] = posts[-1:] if posts else []
    _check('告警规则：POST /test-devices/alarm-rules 2xx',
           bool(posts) and (posts[-1].get('status') or 0) < 300,
           detail=json.dumps(posts[-1:] if posts else [], ensure_ascii=False)[:600])
    st, data = _api(drv, '/api/v1/test-devices/alarm-rules?page=1&per_page=500')
    rule = next((r for r in _items_of(data) if r.get('name') == RULE_NAME), None)
    _NET['rule_readback'] = rule
    _check('告警规则：GET 回读 metric/threshold/severity 一致',
           rule is not None and rule.get('metric_type') == 'offline_duration'
           and abs(float(rule.get('threshold_value') or 0) - 85) < 1e-6
           and rule.get('severity') == 'warning',
           detail=json.dumps(rule, ensure_ascii=False)[:500] if rule else 'not found')

    time.sleep(0.6)
    _screenshot(drv, 'p2_1_p3_2_alarm_rules_light')
    return rule


def _header_metrics(drv, dialog=None):
    """可见表格表头 [文本, clientHeight, whiteSpace, scrollWidth, clientWidth, 行盒数]。

    行盒数 = Range.getClientRects().length：单行 = 1；逐字竖排（修复前）= 每字一个行盒。
    """
    scope = dialog or drv
    out = []
    for th in scope.find_elements(By.TAG_NAME, 'th'):
        try:
            if not th.is_displayed():
                continue
            m = drv.execute_script("""
                const e = arguments[0];
                const cs = getComputedStyle(e);
                const r = document.createRange();
                r.selectNodeContents(e);
                const rects = Array.prototype.filter.call(
                    r.getClientRects(), x => x.width > 0 && x.height > 0).length;
                return [e.textContent.trim(), e.clientHeight, cs.whiteSpace,
                        e.scrollWidth, e.clientWidth, rects];
            """, th)
            out.append(m)
        except Exception:
            continue
    return out


def step_header_p3_2(drv):
    dlg = _visible_dialog(drv)
    rows = _header_metrics(drv, dlg)
    _NET['alarm_headers'] = rows
    bad = [r for r in rows
           if r[0] in ('指标', '阈值', '级别', '邮件', '启用') and (r[5] > 1 or r[2] != 'nowrap')]
    _check('P3-2 告警规则表头 指标/阈值/级别/邮件/启用 单行不竖排（nowrap & 行盒=1）',
           not bad, detail=json.dumps(rows, ensure_ascii=False))
    _check('P3-2 告警规则表头存在（5 列命中）',
           sum(1 for r in rows if r[0] in ('指标', '阈值', '级别', '邮件', '启用')) == 5,
           detail=json.dumps([r[0] for r in rows], ensure_ascii=False))

    # 数据行同样不得竖排（离线时长 / 85 分钟 / 警告）
    cells = []
    for td in dlg.find_elements(By.TAG_NAME, 'td'):
        try:
            if not td.is_displayed() or not (td.text or '').strip():
                continue
            cells.append(drv.execute_script("""
                const e = arguments[0];
                const cs = getComputedStyle(e);
                const r = document.createRange();
                r.selectNodeContents(e);
                const rects = Array.prototype.filter.call(
                    r.getClientRects(), x => x.width > 0 && x.height > 0).length;
                return [e.textContent.trim(), cs.whiteSpace, rects];
            """, td))
        except Exception:
            continue
    _NET['alarm_cells'] = cells
    # 文本单元格（徽章/按钮是 inline-flex 组件，行盒数不代表断行，排除）
    bad_cells = [c for c in cells if c[0] in ('离线时长', '85 分钟') and c[2] > 1]
    _check('P3-2 告警规则数据行 离线时长/85 分钟 文本不竖排',
           not bad_cells, detail=json.dumps(cells, ensure_ascii=False))

    # 测试设备列表「提示词」列
    _close_sheet_or_dialog(drv)
    _goto_devices(drv)
    _wait_header(drv, '提示词')
    time.sleep(0.5)
    rows = _header_metrics(drv)
    _NET['device_headers'] = rows
    tgt = next((r for r in rows if '提示词' in r[0]), None)
    _check('P3-2 测试设备表「提示词」表头单行（行盒=1、列宽容纳三字）',
           tgt is not None and tgt[5] <= 1 and tgt[3] <= tgt[4],
           detail=json.dumps(tgt, ensure_ascii=False))
    _screenshot(drv, 'p3_2_device_table_light')


def step_dark_screenshots(drv):
    _set_theme(drv, 'dark')
    _open_drawer(drv)
    got = {k: _trigger_text(_field_trigger(drv, k)) for k in ('设备类型', '设备系统', '连接方式')}
    _check('P2-1 深色：抽屉 Select 闭合态仍为中文 label',
           got == {'设备类型': '真机', '设备系统': 'Android', '连接方式': 'USB连接'},
           detail=json.dumps(got, ensure_ascii=False))
    _screenshot(drv, 'p2_1_drawer_dark')
    _close_sheet_or_dialog(drv)

    _open_operate(drv, _NET.get('operate_device') or DEV_NAME, '安装应用')
    fp = drv.find_element(By.ID, 'op-file-path')
    _check('P3-1 深色：重开安装弹窗为空', _attr_value(drv, fp) == '')
    _screenshot(drv, 'p3_1_operate_dark')
    _close_sheet_or_dialog(drv)

    _open_alarm_rules(drv)
    trig_metric = drv.find_element(By.XPATH, "//label[@for='rule-metric']/parent::div//*[@data-slot='select-trigger']")
    _check('P2-1 深色：告警指标闭合态 = 离线时长', _trigger_text(trig_metric) == '离线时长',
           detail=_trigger_text(trig_metric))
    rows = _header_metrics(drv, _visible_dialog(drv))
    bad = [r for r in rows
           if r[0] in ('指标', '阈值', '级别', '邮件', '启用') and (r[5] > 1 or r[2] != 'nowrap')]
    _check('P3-2 深色：告警规则表头单行', not bad, detail=json.dumps(rows, ensure_ascii=False))
    _screenshot(drv, 'p2_1_p3_2_alarm_rules_dark')
    _close_sheet_or_dialog(drv)

    _goto_devices(drv)
    _wait_header(drv, '提示词')
    rows = _header_metrics(drv)
    tgt = next((r for r in rows if '提示词' in r[0]), None)
    _check('P3-2 深色：测试设备表「提示词」表头单行',
           tgt is not None and tgt[5] <= 1, detail=json.dumps(tgt, ensure_ascii=False))
    _screenshot(drv, 'p3_2_device_table_dark')


def step_cleanup(drv):
    """删除「接线测试_INT1480R4_」数据并 API 复核零残留。"""
    _drain_logs(drv)
    # 告警规则
    _open_alarm_rules(drv)
    try:
        btn = drv.find_element(By.XPATH, f"//button[@aria-label='删除规则 {RULE_NAME}']")
        _js_click(drv, btn)
        time.sleep(1.2)
        ad = _visible_dialog(drv, 'alertdialog')
        if ad is not None:
            _click_button(drv, '删除', ad)
        time.sleep(1.5)
    except Exception as e:
        print('rule cleanup:', e)
    _close_sheet_or_dialog(drv)

    # 设备
    _goto_devices(drv)
    try:
        _open_row_actions(drv, DEV_NAME)
        mi = _menu_item(drv, '删除')
        _js_click(drv, mi)
        time.sleep(1.2)
        ad = _visible_dialog(drv, 'alertdialog')
        if ad is not None:
            _click_button(drv, '删除', ad)
        time.sleep(2.0)
    except Exception as e:
        print('device cleanup:', e)

    st, data = _api(drv, '/api/v1/test-devices?page=1&per_page=1000')
    items = _items_of(data)
    st2, data2 = _api(drv, '/api/v1/test-devices/alarm-rules?page=1&per_page=500')
    rules = _items_of(data2)
    left_dev = [x.get('name') for x in items if str(x.get('name', '')).startswith(PREFIX)]
    left_rule = [r.get('name') for r in rules if str(r.get('name', '')).startswith(PREFIX)]

    # 兜底清扫（仅本卡前缀），覆盖 UI 删除失败/中断重跑的残留
    for x in items:
        if str(x.get('name', '')).startswith(PREFIX):
            _api(drv, f"/api/v1/test-devices/{x.get('id')}", 'DELETE')
    for r in rules:
        if str(r.get('name', '')).startswith(PREFIX):
            _api(drv, f"/api/v1/test-devices/alarm-rules/{r.get('id')}", 'DELETE')
    if left_dev or left_rule:
        time.sleep(1.5)
        st, data = _api(drv, '/api/v1/test-devices?page=1&per_page=1000')
        st2, data2 = _api(drv, '/api/v1/test-devices/alarm-rules?page=1&per_page=500')
        left_dev = [x.get('name') for x in _items_of(data)
                    if str(x.get('name', '')).startswith(PREFIX)]
        left_rule = [r.get('name') for r in _items_of(data2)
                     if str(r.get('name', '')).startswith(PREFIX)]

    _NET['cleanup'] = {'devices': left_dev, 'rules': left_rule}
    _check('数据卫生：设备零残留', not left_dev, detail=str(left_dev))
    _check('数据卫生：告警规则零残留', not left_rule, detail=str(left_rule))

    console = drv.get_log('browser')
    severe = [c for c in console if c.get('level') == 'SEVERE']
    _check('控制台无 SEVERE', not severe, detail=json.dumps(severe[:3], ensure_ascii=False)[:800])


def _run_step(name, fn, *args):
    print(f'== {name} ==')
    try:
        return fn(*args)
    except Exception as e:
        import traceback
        traceback.print_exc()
        _check(f'步骤异常：{name}', False, detail=repr(e)[:300])
        return None


def main():
    os.makedirs(ARTIFACTS, exist_ok=True)
    drv = _driver()
    try:
        _run_step('环境', step_preflight, drv)
        _run_step('P2-1 设备抽屉', step_drawer_selects, drv)
        _run_step('设备新建闭环', step_create_device, drv)
        _run_step('P3-1 安装/卸载重开残留', step_operate_reset, drv)
        _run_step('P2-1/P3-2 告警规则', step_alarm_rules, drv)
        _run_step('P3-2 表头（告警规则 + 设备表）', step_header_p3_2, drv)
        _run_step('深色复拍', step_dark_screenshots, drv)
        _run_step('清理', step_cleanup, drv)
    finally:
        with open(os.path.join(ARTIFACTS, 'network_evidence.json'), 'w', encoding='utf-8') as f:
            json.dump(_NET, f, ensure_ascii=False, indent=2, default=str)
        print('\nNETWORK EVIDENCE ->', os.path.join(ARTIFACTS, 'network_evidence.json'))
        print('FAILURES:', _FAILURES if _FAILURES else 'none')
        try:
            drv.quit()
        except Exception:
            pass
    return 1 if _FAILURES else 0


if __name__ == '__main__':
    sys.exit(main())
