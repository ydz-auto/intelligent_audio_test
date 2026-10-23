# -*- coding: utf-8 -*-
"""INT-1480 第四轮返工复测（测试工程师侧，独立脚本）。

复测对象 = 前端UX审计打回的三项 + 其回归面：
  P2-1 base-ui Select 闭合态显示原始 value → 应显示中文 label（设备抽屉 / 告警规则 / 告警面板筛选 / 分页条数）
  P3-1 安装·卸载弹窗关闭后重开残留上次输入 → 每次打开为空
  P3-2 表头逐字竖排 → 告警规则表 5 列表头 + 设备表「提示词」单选行

A/B 用法（同一脚本两侧跑，证明区分力）：
  INT1480_BASE=http://127.0.0.1:15248 INT1480_TAG=R4V INT1480_CHUNK=index.d23fe9da60.js python verify_int1480_round4_retest.py
  INT1480_BASE=http://127.0.0.1:15173 INT1480_TAG=R4O INT1480_CHUNK=index.8a1076e8bb.js python verify_int1480_round4_retest.py

环境：后端 docker 真实库栈 :15000（/health database=intelligent_audio_test）。
数据卫生：只写「接线测试_INT1480R4<TAG>_」前缀，结束前删除并 API 复核零残留。
"""
import functools
import json
import os
import sys
import time
import urllib.request

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

BASE = os.environ.get('INT1480_BASE', 'http://127.0.0.1:15248')
GATEWAY = os.environ.get('INT1480_GATEWAY', 'http://127.0.0.1:15000')
TAG = os.environ.get('INT1480_TAG', 'R4V')
EXPECT_CHUNK = os.environ.get('INT1480_CHUNK', 'index.d23fe9da60.js')
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1480_round4_retest', TAG)
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

PREFIX = f'接线测试_INT1480R4{TAG}_'
DEV_NAME = PREFIX + '设备'
DEV_MODEL = 'R4M-' + TAG
DEV_SERIAL = 'JXR4SN' + TAG
RULE_NAME = PREFIX + '规则'

_FAIL = []
_OK = []
_NET = {}


def _check(name, cond, detail=''):
    print(f'[{"PASS" if cond else "FAIL"}] {name}' + (f' — {detail}' if detail else ''))
    (_OK if cond else _FAIL).append(name)


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
    o = Options()
    o.binary_location = CHROME_BINARY
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1050')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    p = _chromedriver()
    d = webdriver.Chrome(options=o, service=Service(executable_path=p) if p else Service())
    d.set_page_load_timeout(60)
    d.set_script_timeout(180)
    return d


def _goto(drv, path):
    last = None
    for _ in range(2):
        try:
            drv.get(BASE + path)
            WebDriverWait(drv, 40).until(
                lambda d: d.execute_script('return document.readyState') == 'complete')
            time.sleep(1.5)
            return
        except Exception as e:
            last = e
            time.sleep(2)
    raise last


def _body(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _wait_text(drv, text, timeout=25):
    WebDriverWait(drv, timeout).until(lambda d: text in _body(d))


def _js_click(drv, el):
    drv.execute_script('arguments[0].click()', el)
    time.sleep(0.45)


def _network(drv, needle):
    """performance log（双层解包）：method/url/status/postData。"""
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


def _items_of(payload):
    body = payload.get('data') if isinstance(payload, dict) and 'data' in payload else payload
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
    drv.execute_script("window.localStorage.setItem('iatp:theme:v1:mode', arguments[0])", theme)
    drv.refresh()
    WebDriverWait(drv, 35).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(2.0)


def _click_button(drv, text, scope=None):
    for b in (scope or drv).find_elements(By.TAG_NAME, 'button'):
        try:
            if (b.text or '').strip() == text and b.is_displayed():
                _js_click(drv, b)
                return b
        except Exception:
            continue
    return None


def _click_button_contains(drv, text, scope=None):
    for b in (scope or drv).find_elements(By.TAG_NAME, 'button'):
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


def _open_select_options(drv, trigger):
    _js_click(drv, trigger)
    time.sleep(0.6)
    return [o for o in drv.find_elements(By.XPATH, "//*[@role='option']") if o.is_displayed()]


def _select_option(drv, trigger, label):
    for o in _open_select_options(drv, trigger):
        if (o.text or '').strip() == label:
            _js_click(drv, o)
            time.sleep(0.5)
            return True
    # 关掉误开的弹层
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(0.5)
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


def _menu_item(drv, label, timeout=12):
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
    def find(d):
        els = d.find_elements(By.XPATH, f"//button[@aria-label='操作 {name}']")
        return els[0] if els else False
    _js_click(drv, WebDriverWait(drv, 40).until(find))


def _header_metrics(drv, scope=None):
    """可见表头 [文本, clientHeight, whiteSpace, scrollWidth, clientWidth, 行盒数]。"""
    out = []
    for th in (scope or drv).find_elements(By.TAG_NAME, 'th'):
        try:
            if not th.is_displayed():
                continue
            out.append(drv.execute_script("""
                const e = arguments[0]; const cs = getComputedStyle(e);
                const r = document.createRange(); r.selectNodeContents(e);
                const rects = Array.prototype.filter.call(
                    r.getClientRects(), x => x.width > 0 && x.height > 0).length;
                return [e.textContent.trim(), e.clientHeight, cs.whiteSpace,
                        e.scrollWidth, e.clientWidth, rects];
            """, th))
        except Exception:
            continue
    return out


def _attr(drv, el, prop='value'):
    return (drv.execute_script('return arguments[0][arguments[1]] || ""', el, prop) or '').strip()


def _goto_devices(drv):
    _goto(drv, '/devices/test')
    _wait_text(drv, '设备管理', 35)
    time.sleep(1.2)


def _open_drawer(drv):
    _goto_devices(drv)
    assert _click_button(drv, '添加测试设备') is not None, '添加测试设备 not found'
    _wait_text(drv, '基本信息', 25)
    WebDriverWait(drv, 25).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, "[data-slot='select-trigger']")) > 0)
    time.sleep(0.8)


def _close_dialog(drv):
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(1.0)


def _open_alarm_rules(drv):
    _goto_devices(drv)
    if _click_button_contains(drv, '监控告警') is None:
        raise AssertionError('监控告警 switch not found')
    time.sleep(1.2)
    assert _click_button(drv, '告警规则') is not None, '告警规则 not found'
    _wait_text(drv, '监控告警规则', 20)
    time.sleep(0.8)


def _open_operate(drv, name, item):
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


def _online_device(drv):
    st, data = _api(drv, '/api/v1/test-devices?page=1&per_page=1000')
    for d in _items_of(data):
        if d.get('status') == 'online' and 'ios' not in str(d.get('system') or '').lower():
            return d.get('name')
    return None


# ------------------------------ steps ------------------------------

def step_preflight(drv):
    h = _health()
    _check('环境：真实库栈 database=intelligent_audio_test',
           h.get('database') == 'intelligent_audio_test', json.dumps(h, ensure_ascii=False)[:200])
    html = urllib.request.urlopen(BASE + '/', timeout=15).read().decode('utf-8', 'ignore')
    chunks = [s for s in html.split('"') if s.startswith('/static/js/index.')]
    _check(f'被测前端入口 chunk = {EXPECT_CHUNK}', any(EXPECT_CHUNK in c for c in chunks),
           str(chunks[:2]))
    _goto_devices(drv)
    _check('AUTH_MODE 直入 /devices/test', '/devices/test' in drv.current_url, drv.current_url)


def step_drawer(drv):
    _open_drawer(drv)
    expect = {'设备类型': '真机', '设备系统': 'Android', '连接方式': 'USB连接'}
    got = {}
    for label, want in expect.items():
        trig = _field_trigger(drv, label)
        got[label] = _trigger_text(trig) if trig is not None else '<missing>'
        _check(f'P2-1 抽屉「{label}」闭合态 = {want}', got[label] == want, repr(got[label]))
    _NET['drawer_closed'] = got

    trig = _field_trigger(drv, '设备类型')
    opts = [o.text.strip() for o in _open_select_options(drv, trig)]
    _check('P2-1「设备类型」选项 3 条且中文',
           len(opts) == 3 and set(opts) == {'真机', 'HTTP API', 'Realtime WS'}, str(opts))
    for o in opts:
        pass
    # 选 HTTP API
    for o in drv.find_elements(By.XPATH, "//*[@role='option']"):
        if o.is_displayed() and (o.text or '').strip() == 'HTTP API':
            _js_click(drv, o)
            break
    time.sleep(0.5)
    t = _trigger_text(_field_trigger(drv, '设备类型'))
    _check('P2-1「设备类型」切换后闭合态 = HTTP API', t == 'HTTP API', repr(t))

    ctrig = _field_trigger(drv, '连接方式')
    opts2 = [o.text.strip() for o in _open_select_options(drv, ctrig)]
    _check('P2-1「连接方式」选项 2 条', set(opts2) == {'USB连接', '远程连接'}, str(opts2))
    for o in drv.find_elements(By.XPATH, "//*[@role='option']"):
        if o.is_displayed() and (o.text or '').strip() == '远程连接':
            _js_click(drv, o)
            break
    time.sleep(0.6)
    t2 = _trigger_text(_field_trigger(drv, '连接方式'))
    _check('P2-1「连接方式」切换后闭合态 = 远程连接', t2 == '远程连接', repr(t2))
    _check('连接方式=远程连接 出现 IP 地址输入', _field_input(drv, 'IP 地址') is not None)

    # 复位为真机/USB，供后续创建
    _select_option(drv, _field_trigger(drv, '设备类型'), '真机')
    _select_option(drv, _field_trigger(drv, '连接方式'), 'USB连接')
    _click_button(drv, '高级设置')
    time.sleep(0.5)
    pri = _trigger_text(_field_trigger(drv, '优先级')) if _field_trigger(drv, '优先级') else ''
    _check('P2-1「优先级」闭合态 = 5', pri == '5', repr(pri))
    _screenshot(drv, 'p2_1_drawer_light')


def step_create(drv):
    st0, d0 = _api(drv, '/api/v1/test-devices?page=1&per_page=1000')
    before = {x.get('id') for x in _items_of(d0)}
    drv.execute_script('return 0')
    try:
        drv.get_log('performance')
    except Exception:
        pass
    for label, val in (('名称', DEV_NAME), ('型号', DEV_MODEL), ('系统版本', '12'),
                       ('应用名称', 'JXApp'), ('应用版本', '1.0.0'), ('设备序列号', DEV_SERIAL)):
        try:
            _fill(drv, label, val)
        except AssertionError as e:
            print('field missing:', e)
    _click_button(drv, '保存')
    row = None
    for _ in range(45):
        st, data = _api(drv, '/api/v1/test-devices?page=1&per_page=1000')
        row = next((x for x in _items_of(data)
                    if x.get('name') == DEV_NAME and x.get('id') not in before), None)
        if row is not None:
            break
        time.sleep(2.0)
    _NET['created'] = row
    posts = [n for n in _network(drv, '/api/v1/test-devices') if n.get('method') == 'POST']
    post = posts[-1] if posts else {}
    _NET['create_post'] = post
    body = post.get('postData') or ''
    _check('提交完整性：POST 请求体仍为 physical/Android/usb',
           '"type":"physical"' in body and '"system":"Android"' in body
           and '"connection_type":"usb"' in body, body[:400])
    # 15000 网关偶发 504（已知 SSE 线程池耗尽）：以「请求体正确 + GET 回读存在」为落库判据，
    # 状态码 504 只记环境注记，不作为本卡缺陷。
    st_code = post.get('status')
    _check('提交完整性：设备已落库（POST 2xx 或网关 504 但 GET 可读到新行）',
           (st_code is not None and st_code < 300) or row is not None,
           f'status={st_code} row={"yes" if row else "no"}')
    if st_code is not None and st_code >= 500:
        _NET['env_note_post_5xx'] = st_code
    _check('GET 回读：名称/型号/序列号一致',
           row is not None and row.get('model') == DEV_MODEL and row.get('serial_number') == DEV_SERIAL,
           json.dumps(row, ensure_ascii=False)[:400] if row else 'not found')
    return row


def step_edit_prefill(drv):
    """编辑回填时闭合态也应是中文 label（P2-1 的直接场景）。"""
    try:
        _goto_devices(drv)
        _open_row_actions(drv, DEV_NAME)
        _js_click(drv, _menu_item(drv, '编辑'))
        _wait_text(drv, '基本信息', 25)
        time.sleep(1.0)
        got = {k: _trigger_text(_field_trigger(drv, k))
               for k in ('设备类型', '设备系统', '连接方式')}
        _NET['edit_closed'] = got
        _check('P2-1 编辑回填闭合态 = 真机/Android/USB连接',
               got == {'设备类型': '真机', '设备系统': 'Android', '连接方式': 'USB连接'},
               json.dumps(got, ensure_ascii=False))
        _screenshot(drv, 'p2_1_edit_light')
        _close_dialog(drv)
    except Exception as e:
        _check('P2-1 编辑回填检查', False, repr(e)[:200])


def step_pagination_and_alarm_filters(drv):
    _goto_devices(drv)
    trig = None
    for t in drv.find_elements(
            By.XPATH, "//span[contains(normalize-space(.),'共 ') and contains(normalize-space(.),'条')]"
                      "/following-sibling::*[@data-slot='select-trigger']"):
        if t.is_displayed():
            trig = t
            break
    txt = (trig.text or '').strip() if trig is not None else ''
    _check('P2-1 分页条数闭合态含「条/页」', '条/页' in txt, repr(txt))

    if _click_button_contains(drv, '监控告警') is None:
        _check('打开监控告警面板', False)
        return
    time.sleep(1.5)
    vals = [v.text.strip() for v in drv.find_elements(By.CSS_SELECTOR, "[data-slot='select-value']")
            if v.is_displayed()]
    _NET['alarm_filter_values'] = vals
    _check('P2-1 告警面板筛选闭合态无裸枚举（无 all/offline 等）',
           not any(v in ('all', 'active', 'offline_duration', 'warning') for v in vals), str(vals))
    _check('P2-1 告警面板筛选闭合态含「全部状态」「全部级别」',
           '全部状态' in vals and '全部级别' in vals, str(vals))
    _screenshot(drv, 'p2_1_alarm_panel_light')


def step_operate(drv):
    name = _online_device(drv)
    _NET['operate_device'] = name
    _check('借到在线测试设备用于安装/卸载弹窗', name is not None, str(name))
    if name is None:
        return
    _open_operate(drv, name, '安装应用')
    _check('安装应用弹窗打开', _visible_dialog(drv) is not None)
    fp = drv.find_element(By.ID, 'op-file-path')
    pk = drv.find_element(By.ID, 'op-package')
    fp.send_keys('/sdcard/residue.apk')
    pk.send_keys('com.jx.residue')
    _screenshot(drv, 'p3_1_install_light')
    _close_dialog(drv)
    _check('安装弹窗 Esc 关闭', _visible_dialog(drv) is None)

    _open_operate(drv, name, '安装应用')
    v1 = _attr(drv, drv.find_element(By.ID, 'op-file-path'))
    v2 = _attr(drv, drv.find_element(By.ID, 'op-package'))
    _check('P3-1 安装弹窗重开：应用安装包路径为空', v1 == '', repr(v1))
    _check('P3-1 安装弹窗重开：应用包名为空', v2 == '', repr(v2))
    _close_dialog(drv)

    _open_operate(drv, name, '卸载应用')
    up = drv.find_element(By.ID, 'op-uninstall-package')
    up.send_keys('com.jx.residue')
    _screenshot(drv, 'p3_1_uninstall_light')
    _click_button(drv, '取消')
    time.sleep(1.0)
    _check('卸载弹窗「取消」关闭', _visible_dialog(drv) is None)
    _open_operate(drv, name, '卸载应用')
    v3 = _attr(drv, drv.find_element(By.ID, 'op-uninstall-package'))
    _check('P3-1 卸载弹窗重开：应用包名为空', v3 == '', repr(v3))
    _close_dialog(drv)


def _open_operate_inplace(drv, name, item):
    """同页重开（不导航，避免整页 reload 把表单状态顺带清掉，令 P3-1 假通过）。"""
    _open_row_actions(drv, name)
    _js_click(drv, _menu_item(drv, item))
    time.sleep(1.0)


def step_operate_inplace(drv):
    """P3-1 严格复测：同一页面实例内关闭→重开，验证 reset 是否生效。"""
    name = _online_device(drv)
    _check('P3-1 借到在线测试设备', name is not None, str(name))
    if name is None:
        return
    _goto_devices(drv)
    _open_operate_inplace(drv, name, '安装应用')
    drv.find_element(By.ID, 'op-file-path').send_keys('/sdcard/residue.apk')
    drv.find_element(By.ID, 'op-package').send_keys('com.jx.residue')
    _screenshot(drv, 'p3_1_install_light_inplace')
    _close_dialog(drv)
    _check('P3-1 安装弹窗 Esc 关闭（未导航）', _visible_dialog(drv) is None)
    _open_operate_inplace(drv, name, '安装应用')
    v1 = _attr(drv, drv.find_element(By.ID, 'op-file-path'))
    v2 = _attr(drv, drv.find_element(By.ID, 'op-package'))
    _check('P3-1 同页重开安装弹窗：路径为空', v1 == '', repr(v1))
    _check('P3-1 同页重开安装弹窗：包名为空', v2 == '', repr(v2))
    _screenshot(drv, 'p3_1_install_reopen_light')
    _close_dialog(drv)

    _open_operate_inplace(drv, name, '卸载应用')
    drv.find_element(By.ID, 'op-uninstall-package').send_keys('com.jx.residue')
    _click_button(drv, '取消')
    time.sleep(1.0)
    _check('P3-1 卸载弹窗「取消」关闭（未导航）', _visible_dialog(drv) is None)
    _open_operate_inplace(drv, name, '卸载应用')
    v3 = _attr(drv, drv.find_element(By.ID, 'op-uninstall-package'))
    _check('P3-1 同页重开卸载弹窗：包名为空', v3 == '', repr(v3))
    _screenshot(drv, 'p3_1_uninstall_reopen_light')
    _close_dialog(drv)


def step_alarm_rules(drv):
    _open_alarm_rules(drv)
    tm = drv.find_element(By.XPATH, "//label[@for='rule-metric']/parent::div//*[@data-slot='select-trigger']")
    ts = drv.find_element(By.XPATH, "//label[@for='rule-severity']/parent::div//*[@data-slot='select-trigger']")
    mt, sv = _trigger_text(tm), _trigger_text(ts)
    _check('P2-1 告警规则「告警指标」闭合态 = 离线时长', mt == '离线时长', repr(mt))
    _check('P2-1 告警规则「告警级别」闭合态 = 警告', sv == '警告', repr(sv))
    _NET['rule_closed'] = {'metric': mt, 'severity': sv}

    _select_option(drv, tm, 'CPU 使用率')
    mt2 = _trigger_text(tm)
    _check('P2-1 告警指标切换后闭合态 = CPU 使用率', mt2 == 'CPU 使用率', repr(mt2))
    _select_option(drv, tm, '离线时长')

    drv.find_element(By.ID, 'rule-name').send_keys(RULE_NAME)
    thr = drv.find_element(By.ID, 'rule-threshold')
    thr.clear()
    thr.send_keys('85')
    _click_button(drv, '创建规则')
    time.sleep(2.5)
    posts = [n for n in _network(drv, '/api/v1/test-devices/alarm-rules') if n.get('method') == 'POST']
    post = posts[-1] if posts else {}
    _NET['rule_post'] = post
    _check('告警规则：POST 2xx', post.get('status') is not None and post.get('status') < 300,
           json.dumps(post, ensure_ascii=False)[:400])
    rule = None
    for _ in range(15):
        st, data = _api(drv, '/api/v1/test-devices/alarm-rules?page=1&per_page=500')
        rule = next((r for r in _items_of(data) if r.get('name') == RULE_NAME), None)
        if rule:
            break
        time.sleep(1.2)
    _NET['rule_readback'] = rule
    _check('告警规则：GET 回读 metric=offline_duration / threshold=85 / severity=warning',
           rule is not None and rule.get('metric_type') == 'offline_duration'
           and abs(float(rule.get('threshold_value') or 0) - 85) < 1e-6
           and rule.get('severity') == 'warning',
           json.dumps(rule, ensure_ascii=False)[:400] if rule else 'not found')

    time.sleep(0.8)
    dlg = _visible_dialog(drv)
    rows = _header_metrics(drv, dlg)
    _NET['alarm_headers'] = rows
    target = ('指标', '阈值', '级别', '邮件', '启用')
    hit = [r for r in rows if r[0] in target]
    bad = [r for r in hit if r[5] > 1 or r[2] != 'nowrap']
    _check('P3-2 告警规则表头 5 列命中', len(hit) == 5, str([r[0] for r in hit]))
    _check('P3-2 告警规则表头 5 列单行（行盒=1 且 white-space:nowrap）', not bad,
           json.dumps(rows, ensure_ascii=False)[:700])
    _screenshot(drv, 'p2_1_p3_2_alarm_rules_light')
    _close_dialog(drv)


def step_device_table_header(drv):
    _goto_devices(drv)
    WebDriverWait(drv, 35).until(
        lambda d: any('提示词' in (th.text or '') and th.is_displayed()
                      for th in d.find_elements(By.TAG_NAME, 'th')))
    rows = _header_metrics(drv)
    tgt = next((r for r in rows if '提示词' in r[0]), None)
    _NET['device_headers'] = rows
    _check('P3-2 设备表「提示词」表头单行（行盒=1）',
           tgt is not None and tgt[5] <= 1, json.dumps(tgt, ensure_ascii=False) if tgt else 'missing')
    _screenshot(drv, 'p3_2_device_table_light')


def step_dark(drv):
    _set_theme(drv, 'dark')
    _open_drawer(drv)
    got = {k: _trigger_text(_field_trigger(drv, k)) for k in ('设备类型', '设备系统', '连接方式')}
    _check('深色：抽屉闭合态仍为中文 label',
           got == {'设备类型': '真机', '设备系统': 'Android', '连接方式': 'USB连接'},
           json.dumps(got, ensure_ascii=False))
    _screenshot(drv, 'p2_1_drawer_dark')
    _close_dialog(drv)

    name = _NET.get('operate_device')
    if name:
        _open_operate(drv, name, '安装应用')
        v = _attr(drv, drv.find_element(By.ID, 'op-file-path'))
        _check('深色：重开安装弹窗为空', v == '', repr(v))
        _screenshot(drv, 'p3_1_install_dark')
        _close_dialog(drv)

    _open_alarm_rules(drv)
    tm = drv.find_element(By.XPATH, "//label[@for='rule-metric']/parent::div//*[@data-slot='select-trigger']")
    _check('深色：告警指标闭合态 = 离线时长', _trigger_text(tm) == '离线时长', _trigger_text(tm))
    rows = _header_metrics(drv, _visible_dialog(drv))
    bad = [r for r in rows if r[0] in ('指标', '阈值', '级别', '邮件', '启用') and r[5] > 1]
    _check('深色：告警规则表头单行', not bad, json.dumps(rows, ensure_ascii=False)[:600])
    _screenshot(drv, 'p2_1_p3_2_alarm_rules_dark')
    _close_dialog(drv)

    _goto_devices(drv)
    rows = _header_metrics(drv)
    tgt = next((r for r in rows if '提示词' in r[0]), None)
    _check('深色：设备表「提示词」表头单行', tgt is not None and tgt[5] <= 1,
           json.dumps(tgt, ensure_ascii=False) if tgt else 'missing')
    _screenshot(drv, 'p3_2_device_table_dark')
    _set_theme(drv, 'light')


def step_cleanup(drv):
    _open_alarm_rules(drv)
    try:
        _js_click(drv, drv.find_element(By.XPATH, f"//button[@aria-label='删除规则 {RULE_NAME}']"))
        time.sleep(1.2)
        ad = _visible_dialog(drv, 'alertdialog')
        if ad is not None:
            _click_button(drv, '删除', ad)
        time.sleep(1.5)
    except Exception as e:
        print('rule cleanup:', repr(e)[:200])
    _close_dialog(drv)

    _goto_devices(drv)
    try:
        _open_row_actions(drv, DEV_NAME)
        _js_click(drv, _menu_item(drv, '删除'))
        time.sleep(1.2)
        ad = _visible_dialog(drv, 'alertdialog')
        if ad is not None:
            _click_button(drv, '删除', ad)
        time.sleep(2.0)
    except Exception as e:
        print('device cleanup:', repr(e)[:200])

    # 兜底：按前缀 API 清扫
    st, data = _api(drv, '/api/v1/test-devices?page=1&per_page=1000')
    for x in _items_of(data):
        if str(x.get('name', '')).startswith(PREFIX):
            _api(drv, f"/api/v1/test-devices/{x.get('id')}", 'DELETE')
    st, data = _api(drv, '/api/v1/test-devices/alarm-rules?page=1&per_page=500')
    for r in _items_of(data):
        if str(r.get('name', '')).startswith(PREFIX):
            _api(drv, f"/api/v1/test-devices/alarm-rules/{r.get('id')}", 'DELETE')
    time.sleep(2.0)
    st, data = _api(drv, '/api/v1/test-devices?page=1&per_page=1000')
    left_dev = [x.get('name') for x in _items_of(data) if str(x.get('name', '')).startswith(PREFIX)]
    total_dev = (data.get('data') or {}).get('total') if isinstance(data, dict) else None
    st2, data2 = _api(drv, '/api/v1/test-devices/alarm-rules?page=1&per_page=500')
    left_rule = [r.get('name') for r in _items_of(data2) if str(r.get('name', '')).startswith(PREFIX)]
    _NET['cleanup'] = {'devices': left_dev, 'rules': left_rule, 'device_total': total_dev}
    _check('数据卫生：设备零残留', not left_dev, str(left_dev))
    _check('数据卫生：告警规则零残留', not left_rule, str(left_rule))

    severe = [c for c in drv.get_log('browser') if c.get('level') == 'SEVERE']
    _check('控制台无 SEVERE', not severe, json.dumps(severe[:3], ensure_ascii=False)[:600])


def _run(name, fn, drv):
    print(f'== {name} ==')
    try:
        return fn(drv)
    except Exception as e:
        import traceback
        traceback.print_exc()
        _check(f'步骤异常：{name}', False, repr(e)[:300])


def main():
    os.makedirs(ARTIFACTS, exist_ok=True)
    print(f'BASE={BASE} TAG={TAG} EXPECT={EXPECT_CHUNK} PREFIX={PREFIX}')
    steps = [s.strip() for s in os.environ.get('INT1480_STEPS', '').split(',') if s.strip()] or None
    drv = _driver()
    try:
        for name, fn in (('preflight', step_preflight), ('drawer', step_drawer),
                         ('create', step_create), ('edit', step_edit_prefill),
                         ('filters', step_pagination_and_alarm_filters),
                         ('operate', step_operate), ('operate_inplace', step_operate_inplace),
                         ('alarm', step_alarm_rules),
                         ('table', step_device_table_header), ('dark', step_dark),
                         ('cleanup', step_cleanup)):
            if steps and name not in steps:
                continue
            _run(name, fn, drv)
    finally:
        with open(os.path.join(ARTIFACTS, 'evidence.json'), 'w', encoding='utf-8') as f:
            json.dump({'ok': _OK, 'fail': _FAIL, 'net': _NET}, f, ensure_ascii=False,
                      indent=2, default=str)
        print(f'\nPASS {len(_OK)} / FAIL {len(_FAIL)}')
        if _FAIL:
            for f_ in _FAIL:
                print(' -', f_)
        try:
            drv.quit()
        except Exception:
            pass
    return 1 if _FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
