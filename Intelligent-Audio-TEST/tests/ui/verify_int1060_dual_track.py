# -*- coding: utf-8 -*-
"""INT-1060 返工（第二轮）双道语义浏览器实测。

覆盖验收标准（2026-10-21 双道口径 + 代码审计 P1/P2 修正）：
  ① 步骤二逐卡出现「并行/串行」选项，默认并行；纯设备/纯 API/混选均可设置
  ② 底部示意图为**双道版式**（设备道 / API 道各自独立、互不等待、空道折叠），
     随配置实时更新（增删卡、切换模式即变），深浅色截图
  ③ 创建任务请求携带逐目标 target_modes（INT-1115 契约：恰好覆盖全部选中目标、
     保选中顺序、mode 正确；不再有 execution_mode/serial_first）Network 证据
  ④ 跨类型独立性（验收标准第 6 项）：混选设备+API 且两侧各有串行目标时，
     示意图呈现双道（设备道 / API 道各自独立串行链），串行设备不等 API 道、
     串行 API 不等设备道（无跨类型阶段箭头 / 无跨道节点）

用法：python verify_int1060_dual_track.py --base http://localhost:5386
输出：tests/ui/artifacts/int1060_dualtrack/*.png + network_evidence.md
"""
import argparse
import json
import os
import time
import urllib.request
import urllib.error
import winreg

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1060_dualtrack')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

DEVICE_NAME = 'pura90小艺'
DEVICE_ID = 21
API_NAME = 'INT314SMOKE_befd9a93_mock_api'
API_ID = 9


def _set_online(gateway, path, payload):
    """常驻栈周期健康检查会把假设备/API 翻回离线——交互前 PUT 置 online。"""
    req = urllib.request.Request(
        gateway + path,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='PUT')
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as exc:
        print('WARN set online failed:', path, exc)
        return False


def _stop_task(gateway, task_id):
    """停止本卡创建的测试任务（最小化共享库干扰）；best-effort。"""
    req = urllib.request.Request(
        gateway + '/api/v1/tasks/%d/stop' % task_id,
        data=b'{}',
        headers={'Content-Type': 'application/json'},
        method='POST')
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status < 400
    except Exception as exc:
        print('WARN stop task failed (best-effort):', exc)
        return False


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1100')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
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
    return webdriver.Chrome(options=options, service=service)


def collect_requests(drv):
    reqs = {}
    try:
        for entry in drv.get_log('performance'):
            try:
                msg = json.loads(entry.get('message', '') or '')
                params = (msg.get('message') or {}).get('params') or {}
                method = (msg.get('message') or {}).get('method') or ''
            except Exception:
                continue
            if method == 'Network.requestWillBeSent':
                req = params.get('request') or {}
                url = req.get('url') or ''
                reqs[params.get('requestId')] = {
                    'method': req.get('method', 'GET'),
                    'url': url,
                    'status': None,
                    'postData': req.get('postData') or '',
                }
            elif method == 'Network.responseReceived':
                rid = params.get('requestId')
                if rid in reqs:
                    reqs[rid]['status'] = (params.get('response') or {}).get('status')
    except Exception:
        pass
    return [v for k, v in reqs.items()]


def wait_for(cond, timeout=25, desc='condition'):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if cond():
                return True
        except Exception:
            pass
        time.sleep(0.5)
    raise AssertionError('timeout waiting for %s' % desc)


def _click_visible(drv, css, timeout=15):
    def do():
        for el in drv.find_elements(By.CSS_SELECTOR, css):
            try:
                if el.is_displayed() and el.get_attribute('aria-disabled') != 'true' \
                        and el.get_attribute('disabled') is None:
                    drv.execute_script('arguments[0].scrollIntoView({block:"center"});', el)
                    time.sleep(0.4)
                    el.click()
                    return True
            except Exception:
                continue
        return False

    deadline = time.time() + timeout
    while time.time() < deadline:
        if do():
            return
        time.sleep(0.5)
    raise AssertionError('click failed: ' + css)


def _goto(drv, base, path):
    drv.get(base + path)
    time.sleep(1.5)
    drv.get(base + path)


def _mode_group(drv, name):
    """定位某目标的执行模式 radiogroup（aria-label = '{name} 执行模式'）。"""
    els = drv.find_elements(
        By.XPATH,
        "//div[@role='radiogroup'][contains(@aria-label, '执行模式') and contains(@aria-label, '%s')]" % name)
    assert els, '未找到 %s 的执行模式控件' % name
    return els[0]


def _set_mode(drv, name, mode):
    grp = _mode_group(drv, name)
    btn = grp.find_element(By.XPATH, ".//button[@role='radio'][contains(., '%s')]" % mode)
    drv.execute_script('arguments[0].scrollIntoView({block:"center"});', btn)
    time.sleep(0.3)
    btn.click()
    time.sleep(0.5)


def _diagram_text(drv):
    sec = drv.find_element(By.CSS_SELECTOR, 'section[aria-label="执行示意"]')
    return (sec.text or '')


def _lane(drv, lane_type):
    els = drv.find_elements(By.CSS_SELECTOR, 'section[aria-label="执行示意"] [data-lane="%s"]' % lane_type)
    return els[0] if els else None


def _lane_text(lane_el):
    return (lane_el.text or '') if lane_el is not None else ''


def _click_button(drv, text, timeout=15):
    def do():
        for el in drv.find_elements(By.XPATH, '//button[contains(., "%s")]' % text):
            try:
                if el.is_displayed() and el.get_attribute('disabled') is None:
                    drv.execute_script('arguments[0].scrollIntoView({block:"center"});', el)
                    time.sleep(0.4)
                    el.click()
                    return True
            except Exception:
                continue
        return False

    deadline = time.time() + timeout
    while time.time() < deadline:
        if do():
            return
        time.sleep(0.5)
    raise AssertionError('button click failed: ' + text)


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print('  OK', msg)


def _set_mode_group_all(drv):
    return drv.find_elements(By.CSS_SELECTOR, '[role="radiogroup"][aria-label*="执行模式"]')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:5386')
    ap.add_argument('--gateway', default='http://127.0.0.1:5000')
    args = ap.parse_args()
    base = args.base.rstrip('/')
    gateway = args.gateway.rstrip('/')
    os.makedirs(ARTIFACTS, exist_ok=True)

    assert _set_online(gateway, '/api/v1/test-devices/%d' % DEVICE_ID, {'status': 'online'}), '测试设备置 online 失败'
    assert _set_online(gateway, '/api/v1/apis/%d' % API_ID, {'status': 'online'}), '测试 API 置 online 失败'

    drv = _driver()
    try:
        drv.set_page_load_timeout(60)
        # ============ 浅色：/start-test?step=1 逐卡模式 + 双道示意图 ============
        drv.get(base + '/')
        time.sleep(2)
        drv.execute_script('localStorage.setItem("iatp:theme:v1:mode", "light")')
        _set_online(gateway, '/api/v1/test-devices/%d' % DEVICE_ID, {'status': 'online'})
        _set_online(gateway, '/api/v1/apis/%d' % API_ID, {'status': 'online'})
        _goto(drv, base, '/start-test?step=1')
        wait_for(lambda: len(drv.find_elements(By.CSS_SELECTOR, '[aria-label="选择设备 %s"]' % DEVICE_NAME)) > 0,
                 30, 'resource page renders')

        # ① 执行参数区不再有全局执行模式开关（INT-1119 移除）
        _assert(len(drv.find_elements(By.CSS_SELECTOR, 'input[name=execution-mode]')) == 0,
                '执行参数区应无全局执行模式开关')
        _assert(len(drv.find_elements(By.CSS_SELECTOR, 'input[name=serial-first]')) == 0,
                '执行参数区应无串行优先侧')

        # ② 未选中任何目标：无逐卡模式控件；示意图空态
        _assert(len(_set_mode_group_all(drv)) == 0, '未选中任何目标时不应渲染模式控件')
        _assert('选择设备或 API 后' in _diagram_text(drv), '空态示意图占位应可见')

        # ③ 纯设备：勾选设备卡 → 出现「并行｜串行」（默认并行）→ 切串行
        _click_visible(drv, '[aria-label="选择设备 %s"]' % DEVICE_NAME)
        time.sleep(0.6)
        checked = _mode_group(drv, DEVICE_NAME).find_elements(By.CSS_SELECTOR, 'button[aria-checked="true"]')
        _assert(checked and '并行' in checked[0].text, '设备卡默认应为并行')
        _set_mode(drv, DEVICE_NAME, '串行')
        checked = _mode_group(drv, DEVICE_NAME).find_elements(By.CSS_SELECTOR, 'button[aria-checked="true"]')
        _assert(checked and '串行' in checked[0].text, '纯设备可切串行')
        # 纯设备：仅设备道，API 道折叠
        dev_lane = _lane(drv, 'device')
        api_lane = _lane(drv, 'api')
        _assert(dev_lane is not None, '纯设备应有设备道')
        _assert(api_lane is None, '纯设备不应有 API 道（空道折叠）')
        _assert(DEVICE_NAME in _lane_text(dev_lane), '设备道应含设备节点')
        _assert('串行 · 依次执行' in _lane_text(dev_lane), '设备道应含串行链')
        drv.save_screenshot(os.path.join(ARTIFACTS, 'step1_device_only_serial.png'))
        print('③ 纯设备逐卡选项 + 单道版式：OK')

        # ④ 混选：勾选 API（默认并行）→ 双道：设备道串行链 + API 道并行组（互不等待）
        _set_online(gateway, '/api/v1/apis/%d' % API_ID, {'status': 'online'})
        _click_visible(drv, '[aria-label="选择 %s"]' % API_NAME)
        time.sleep(0.6)
        checked = _mode_group(drv, API_NAME).find_elements(By.CSS_SELECTOR, 'button[aria-checked="true"]')
        _assert(checked and '并行' in checked[0].text, 'API 行默认应为并行')
        diagram = _diagram_text(drv)
        _assert('设备道' in diagram and 'API 道' in diagram, '示意图应含设备道 / API 道双道')
        dev_lane = _lane(drv, 'device')
        api_lane = _lane(drv, 'api')
        _assert(DEVICE_NAME in _lane_text(dev_lane), '设备道应含设备节点')
        _assert('串行 · 依次执行' in _lane_text(dev_lane), '设备道应含串行链')
        _assert(API_NAME in _lane_text(api_lane), 'API 道应含 API 节点')
        _assert('并行 · 同时执行' in _lane_text(api_lane), 'API 道应含并行组')
        _assert('串行 · 依次执行' not in _lane_text(api_lane), 'API 并行时其道内不应有串行链')
        _assert(API_NAME not in _lane_text(dev_lane), '设备道不应含 API 节点（无跨道混排）')
        _assert(DEVICE_NAME not in _lane_text(api_lane), 'API 道不应含设备节点（无跨道混排）')
        drv.save_screenshot(os.path.join(ARTIFACTS, 'step1_mixed_parallel_serial.png'))
        print('④ 混选双道（设备串行 + API 并行）独立道：OK')

        # ⑤ API 切串行 → 双道各自独立串行链（验收标准第 6 项核心断言）
        _set_mode(drv, API_NAME, '串行')
        diagram = _diagram_text(drv)
        _assert(diagram.count('串行 · 依次执行') == 2, '全串行应出现两条独立串行链（设备道 + API 道），实际 %d' % diagram.count('串行 · 依次执行'))
        dev_lane = _lane(drv, 'device')
        api_lane = _lane(drv, 'api')
        _assert(DEVICE_NAME in _lane_text(dev_lane) and API_NAME not in _lane_text(dev_lane),
                '设备道串行链仅含设备节点')
        _assert(API_NAME in _lane_text(api_lane) and DEVICE_NAME not in _lane_text(api_lane),
                'API 道串行链仅含 API 节点')
        _assert('并行 · 同时执行' not in _lane_text(dev_lane), '设备全串行时其道内不应有并行组')
        _assert('并行 · 同时执行' not in _lane_text(api_lane), 'API 全串行时其道内不应有并行组')
        drv.save_screenshot(os.path.join(ARTIFACTS, 'step1_dual_serial_tracks.png'))
        print('⑤ 双道各自独立串行链（串行设备不等 API、串行 API 不等设备）：OK')

        # ⑥ 取消选择 API → 示意图移除 API 道（实时增删卡）；重选回默认并行再切串行
        _click_visible(drv, '[aria-label="选择 %s"]' % API_NAME)
        time.sleep(0.6)
        _assert(_lane(drv, 'api') is None, '取消选择后 API 道应移除')
        _assert(_lane(drv, 'device') is not None, '设备道应保留')
        _click_visible(drv, '[aria-label="选择 %s"]' % API_NAME)
        time.sleep(0.6)
        checked = _mode_group(drv, API_NAME).find_elements(By.CSS_SELECTOR, 'button[aria-checked="true"]')
        _assert(checked and '并行' in checked[0].text, '取消选择后重选 API 应回默认并行')
        _set_mode(drv, API_NAME, '串行')
        print('⑥ 取消/重选 API → 双道实时增删 + 模式回默认：OK')

        # ============ ③ 创建任务携带 target_modes（INT-1115 契约） ============
        drv.execute_script("""
          (function () {
            const orig = window.fetch.bind(window);
            window.__INT1060DT_TASK_ID__ = null;
            window.fetch = (url, opts) => {
              const u = typeof url === 'string' ? url : (url && url.url) || '';
              const method = (opts && opts.method) || 'GET';
              if (method === 'POST' && /\\/api\\/v1\\/tasks(?:[?]|$)/.test(u)) {
                return orig(url, opts).then((resp) => {
                  try {
                    resp.clone().json().then((d) => {
                      if (d && d.data && d.data.id) window.__INT1060DT_TASK_ID__ = d.data.id;
                    }).catch(function(){});
                  } catch (e) {}
                  return resp;
                });
              }
              return orig(url, opts);
            };
          })();
        """)
        drv.get_log('performance')  # drain 基线
        # 底部「开始测试」钮 → 任务名称弹窗 → 开始测试
        _click_button(drv, '开始测试')
        wait_for(lambda: any(e.is_displayed() for e in drv.find_elements(
            By.XPATH, "//div[@data-slot='dialog-content'][.//*[@data-slot='dialog-title'][contains(., '任务名称')]]")),
            15, 'task name dialog open')
        time.sleep(0.5)
        dlg = [d for d in drv.find_elements(
            By.XPATH, "//div[@data-slot='dialog-content'][.//*[@data-slot='dialog-title'][contains(., '任务名称')]]")
            if d.is_displayed()][0]
        dlg_text = dlg.text or ''
        _assert('串行 2 个目标' in dlg_text, '任务名称弹窗摘要应附串行计数')
        drv.save_screenshot(os.path.join(ARTIFACTS, 'task_name_dialog.png'))
        dlg.find_element(By.XPATH, ".//button[contains(., '开始测试')]").click()
        time.sleep(2.5)
        reqs = collect_requests(drv)
        create_reqs = [r for r in reqs
                       if r['method'] == 'POST' and '/api/v1/tasks' in r['url']
                       and (r['url'].rstrip('/').endswith('/tasks') or '/tasks?' in r['url'])]
        _assert(create_reqs, '未捕获 POST /tasks（创建任务请求缺失）')
        body = create_reqs[0]['postData'] or ''
        print('③ POST /tasks body:', body[:800])
        _assert('target_modes' in body, 'POST /tasks 应携带 target_modes')
        _assert('execution_mode' not in body, 'POST /tasks 不应再携带 execution_mode')
        _assert('serial_first' not in body, 'POST /tasks 不应再携带 serial_first')
        tm = json.loads(body).get('target_modes') or []
        _assert(len(tm) == 2, 'target_modes 应恰好覆盖全部选中目标（2 条）')
        types = [(t.get('target_type'), t.get('target_id'), t.get('mode')) for t in tm]
        _assert(types == [('device', DEVICE_ID, 'serial'), ('api', API_ID, 'serial')],
                'target_modes 保选中顺序且 mode 正确，实际：%r' % types)
        _assert(create_reqs[0]['status'] is not None and create_reqs[0]['status'] < 400,
                'POST /tasks 非成功状态：%r' % create_reqs[0]['status'])
        print('③ POST /tasks target_modes 契约（覆盖/顺序/mode）：OK')

        # Network 证据落盘
        with open(os.path.join(ARTIFACTS, 'network_evidence.md'), 'w', encoding='utf-8') as f:
            f.write('## INT-1060 双道返工 Network 证据\n\n')
            f.write('- POST /tasks URL: `%s`\n' % create_reqs[0]['url'])
            f.write('- POST /tasks status: %r\n' % create_reqs[0]['status'])
            f.write('- POST /tasks body: `%s`\n' % body)
            f.write('- 断言：`target_modes` 存在；`execution_mode` / `serial_first` 不存在；恰好覆盖 2 个选中目标；保选中顺序 [device→api]；mode 均 serial。\n')

        task_id = drv.execute_script('return window.__INT1060DT_TASK_ID__')
        print('③ captured task id:', task_id)
        if task_id:
            _stop_task(gateway, int(task_id))
            print('③ 已停止测试任务', task_id)

        # ============ 深色截图（双道全串行） ============
        drv.execute_script('localStorage.setItem("iatp:theme:v1:mode", "dark")')
        drv.get('about:blank')
        _set_online(gateway, '/api/v1/test-devices/%d' % DEVICE_ID, {'status': 'online'})
        _set_online(gateway, '/api/v1/apis/%d' % API_ID, {'status': 'online'})
        _goto(drv, base, '/start-test?step=1')
        wait_for(lambda: len(drv.find_elements(By.CSS_SELECTOR, '[aria-label="选择设备 %s"]' % DEVICE_NAME)) > 0,
                 25, 'dark rerender')
        _click_visible(drv, '[aria-label="选择设备 %s"]' % DEVICE_NAME)
        time.sleep(0.5)
        _set_mode(drv, DEVICE_NAME, '串行')
        _click_visible(drv, '[aria-label="选择 %s"]' % API_NAME)
        time.sleep(0.5)
        _set_mode(drv, API_NAME, '串行')
        diagram = _diagram_text(drv)
        _assert(diagram.count('串行 · 依次执行') == 2, '深色全串行应出现两条独立串行链')
        drv.save_screenshot(os.path.join(ARTIFACTS, 'step1_dual_serial_tracks_dark.png'))
        print('深色双道截图：OK')

        print('=== INT-1060 双道语义实测全部通过 ===')
        if task_id:
            print('NOTE cleanup: stop task id', task_id)
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
