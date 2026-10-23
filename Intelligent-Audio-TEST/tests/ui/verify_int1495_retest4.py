# -*- coding: utf-8 -*-
"""INT-1495 复测第 4 轮（测试工程师）——只复测代码审计打回项 P2-A / P3-a / P3-b。

被测：交付分支 agent/react-b/int-1495-77cdf409df78 @ 85a66fc5（本 run worktree 已 merge）。
环境（铁律走 docker）：
  前端 = 本 run worktree `pnpm build` 产物旁路容器 http://127.0.0.1:15498
         （iat-react-frontend:latest nginx，/api/ → api_gateway:5000，网络 intelligent-audio-test_default）
  后端 = http://127.0.0.1:15000（真实库 intelligent_audio_test，AUTH_MODE=off）
验收点：
  P2-A 实验室删除失败（真实 404）→ 提示后端文案、不出「实验室已删除」、确认框保持；
       成功（真实 200）→ 「实验室已删除」+ 行消失 + GET 回读无。
  P3-a API 健康检查一次点击只一条 toast（真实 POST /apis/1/health 200）。
  P3-b 播放测试真实失败（真实 400）→ 错误 toast，且「测试中」占用徽章回滚不残留。
唯一合成点（显式标注）：真实库 API/播放设备全部 offline，行菜单按离线禁用无法点击，
故页内 fetch 打点把 /apis、/playback-devices 列表响应的 status 改写成 online（synthetic online），
失败与成功响应全部来自真实后端，不伪造状态码。

测试数据：实验室一律「接线测试_INT1495V4_」前缀，脚本内删除并 GET 复核零残留。
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

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15498')
GATEWAY = os.environ.get('REAL_GATEWAY', 'http://127.0.0.1:15000')
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1495_v4')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

LAB_FAIL_NAME = '接线测试_INT1495V4_删除失败'
LAB_FAIL_CODE = 'JX1495V4A'
LAB_OK_NAME = '接线测试_INT1495V4_删除成功'
LAB_OK_CODE = 'JX1495V4B'
LAB_DARK_NAME = '接线测试_INT1495V4_深色失败'
LAB_DARK_CODE = 'JX1495V4C'
TEMP_PB_NAME = '接线测试_INT1495V4_临时播放'

_FAILURES = []
_COMPARE = {}
print = functools.partial(print, flush=True)  # noqa: A001
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

PROBE_JS = r"""
    (function () {
      if (window.__reqlogInstalled) return;
      window.__reqlogInstalled = true;
      window.__reqlog = [];
      window.__synth = window.__synth || { forceOnline: false };
      const orig = window.fetch;
      window.fetch = function (input, init) {
        init = init || {};
        const url = typeof input === 'string' ? input : ((input && input.url) || '');
        const method = (init.method || (input && input.method) || 'GET').toUpperCase();
        const rec = {url: url, method: method,
                     body: typeof init.body === 'string' ? init.body : null};
        window.__reqlog.push(rec);
        return orig.apply(this, arguments).then(function (r) {
          rec.status = r.status;
          const s = window.__synth || {};
          if (s.forceOnline && method === 'GET' &&
              /\/api\/v1\/(apis|playback-devices)(\?|$)/.test(url) && r.ok) {
            return r.clone().text().then(function (txt) {
              var j;
              try { j = JSON.parse(txt); } catch (e) { return r; }
              var items = (j && j.data && j.data.items) || [];
              for (var i = 0; i < items.length; i++) { items[i].status = 'online'; }
              rec.syntheticOnline = items.length;
              return new Response(JSON.stringify(j),
                {status: r.status, headers: {'Content-Type': 'application/json'}});
            });
          }
          return r;
        });
      };
    })();
"""


def _check(name, cond, detail=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f' — {detail}' if detail else ''))
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
    profile = os.path.join(os.environ.get('TEMP', '.'), 'int1495v4_chrome')
    shutil.rmtree(profile, ignore_errors=True)
    o = Options()
    o.binary_location = CHROME_BINARY
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1050')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--user-data-dir=' + profile)
    o.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
    p = _chromedriver()
    d = webdriver.Chrome(options=o, service=Service(executable_path=p) if p else Service())
    d.set_page_load_timeout(60)
    d.set_script_timeout(180)
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': PROBE_JS})
    return d


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 45).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(2.0)


def _body(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _wait_text(drv, text, timeout=25):
    WebDriverWait(drv, timeout).until(
        lambda d: text in d.execute_script('return document.body.textContent || ""'))


def _js_click(drv, el, wait=0.6):
    drv.execute_script('arguments[0].click()', el)
    time.sleep(wait)


def _synth(drv, **kwargs):
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
        'source': 'window.__synth = Object.assign(window.__synth || {}, '
                  + json.dumps(kwargs) + ');',
    })


def _reqlog(drv):
    return drv.execute_script('return window.__reqlog || []')


def _clear_reqlog(drv):
    drv.execute_script('window.__reqlog = []')


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
        url = GATEWAY + '/health'
        with urllib.request.urlopen(url, timeout=10) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception as e:
        return {'error': str(e)}


def _shot(drv, name):
    d = os.path.join(ARTIFACTS, name)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, 'screenshot.png')
    try:
        drv.save_screenshot(path)
        with open(os.path.join(d, 'body.txt'), 'w', encoding='utf-8') as f:
            f.write(_body(drv))
    except Exception as e:
        print('evidence error', name, e)
    return path


def _toasts(drv, timeout=15):
    def find(d):
        els = d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')
        return [(e.text or '').strip() for e in els if (e.text or '').strip()] or False
    try:
        return WebDriverWait(drv, timeout).until(find)
    except Exception:
        return []


def _wait_no_toast(drv, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        if not drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]'):
            return True
        time.sleep(0.4)
    return False


def _menu_item(drv, label, timeout=12):
    def find(d):
        for it in d.find_elements(By.XPATH, "//*[@role='menuitem']"):
            if label in (it.text or ''):
                return it
        return False
    return WebDriverWait(drv, timeout).until(find)


def _disabled(el):
    return (el.get_attribute('data-disabled') is not None
            or el.get_attribute('aria-disabled') == 'true')


def _set_theme(drv, theme):
    drv.get(BASE + '/devices/test')
    WebDriverWait(drv, 45).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    drv.execute_script("window.localStorage.setItem('iatp:theme:v1:mode', arguments[0])", theme)
    drv.get(BASE + '/devices/test')
    WebDriverWait(drv, 45).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(2.0)


def _open_lab_dialog(drv):
    btn = drv.find_element(By.XPATH, "//button[@aria-label='更多操作']")
    _js_click(drv, btn)
    _js_click(drv, _menu_item(drv, '实验室管理'))
    _wait_text(drv, '管理物理实验室及其资源归属', 30)
    time.sleep(1.0)


def _alert(drv, timeout=12):
    def find(d):
        els = d.find_elements(By.XPATH, "//*[@role='alertdialog']")
        return els[-1] if els else False
    return WebDriverWait(drv, timeout).until(find)


def _alert_open(drv):
    return bool(drv.find_elements(By.XPATH, "//*[@role='alertdialog']"))


def _alert_click(drv, text):
    alert = _alert(drv)
    for b in alert.find_elements(By.TAG_NAME, 'button'):
        if (b.text or '').strip() == text:
            _js_click(drv, b)
            return True
    return False


def _labs(drv):
    st, d = _api(drv, '/api/v1/laboratories?page=1&per_page=1000')
    return st, ((d.get('data') or {}).get('items', []) if isinstance(d, dict) else [])


def _purge(drv, code):
    st, items = _labs(drv)
    for it in items:
        if it.get('code') == code:
            _api(drv, f"/api/v1/laboratories/{it['id']}", 'DELETE')
    return st


def _create_lab(drv, name, code, room):
    return _api(drv, '/api/v1/laboratories', 'POST', {
        'name': name, 'code': code, 'building': '研发中心测试楼', 'floor': '5 层',
        'room_number': room, 'description': 'INT-1495 V4 复测自建', 'status': 'active',
    })


def _testing_badges(drv):
    """「测试中」占用徽章（DeviceStatusBadge 里 animate-pulse 的 Badge）。"""
    return drv.find_elements(
        By.XPATH, "//*[contains(@class,'animate-pulse') and normalize-space(.)='测试中']")


def _tab_click(drv, label, expect_path, timeout=30):
    """SPA 内切页签（不整页 reload，模块内覆盖值保留，才能暴露「测试中」残留）。"""
    el = drv.find_element(
        By.XPATH, f"//button[@role='tab' and normalize-space(.)='{label}']")
    _js_click(drv, el)
    WebDriverWait(drv, timeout).until(lambda d: expect_path in d.current_url)
    time.sleep(2.0)


def _row_buttons(drv, timeout=45):
    """等列表行操作入口出现（列表 GET 可能较慢）。"""
    def find(d):
        els = d.find_elements(By.XPATH, "//button[starts-with(@aria-label,'操作 ')]")
        return els or False
    try:
        return WebDriverWait(drv, timeout).until(find)
    except Exception:
        return []


def _pick_row(drv, buttons, name):
    for b in buttons:
        if (b.get_attribute('aria-label') or '').endswith(' ' + name):
            return b
    return buttons[0]


def _console_errors(drv):
    """只看 JS 异常；network 级别的 404/400 是本脚本故意制造的真实失败态，不计。"""
    try:
        return [e for e in drv.get_log('browser')
                if e.get('level') == 'SEVERE' and e.get('source') != 'network']
    except Exception:
        return []


# ───────────────────────────── 步骤 ─────────────────────────────

def step_preflight(drv):
    h = _health()
    _COMPARE['health_start'] = h
    _check('真实库栈 /health database=intelligent_audio_test',
           h.get('database') == 'intelligent_audio_test', json.dumps(h, ensure_ascii=False))
    _goto(drv, '/devices/test')
    _wait_text(drv, '设备管理', 40)
    _check('AUTH_MODE=off 免登录直达设备页', '设备管理' in _body(drv), drv.current_url)
    for code in (LAB_FAIL_CODE, LAB_OK_CODE, LAB_DARK_CODE):
        _purge(drv, code)
    _purge_temp_playback(drv, None)
    st, labs = _labs(drv)
    _COMPARE['labs_start'] = [x.get('code') for x in labs]
    _check('基线 GET /laboratories 200', st == 200, f'status={st} total={len(labs)}')


def step_p2a_failure(drv):
    """P2-A：后台已删 → 页面再删必然真实 404。"""
    st, d = _create_lab(drv, LAB_FAIL_NAME, LAB_FAIL_CODE, '601')
    _COMPARE['lab_fail_create'] = {'status': st, 'resp': d}
    _check('前置：自建实验室（删除失败态）', st in (200, 201), str(d)[:200])
    _, labs = _labs(drv)
    lab = next((x for x in labs if x.get('code') == LAB_FAIL_CODE), None)
    _check('前置：实验室可 GET 回读', lab is not None, f"id={lab and lab.get('id')}")
    if not lab:
        return None

    _goto(drv, '/devices/test')
    _wait_text(drv, '设备管理', 40)
    _open_lab_dialog(drv)
    _wait_text(drv, LAB_FAIL_NAME, 40)

    # 后台删除，页面行保持旧数据
    st, d = _api(drv, f"/api/v1/laboratories/{lab['id']}", 'DELETE')
    _check('前置：后台先删（制造真实 404 目标）', st in (200, 204), f'status={st} {d}')

    _wait_no_toast(drv)
    _clear_reqlog(drv)
    _js_click(drv, drv.find_element(By.XPATH, f"//button[@aria-label='删除实验室 {LAB_FAIL_NAME}']"))
    _wait_text(drv, '删除实验室', 15)
    time.sleep(1.2)  # ConfirmDialog 动画期点击会被吞
    _alert_click(drv, '删除')
    toasts = _toasts(drv)
    _COMPARE['p2a_fail_toasts'] = toasts
    net = [r for r in _reqlog(drv) if r['method'] == 'DELETE' and '/laboratories/' in r['url']]
    _COMPARE['p2a_fail_requests'] = net
    joined = ' | '.join(toasts)
    _check('P2-A 真实 DELETE /laboratories/{id} → 404',
           bool(net) and net[-1].get('status') == 404, json.dumps(net, ensure_ascii=False))
    _check('P2-A 失败提示后端文案「未找到实验室」', '未找到实验室' in joined, joined)
    _check('P2-A 不再出现「实验室已删除」假成功', '实验室已删除' not in joined, joined)
    _check('P2-A 失败后确认框保持打开', _alert_open(drv), f'alertdialog={_alert_open(drv)}')
    _shot(drv, 'p2a_delete_failure_light')
    if _alert_open(drv):
        _alert_click(drv, '取消')
        time.sleep(0.8)
    return lab


def step_p2a_success(drv):
    st, d = _create_lab(drv, LAB_OK_NAME, LAB_OK_CODE, '602')
    _check('前置：自建实验室（删除成功态）', st in (200, 201), str(d)[:200])
    _goto(drv, '/devices/test')
    _wait_text(drv, '设备管理', 40)
    _open_lab_dialog(drv)
    _wait_text(drv, LAB_OK_NAME, 40)
    _wait_no_toast(drv)
    _clear_reqlog(drv)
    _js_click(drv, drv.find_element(By.XPATH, f"//button[@aria-label='删除实验室 {LAB_OK_NAME}']"))
    _wait_text(drv, '删除实验室', 15)
    time.sleep(1.2)
    _alert_click(drv, '删除')
    toasts = _toasts(drv)
    _COMPARE['p2a_ok_toasts'] = toasts
    net = [r for r in _reqlog(drv) if r['method'] == 'DELETE' and '/laboratories/' in r['url']]
    _COMPARE['p2a_ok_requests'] = net
    joined = ' | '.join(toasts)
    _check('P2-A 回归：成功删除提示「实验室已删除」', '实验室已删除' in joined, joined)
    _check('P2-A 回归：DELETE 返回 2xx', bool(net) and net[-1].get('status') in (200, 204),
           json.dumps(net, ensure_ascii=False))
    time.sleep(1.5)
    _check('P2-A 回归：确认框关闭', not _alert_open(drv))
    _check('P2-A 回归：列表行消失', LAB_OK_NAME not in _body(drv))
    _shot(drv, 'p2a_delete_success_light')
    _, labs = _labs(drv)
    _check('P2-A 回归：GET 回读已无该实验室',
           not any(x.get('code') == LAB_OK_CODE for x in labs),
           json.dumps([x.get('code') for x in labs], ensure_ascii=False))


def step_p3a(drv):
    """P3-a：真实 200 的健康检查，一次点击只一条 toast。"""
    _synth(drv, forceOnline=True)
    _goto(drv, '/devices/api')
    _wait_text(drv, '设备管理', 40)
    time.sleep(2.0)
    buttons = _row_buttons(drv)
    _check('P3-a 前置：API 页有行操作入口', bool(buttons), f'{len(buttons)} 行')
    if not buttons:
        return
    _js_click(drv, _pick_row(drv, buttons, '1'))
    item = _menu_item(drv, '健康检查')
    _check('P3-a 前置：健康检查可点（synthetic online）', not _disabled(item),
           f'disabled={_disabled(item)}')
    if _disabled(item):
        return
    _wait_no_toast(drv)
    _clear_reqlog(drv)
    _js_click(drv, item)
    # 真实健康检查要等后端连设备超时（实测 20~40s），先等请求落定再读 toast
    end = time.time() + 180
    while time.time() < end:
        done = [r for r in _reqlog(drv)
                if r['method'] == 'POST' and '/health' in r['url'] and r.get('status')]
        if done:
            break
        time.sleep(1.0)
    toasts = _toasts(drv, timeout=20)
    _COMPARE['p3a_toasts'] = toasts
    net = [r for r in _reqlog(drv) if r['method'] == 'POST' and '/health' in r['url']]
    _COMPARE['p3a_requests'] = net
    joined = ' | '.join(toasts)
    _check('P3-a 健康检查真实 POST 命中 /apis/1/health',
           bool(net) and '/apis/' in net[-1]['url'], json.dumps(net, ensure_ascii=False))
    _check('P3-a 真实后端返回 200', bool(net) and net[-1].get('status') == 200,
           json.dumps(net, ensure_ascii=False))
    _check('P3-a 一次点击只一条 toast', len(toasts) == 1, json.dumps(toasts, ensure_ascii=False))
    _check('P3-a 不再叠加「健康检查已发起」', '健康检查已发起' not in joined, joined)
    _shot(drv, 'p3a_api_health_single_toast_light')


def _create_temp_playback(drv):
    st, d = _api(drv, '/api/v1/playback-devices', 'POST', {
        'name': TEMP_PB_NAME, 'model': 'probe', 'device_type': 'dry', 'status': 'offline',
        'sample_rate': 48000, 'device_unique_id': 'JX1495V4P3B',
        'description': 'INT-1495 V4 P3-b 对照自建',
    })
    return st, d


def _purge_temp_playback(drv, st):
    _, d = _api(drv, '/api/v1/playback-devices?page=1&per_page=1000')
    items = ((d.get('data') or {}).get('items', []) if isinstance(d, dict) else [])
    for it in items:
        if it.get('name') == TEMP_PB_NAME:
            st = _api(drv, f"/api/v1/playback-devices/{it['id']}", 'DELETE')
    return st


def step_p3b(drv):
    """P3-b：真实 400 的播放测试失败 →「测试中」占用覆盖必须回滚。

    敏感度设计：失败当下列表不会重取（react-query staleTime 60s），单看当时 DOM 新旧构建都是 0 徽章，
    没有区分力。所以再用一次 UI 删除自建临时播放设备成功 → invalidate('playback') → 强制重取列表：
    旧构建（不回滚）这时会把失败设备装饰成「测试中」并一直显示；新构建应为 0。
    """
    st, d = _create_temp_playback(drv)
    _COMPARE['p3b_temp_pb_create'] = {'status': st, 'resp': d}
    _check('P3-b 前置：自建临时播放设备（接线测试前缀）', st in (200, 201), str(d)[:160])

    _synth(drv, forceOnline=True)
    _goto(drv, '/devices/playback')
    _wait_text(drv, '设备管理', 40)
    time.sleep(2.0)
    buttons = _row_buttons(drv)
    _check('P3-b 前置：播放设备页有行操作入口', bool(buttons), f'{len(buttons)} 行')
    if not buttons:
        return
    target = next((b for b in buttons
                   if TEMP_PB_NAME not in (b.get_attribute('aria-label') or '')), buttons[0])
    _js_click(drv, target)
    item = _menu_item(drv, '播放测试')
    _check('P3-b 前置：播放测试可点（synthetic online）', not _disabled(item),
           f'disabled={_disabled(item)}')
    if _disabled(item):
        return
    _wait_no_toast(drv)
    _clear_reqlog(drv)
    _js_click(drv, item)
    toasts = _toasts(drv)
    _COMPARE['p3b_toasts'] = toasts
    net = [r for r in _reqlog(drv) if r['method'] == 'POST' and '/playback-devices/' in r['url']]
    _COMPARE['p3b_requests'] = net
    joined = ' | '.join(toasts)
    _check('P3-b 播放测试真实请求 POST /playback-devices/{id}/test',
           bool(net) and '/test' in net[-1]['url'], json.dumps(net, ensure_ascii=False))
    _check('P3-b 真实失败（非 2xx）', bool(net) and net[-1].get('status') == 400,
           json.dumps(net, ensure_ascii=False))
    _check('P3-b 失败提示「播放测试启动失败，请稍后重试」',
           '播放测试启动失败' in joined, joined)
    time.sleep(3.0)
    left = _testing_badges(drv)
    _COMPARE['p3b_testing_badges_after_fail'] = len(left)

    # 用 UI 删除临时播放设备成功 → invalidate('playback') → 真实重取列表
    _wait_no_toast(drv)
    _clear_reqlog(drv)
    tb = next(b for b in _row_buttons(drv)
              if TEMP_PB_NAME in (b.get_attribute('aria-label') or ''))
    _js_click(drv, tb)
    _js_click(drv, _menu_item(drv, '删除'))
    _wait_text(drv, '删除设备', 12)
    time.sleep(1.2)
    _alert_click(drv, '删除')
    del_toasts = _toasts(drv, timeout=20)
    _COMPARE['p3b_temp_delete_toasts'] = del_toasts
    del_net = [r for r in _reqlog(drv) if r['method'] == 'DELETE' and '/playback-devices/' in r['url']]
    _COMPARE['p3b_temp_delete_requests'] = del_net
    _check('P3-b 前置：临时播放设备 UI 删除成功（触发列表重取）',
           bool(del_net) and del_net[-1].get('status') in (200, 204),
           json.dumps(del_net, ensure_ascii=False))
    time.sleep(3.0)
    gets = [r for r in _reqlog(drv) if r['method'] == 'GET' and '/playback-devices' in r['url']]
    _COMPARE['p3b_refetch_gets'] = gets
    _check('P3-b 列表已真实重取', bool(gets), json.dumps(gets, ensure_ascii=False))
    left2 = _testing_badges(drv)
    _COMPARE['p3b_testing_badges_after_refetch'] = len(left2)
    _check('P3-b 重取列表后无「测试中」残留（覆盖已回滚）', len(left2) == 0,
           f'count={len(left2)} body测试中={_body(drv).count("测试中")}')
    _check('P3-b 失败后「测试中」徽章不残留（失败当下）', len(left) == 0,
           f'count={len(left)}')
    _shot(drv, 'p3b_occupied_rollback_light')


def step_dark(drv):
    """深色：实验室删除失败态重走（真实 404）。"""
    st, d = _create_lab(drv, LAB_DARK_NAME, LAB_DARK_CODE, '603')
    _check('深色前置：自建实验室', st in (200, 201), str(d)[:160])
    _, labs = _labs(drv)
    lab = next((x for x in labs if x.get('code') == LAB_DARK_CODE), None)
    if not lab:
        return
    _synth(drv, forceOnline=False)
    _set_theme(drv, 'dark')
    is_dark = drv.execute_script(
        "return document.documentElement.classList.contains('dark')")
    _COMPARE['dark_theme'] = is_dark
    _check('深色主题生效（html.dark）', bool(is_dark))
    _open_lab_dialog(drv)
    _wait_text(drv, LAB_DARK_NAME, 40)
    _shot(drv, 'lab_dialog_dark')
    _api(drv, f"/api/v1/laboratories/{lab['id']}", 'DELETE')
    _wait_no_toast(drv)
    _clear_reqlog(drv)
    _js_click(drv, drv.find_element(By.XPATH, f"//button[@aria-label='删除实验室 {LAB_DARK_NAME}']"))
    _wait_text(drv, '删除实验室', 15)
    time.sleep(1.2)
    _alert_click(drv, '删除')
    toasts = _toasts(drv)
    _COMPARE['dark_toasts'] = toasts
    joined = ' | '.join(toasts)
    _check('深色：删除失败提示后端文案且无假成功',
           '未找到实验室' in joined and '实验室已删除' not in joined, joined)
    _shot(drv, 'p2a_delete_failure_dark')
    if _alert_open(drv):
        _alert_click(drv, '取消')


def step_cleanup(drv):
    for code in (LAB_FAIL_CODE, LAB_OK_CODE, LAB_DARK_CODE):
        _purge(drv, code)
    _purge_temp_playback(drv, None)
    st, labs = _labs(drv)
    left = [x.get('code') for x in labs if str(x.get('code', '')).startswith('JX1495V4')]
    _COMPARE['labs_left'] = left
    _check('收尾：本 run 自建实验室零残留', not left, json.dumps(left, ensure_ascii=False))
    _COMPARE['labs_end'] = [x.get('code') for x in labs]


def main():
    os.makedirs(ARTIFACTS, exist_ok=True)
    drv = _driver()
    try:
        step_preflight(drv)
        step_p2a_failure(drv)
        step_p2a_success(drv)
        step_p3a(drv)
        step_p3b(drv)
        step_dark(drv)
        _COMPARE['health_before_delivery'] = _health()
        _check('交付前 /health 仍为 intelligent_audio_test',
               _COMPARE['health_before_delivery'].get('database') == 'intelligent_audio_test',
               json.dumps(_COMPARE['health_before_delivery'], ensure_ascii=False))
        errs = _console_errors(drv)
        _COMPARE['console_severe'] = errs[:10]
        _check('浏览器控制台无 SEVERE 错误', not errs, json.dumps(errs[:3], ensure_ascii=False))
        step_cleanup(drv)
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
