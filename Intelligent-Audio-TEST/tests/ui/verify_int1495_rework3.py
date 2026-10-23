# -*- coding: utf-8 -*-
"""INT-1495 第三轮返修复测（React 接线 / docker 真实库栈）。

打回清单只测失败项与本次修复相关触点：
  P2-A 实验室删除失败（非 2xx）必须提示后端文案、不得提示「实验室已删除」、确认框保持
  P3-a API 健康检查一次点击只出一条 toast（不再叠加无条件「已发起」）
  P3-b 播放测试请求失败时「测试中」占用覆盖回滚，设备不再卡在测试中

环境：前端 = 本卡交付分支构建的旁路容器 http://127.0.0.1:15497（nginx /api/ → api_gateway:5000），
后端网关 http://127.0.0.1:15000（真实库 intelligent_audio_test，AUTH_MODE=off）。

合成手段（脚本内显式标注 synthetic，只为触发失败态，不改后端、不改页内 mock）：
  - P2-A：自建实验室 → 先用接口删除 → 页面行仍是旧数据 → 页内再删必然 404（真实 404，非合成）
  - P3-a/P3-b：真实库 API/播放设备全为 offline，「健康检查 / 播放测试」入口被离线禁用，
    故页内 fetch 打点把这两个列表的 status 改写为 online（synthetic），并让对应 POST 返回
    合成 500（synthetic 500），以复现失败态。

测试数据：全部带「接线测试_INT1495R3_」前缀，脚本内删除并 API 复核零残留。
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

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15497')
GATEWAY = os.environ.get('REAL_GATEWAY', 'http://127.0.0.1:15000')
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1495_r3')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

LAB_A_NAME = '接线测试_INT1495R3_删除失败'
LAB_A_CODE = 'JX1495R3A'
LAB_B_NAME = '接线测试_INT1495R3_删除成功'
LAB_B_CODE = 'JX1495R3B'
LAB_C_NAME = '接线测试_INT1495R3_深色失败'
LAB_C_CODE = 'JX1495R3C'

_FAILURES = []
_COMPARE = {}
print = functools.partial(print, flush=True)  # noqa: A001
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# 页内 fetch 打点（CDP 注入到每个新文档）+ 合成开关
FETCH_PROBE_JS = """
    (function () {
      if (window.__reqlogInstalled) return;
      window.__reqlogInstalled = true;
      window.__reqlog = [];
      window.__synth = window.__synth || { forceOnline: false, failHealth: false, failPlaybackTest: false };
      const orig = window.fetch;
      window.fetch = function (input, init) {
        init = init || {};
        const url = typeof input === 'string' ? input : ((input && input.url) || '');
        const method = (init.method || (input && input.method) || 'GET').toUpperCase();
        const rec = {url: url, method: method,
                     body: typeof init.body === 'string' ? init.body : null};
        window.__reqlog.push(rec);
        const s = window.__synth || {};
        if (s.failHealth && method === 'POST' && /\\/apis\\/\\d+\\/health$/.test(url)) {
          rec.synthetic = 500;
          rec.status = 500;
          return Promise.resolve(new Response(
            JSON.stringify({success: false, code: 500, message: '合成 500：健康检查失败'}),
            {status: 500, headers: {'Content-Type': 'application/json'}}));
        }
        if (s.failPlaybackTest && method === 'POST' && /\\/playback-devices\\/\\d+\\/test$/.test(url)) {
          rec.synthetic = 500;
          rec.status = 500;
          return Promise.resolve(new Response(
            JSON.stringify({success: false, code: 500, message: '合成 500：播放测试启动失败'}),
            {status: 500, headers: {'Content-Type': 'application/json'}}));
        }
        return orig.apply(this, arguments).then(function (r) {
          rec.status = r.status;
          if (s.forceOnline && method === 'GET' &&
              /\\/api\\/v1\\/(apis|playback-devices)(\\?|$)/.test(url) && r.ok) {
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
    profile = os.path.join(os.environ.get('TEMP', '.'), 'int1495r3_chrome')
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
    d.set_page_load_timeout(45)
    d.set_script_timeout(180)
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PROBE_JS})
    return d


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 30).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(2.0)


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _wait_text(drv, text, timeout=20):
    WebDriverWait(drv, timeout).until(
        lambda d: text in d.execute_script('return document.body.textContent || ""'))


def _js_click(drv, el):
    drv.execute_script('arguments[0].click()', el)
    time.sleep(0.6)


def _synth(drv, **kwargs):
    """合成开关注入到每个新文档（列表 GET 早于页面 readyState 完成，必须在文档起点生效）。"""
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
        'source': 'window.__synth = Object.assign(window.__synth || {}, '
                  + json.dumps(kwargs) + ');',
    })


def _reqlog(drv):
    return drv.execute_script('return window.__reqlog || []')


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


def _evidence(drv, name):
    d = os.path.join(ARTIFACTS, name)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, 'screenshot.png')
    try:
        drv.save_screenshot(path)
        with open(os.path.join(d, 'body.txt'), 'w', encoding='utf-8') as f:
            f.write(_body_text(drv))
    except Exception as e:
        print('evidence error', name, e)
    return path


def _toast_texts(drv, timeout=10):
    """当前 sonner toast 文案列表（默认 4s 消失，须及时读）。"""
    def find(d):
        els = d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')
        return [(e.text or '').strip() for e in els if (e.text or '').strip()] or False
    try:
        return WebDriverWait(drv, timeout).until(find)
    except Exception:
        return []


def _wait_no_toast(drv, timeout=8):
    """等上一步 toast 自动消失，保证本轮 toast 计数只算本次点击。"""
    end = time.time() + timeout
    while time.time() < end:
        if not drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]'):
            return True
        time.sleep(0.4)
    return False


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


def _set_theme(drv, theme):
    drv.execute_script("window.localStorage.setItem('iatp:theme:v1:mode', arguments[0])", theme)
    drv.refresh()
    WebDriverWait(drv, 30).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(2.0)


def _open_lab_dialog(drv):
    btn = drv.find_element(By.XPATH, "//button[@aria-label='更多操作']")
    _js_click(drv, btn)
    item = _menu_item(drv, '实验室管理')
    _js_click(drv, item)
    _wait_text(drv, '管理物理实验室及其资源归属', 20)
    time.sleep(1.0)


def _lab_delete_row(drv, name):
    return drv.find_element(By.XPATH, f"//button[@aria-label='删除实验室 {name}']")


def _confirm_alert(drv, timeout=10):
    def find(d):
        els = d.find_elements(By.XPATH, "//*[@role='alertdialog']")
        return els[-1] if els else False
    return WebDriverWait(drv, timeout).until(find)


def _confirm_click(drv, text):
    alert = _confirm_alert(drv)
    for b in alert.find_elements(By.TAG_NAME, 'button'):
        if (b.text or '').strip() == text:
            _js_click(drv, b)
            return True
    return False


def _alert_open(drv):
    return bool(drv.find_elements(By.XPATH, "//*[@role='alertdialog']"))


def _labs(drv):
    st, d = _api(drv, '/api/v1/laboratories?page=1&per_page=1000')
    return st, ((d.get('data') or {}).get('items', []) if isinstance(d, dict) else [])


def _purge(drv, code):
    st, items = _labs(drv)
    for it in items:
        if it.get('code') == code:
            _api(drv, f"/api/v1/laboratories/{it['id']}", 'DELETE')
    return st


# ------------------------- 步骤 -------------------------

def step_preflight(drv):
    h = _health()
    _COMPARE['health_start'] = h
    _check('真实库栈 /health database=intelligent_audio_test',
           h.get('database') == 'intelligent_audio_test', detail=json.dumps(h, ensure_ascii=False))
    _goto(drv, '/devices/test')
    _wait_text(drv, '设备管理', 30)
    _check('AUTH_MODE=off 免登录直达设备页', '设备管理' in _body_text(drv), detail=drv.current_url)
    _, labs = _labs(drv)
    _COMPARE['labs_total_start'] = len(labs)
    _check('基线 GET /laboratories 200', isinstance(labs, list), detail=f'total={len(labs)}')
    _purge(drv, LAB_A_CODE)
    _purge(drv, LAB_B_CODE)


def step_create_labs(drv):
    st, d = _api(drv, '/api/v1/laboratories', 'POST', {
        'name': LAB_A_NAME, 'code': LAB_A_CODE, 'building': '研发中心测试楼',
        'floor': '5 层', 'room_number': '501', 'description': 'INT-1495 R3 删除失败态自建',
        'status': 'active',
    })
    _COMPARE['lab_a_create'] = {'status': st, 'resp': d}
    _check('前置：自建实验室 A（接线测试_INT1495R3_）', st in (200, 201), detail=str(d)[:200])
    st, d = _api(drv, '/api/v1/laboratories', 'POST', {
        'name': LAB_B_NAME, 'code': LAB_B_CODE, 'building': '研发中心测试楼',
        'floor': '5 层', 'room_number': '502', 'description': 'INT-1495 R3 删除成功态自建',
        'status': 'active',
    })
    _COMPARE['lab_b_create'] = {'status': st, 'resp': d}
    _check('前置：自建实验室 B（接线测试_INT1495R3_）', st in (200, 201), detail=str(d)[:200])
    _, labs = _labs(drv)
    lab_a = next((x for x in labs if x.get('code') == LAB_A_CODE), None)
    lab_b = next((x for x in labs if x.get('code') == LAB_B_CODE), None)
    _check('自建实验室均可回读', lab_a is not None and lab_b is not None,
           detail=f'A={lab_a and lab_a.get("id")} B={lab_b and lab_b.get("id")}')
    return lab_a, lab_b


def step_p2a_delete_failure(drv, lab_a):
    """P2-A：页面持有的行被后台删除后，页内再删必然 404，验证不再假成功。"""
    _goto(drv, '/devices/test')
    _wait_text(drv, '设备管理', 30)
    _open_lab_dialog(drv)
    _wait_text(drv, LAB_A_NAME, 30)
    # 后台删除 A，页面行保持旧数据（raw fetch 不触发列表失效）
    st, d = _api(drv, f"/api/v1/laboratories/{lab_a['id']}", 'DELETE')
    _check('后台先删实验室 A（制造非 2xx 删除目标）', st in (200, 204), detail=f'status={st} {d}')
    drv.execute_script('window.__reqlog = []')
    _js_click(drv, _lab_delete_row(drv, LAB_A_NAME))
    _wait_text(drv, '删除实验室', 10)
    _evidence(drv, 'p2a_confirm_open_light')
    _confirm_click(drv, '删除')
    toasts = _toast_texts(drv, 15)
    _COMPARE['p2a_toasts'] = toasts
    net = [r for r in _reqlog(drv) if r['method'] == 'DELETE' and '/laboratories/' in r['url']]
    _COMPARE['p2a_delete_requests'] = net
    _check('P2-A 真实 DELETE /laboratories/{id} 返回 404',
           bool(net) and net[-1].get('status') == 404, detail=json.dumps(net, ensure_ascii=False))
    joined = ' | '.join(toasts)
    _check('P2-A 删除失败提示后端文案「未找到实验室」', '未找到实验室' in joined, detail=joined)
    _check('P2-A 未出现「实验室已删除」假成功', '实验室已删除' not in joined, detail=joined)
    _check('P2-A 失败后确认框保持打开（可取消/重试）', _alert_open(drv),
           detail=f'alertdialog={_alert_open(drv)}')
    _evidence(drv, 'p2a_delete_failure_toast_light')
    # 关闭确认框，保持页面可用
    if _alert_open(drv):
        _confirm_click(drv, '取消')
        time.sleep(0.5)


def step_p2a_delete_success(drv):
    """P2-A 回归：成功删除仍提示「实验室已删除」并移除行。"""
    _wait_text(drv, LAB_B_NAME, 20)
    drv.execute_script('window.__reqlog = []')
    _js_click(drv, _lab_delete_row(drv, LAB_B_NAME))
    _wait_text(drv, '删除实验室', 10)
    _confirm_click(drv, '删除')
    toasts = _toast_texts(drv, 15)
    _COMPARE['p2a_success_toasts'] = toasts
    joined = ' | '.join(toasts)
    net = [r for r in _reqlog(drv) if r['method'] == 'DELETE' and '/laboratories/' in r['url']]
    _COMPARE['p2a_success_delete_requests'] = net
    _check('P2-A 回归：成功删除提示「实验室已删除」', '实验室已删除' in joined, detail=joined)
    _check('P2-A 回归：DELETE 返回 2xx', bool(net) and net[-1].get('status') in (200, 204),
           detail=json.dumps(net, ensure_ascii=False))
    time.sleep(1.5)
    _check('P2-A 回归：列表行消失', LAB_B_NAME not in _body_text(drv))
    _evidence(drv, 'p2a_delete_success_light')
    _, labs = _labs(drv)
    _check('P2-A 回归：GET 回读已无该实验室',
           not any(x.get('code') == LAB_B_CODE for x in labs),
           detail=json.dumps([x.get('code') for x in labs], ensure_ascii=False))


def step_p3a_api_health_single_toast(drv):
    """P3-a：健康检查失败时只应有一条错误 toast，不再叠加「健康检查已发起」。"""
    _synth(drv, forceOnline=True, failHealth=True)
    _goto(drv, '/devices/api')
    _wait_text(drv, '设备管理', 30)
    time.sleep(2.5)
    buttons = drv.find_elements(By.XPATH, "//button[starts-with(@aria-label,'操作 ')]")
    _check('P3-a 前置：API 页存在行操作入口', bool(buttons), detail=f'{len(buttons)} 行')
    if not buttons:
        return
    _js_click(drv, buttons[0])
    item = _menu_item(drv, '健康检查')
    _check('P3-a 前置：健康检查入口可用（合成 online）', not _item_disabled(item),
           detail=f'disabled={_item_disabled(item)}')
    if _item_disabled(item):
        return
    drv.execute_script('window.__reqlog = []')
    _wait_no_toast(drv)
    _js_click(drv, item)
    toasts = _toast_texts(drv, 15)
    _COMPARE['p3a_toasts'] = toasts
    net = [r for r in _reqlog(drv) if r['method'] == 'POST' and '/health' in r['url']]
    _COMPARE['p3a_health_requests'] = net
    joined = ' | '.join(toasts)
    _check('P3-a 健康检查失败只出错误 toast', len(toasts) == 1, detail=json.dumps(toasts, ensure_ascii=False))
    _check('P3-a 不再叠加「健康检查已发起」', '健康检查已发起' not in joined, detail=joined)
    _check('P3-a 失败文案为后端/合成 500 文案', '失败' in joined or '重试' in joined, detail=joined)
    _evidence(drv, 'p3a_api_health_single_toast_light')


def step_p3b_occupied_rollback(drv):
    """P3-b：播放测试请求失败后「测试中」覆盖回滚，行不残留测试中徽章。"""
    _synth(drv, forceOnline=True, failPlaybackTest=True)
    _goto(drv, '/devices/playback')
    _wait_text(drv, '设备管理', 30)
    time.sleep(2.5)
    buttons = drv.find_elements(By.XPATH, "//button[starts-with(@aria-label,'操作 ')]")
    _check('P3-b 前置：播放设备页存在行操作入口', bool(buttons), detail=f'{len(buttons)} 行')
    if not buttons:
        return
    _js_click(drv, buttons[0])
    item = _menu_item(drv, '播放测试')
    _check('P3-b 前置：播放测试入口可用（合成 online）', not _item_disabled(item),
           detail=f'disabled={_item_disabled(item)}')
    if _item_disabled(item):
        return
    drv.execute_script('window.__reqlog = []')
    _js_click(drv, item)
    toasts = _toast_texts(drv, 15)
    _COMPARE['p3b_toasts'] = toasts
    joined = ' | '.join(toasts)
    net = [r for r in _reqlog(drv) if r['method'] == 'POST' and '/playback-devices/' in r['url']]
    _COMPARE['p3b_playback_requests'] = net
    _check('P3-b 播放测试失败出现错误 toast', '播放测试启动失败' in joined, detail=joined)
    _check('P3-b 请求命中真实播放测试端点', any('/test' in r['url'] for r in net),
           detail=json.dumps(net, ensure_ascii=False))
    time.sleep(2.5)  # 等 onError invalidate 后的列表重取
    body = _body_text(drv)
    _check('P3-b 失败后列表不残留「测试中」徽章', '测试中' not in body,
           detail=f'测试中出现={body.count("测试中")}')
    _evidence(drv, 'p3b_occupied_rollback_light')


def step_dark_shots(drv):
    """深色：实验室弹窗 + 删除失败提示（同一失败路径在深色下重走一次）。"""
    st, d = _api(drv, '/api/v1/laboratories', 'POST', {
        'name': LAB_C_NAME, 'code': LAB_C_CODE, 'building': '研发中心测试楼',
        'floor': '5 层', 'room_number': '503', 'description': 'INT-1495 R3 深色删除失败态',
        'status': 'active',
    })
    _, labs = _labs(drv)
    lab_c = next((x for x in labs if x.get('code') == LAB_C_CODE), None)
    _check('深色：自建实验室 C', lab_c is not None, detail=str(d)[:160])
    if not lab_c:
        return

    _synth(drv, forceOnline=False, failHealth=False, failPlaybackTest=False)
    _set_theme(drv, 'dark')
    _goto(drv, '/devices/test')
    _wait_text(drv, '设备管理', 30)
    _open_lab_dialog(drv)
    _wait_text(drv, LAB_C_NAME, 30)
    _evidence(drv, 'lab_dialog_dark')
    _api(drv, f"/api/v1/laboratories/{lab_c['id']}", 'DELETE')
    drv.execute_script('window.__reqlog = []')
    _js_click(drv, _lab_delete_row(drv, LAB_C_NAME))
    _wait_text(drv, '删除实验室', 10)
    _confirm_click(drv, '删除')
    toasts = _toast_texts(drv, 15)
    _COMPARE['dark_delete_toasts'] = toasts
    joined = ' | '.join(toasts)
    _check('深色：删除失败提示后端文案且无假成功',
           '未找到实验室' in joined and '实验室已删除' not in joined, detail=joined)
    _evidence(drv, 'delete_failure_toast_dark')
    if _alert_open(drv):
        _confirm_click(drv, '取消')
    _set_theme(drv, 'light')


def step_cleanup(drv, lab_a, lab_b):
    _purge(drv, LAB_A_CODE)
    _purge(drv, LAB_B_CODE)
    _purge(drv, 'JX1495R3C')
    st, labs = _labs(drv)
    left = [x for x in labs if str(x.get('code', '')).startswith('JX1495R3')]
    _COMPARE['labs_left'] = [x.get('code') for x in left]
    _check('收尾：本 run 自建实验室零残留', not left, detail=json.dumps(left, ensure_ascii=False))
    _COMPARE['labs_total_end'] = len(labs)


def main():
    os.makedirs(ARTIFACTS, exist_ok=True)
    drv = _driver()
    lab_a = lab_b = None
    try:
        step_preflight(drv)
        lab_a, lab_b = step_create_labs(drv)
        step_p2a_delete_failure(drv, lab_a)
        step_p2a_delete_success(drv)
        step_p3a_api_health_single_toast(drv)
        step_p3b_occupied_rollback(drv)
        step_dark_shots(drv)

        h = _health()
        _COMPARE['health_before_shots'] = h
        _check('截图后 /health 仍为 intelligent_audio_test',
               h.get('database') == 'intelligent_audio_test', detail=json.dumps(h, ensure_ascii=False))

        step_cleanup(drv, lab_a, lab_b)

        h = _health()
        _COMPARE['health_before_delivery'] = h
        _check('交付前 /health 仍为 intelligent_audio_test',
               h.get('database') == 'intelligent_audio_test', detail=json.dumps(h, ensure_ascii=False))
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
