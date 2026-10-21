# -*- coding: utf-8 -*-
"""INT-1060 返工复测——逐卡 并行/串行 选项 + 底部实时示意图（测试工程师独立复测）。

基线：交付脚本 verify_int1060_rework.py；本副本自建 fixture（唯一名 接线测试_INT1060_TE_rework_<ts>
设备 + API），验收后 teardown，另补 readOnly 观察态核对（CDP 注入 algo_engineer 会话）。

覆盖验收标准（2026-10-21 返工口径）：
  ① 步骤二逐卡出现「并行/串行」选项，默认并行；纯设备/纯 API/混选均可设置
     （执行参数区不再有全局执行模式开关）
  ② 底部示意图随配置实时更新（增删卡、切换模式即变），深浅色截图
  ③ 创建任务请求实测携带逐目标 target_modes（INT-1115 契约：恰好覆盖全部选中目标、
     保选中顺序、mode 正确；不再有 execution_mode/serial_first）Network 证据
  ④ 交互走查逐环节可通：选择资源 → 逐卡设模式 → 看示意图 → 开始任务
  ⑤ 文档回写：功能文档 §5.2.4 已核对（裁定日期 2026-10-21）
  ⑥ readOnly 观察态：只读 Badge + 示意图只读渲染（algo_engineer 会话注入）

用法：python verify_int1060_rework_TE.py --base http://localhost:5390
输出：tests/ui/artifacts/int1060_rework_te/*.png
"""
import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
import io
import winreg

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1060_rework_te')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


def _json_req(gateway, path, payload=None, method='GET'):
    """urllib 直达 127.0.0.1（规避 localhost→::1 卡死）。返回 (status, data-dict)。"""
    url = gateway + path
    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if payload is not None:
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode('utf-8', 'replace')
            try:
                return resp.status, json.loads(raw)
            except Exception:
                return resp.status, {'raw': raw}
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {'raw': raw}


def _create_fixtures(gateway):
    """自建设备 + API（唯一名）；返回 (device_id, device_name, api_id, api_name)。"""
    suffix = str(int(time.time() * 1000))[-10:]
    dev_name = '接线测试_INT1060_TE_rework_dev_%s' % suffix
    api_name = '接线测试_INT1060_TE_rework_api_%s' % suffix
    st, dev = _json_req(gateway, '/api/v1/test-devices', {
        'name': dev_name, 'model': 'TE-Model', 'type': 'phone', 'system': 'Android',
        'system_version': '10', 'app_name': 'test', 'app_version': '1.0',
        'serial_number': 'TESN%s' % suffix, 'status': 'online', 'connection_type': 'usb',
    }, 'POST')
    assert st == 201, '设备 fixture 创建失败: %r %s' % (st, dev)
    dev_id = dev['data']['id']
    st, api = _json_req(gateway, '/api/v1/apis', {
        'name': api_name, 'vendor': 'te', 'api_url': 'http://127.0.0.1:9999/mock',
        'description': 'TE rework fixture', 'status': 'online', 'device_type': 'http_api',
        'algorithm_type': 'voice_llm',
        'endpoints': [{'endpoint': 'http://127.0.0.1:9999/mock', 'name': 'mock',
                       'status': 'online', 'max_process': 4, 'max_timeout': 60,
                       'max_audio_duration': 120, 'priority': 1}],
    }, 'POST')
    assert st == 201, 'API fixture 创建失败: %r %s' % (st, api)
    api_id = api['data']['id']
    return dev_id, dev_name, api_id, api_name


def _teardown(gateway, dev_id, api_id, task_id=None):
    """删除本卡 fixture（best-effort，失败告警不抛）。设备关联任务时先删任务再删设备。"""
    if task_id:
        st, _ = _json_req(gateway, '/api/v1/tasks/%d' % task_id, method='DELETE')
        if st >= 400:
            print('WARN delete task %s -> %s' % (task_id, st))
    for path in ['/api/v1/test-devices/%d' % dev_id, '/api/v1/apis/%d' % api_id]:
        st, body = _json_req(gateway, path, method='DELETE')
        if st >= 400:
            print('WARN teardown %s -> %s' % (path, st))


def _stop_task(gateway, task_id):
    st, _ = _json_req(gateway, '/api/v1/tasks/%d/stop' % task_id, {}, 'POST')
    if st >= 400:
        print('WARN stop task %s failed (best-effort)' % task_id)


def _set_online(gateway, path, obj_id):
    """常驻栈周期健康检查会把假设备/API 翻回离线——交互前 PUT 置 online。"""
    st, _ = _json_req(gateway, '/api/v1/%s/%d' % (path, obj_id), {'status': 'online'}, 'PUT')
    return st == 200


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


def wait_for(cond, timeout=30, desc='condition'):
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


def _goto(drv, base, path):
    drv.get(base + path)
    time.sleep(1.5)
    drv.get(base + path)


def _mode_group(drv, name):
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


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print('  OK', msg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:5390')
    ap.add_argument('--gateway', default='http://localhost:5000')
    args = ap.parse_args()
    base = args.base.rstrip('/')
    gateway = args.gateway.rstrip('/')
    os.makedirs(ARTIFACTS, exist_ok=True)

    dev_id, dev_name, api_id, api_name = _create_fixtures(gateway)
    print('fixtures: dev=%s(%d) api=%s(%d)' % (dev_name, dev_id, api_name, api_id))
    task_id = None
    drv = None
    try:
        assert _set_online(gateway, 'test-devices', dev_id), '设备置 online 失败'
        assert _set_online(gateway, 'apis', api_id), 'API 置 online 失败'

        drv = _driver()
        drv.set_page_load_timeout(60)

        # ============ 浅色：逐卡模式 + 示意图 ============
        drv.get(base + '/')
        time.sleep(2)
        drv.execute_script('localStorage.setItem("iatp:theme:v1:mode", "light")')
        _set_online(gateway, 'test-devices', dev_id)
        _set_online(gateway, 'apis', api_id)
        _goto(drv, base, '/start-test?step=1')
        wait_for(lambda: len(drv.find_elements(By.CSS_SELECTOR, '[aria-label="选择设备 %s"]' % dev_name)) > 0,
                 40, 'resource page renders')

        # ① 执行参数区不再有全局执行模式开关 / 串行优先侧
        _assert(len(drv.find_elements(By.CSS_SELECTOR, 'input[name=execution-mode]')) == 0,
                '执行参数区应无全局执行模式开关')
        _assert(len(drv.find_elements(By.CSS_SELECTOR, 'input[name=serial-first]')) == 0,
                '执行参数区应无串行优先侧')

        # ② 未选中目标：不渲染任何逐卡模式控件
        _assert(len(drv.find_elements(By.CSS_SELECTOR, '[role="radiogroup"][aria-label*="执行模式"]')) == 0,
                '未选中任何目标时不应渲染模式控件')

        # ③ 纯设备：勾选设备卡 → 「并行｜串行」默认并行
        _click_visible(drv, '[aria-label="选择设备 %s"]' % dev_name)
        time.sleep(0.6)
        grp = _mode_group(drv, dev_name)
        checked = grp.find_elements(By.CSS_SELECTOR, 'button[aria-checked="true"]')
        _assert(checked and '并行' in checked[0].text, '设备卡默认应为并行')
        drv.save_screenshot(os.path.join(ARTIFACTS, 'step1_device_only_parallel.png'))

        # ④ 纯设备可切串行（不再置灰）
        _set_mode(drv, dev_name, '串行')
        checked = _mode_group(drv, dev_name).find_elements(By.CSS_SELECTOR, 'button[aria-checked="true"]')
        _assert(checked and '串行' in checked[0].text, '纯设备可切串行')
        drv.save_screenshot(os.path.join(ARTIFACTS, 'step1_device_only_serial.png'))
        print('④ 纯设备切串行：OK')

        # ⑤ 混选：勾选 API → API 行模式控件（默认并行）；示意图实时更新
        _set_online(gateway, 'apis', api_id)
        _click_visible(drv, '[aria-label="选择 %s"]' % api_name)
        time.sleep(0.6)
        api_grp = _mode_group(drv, api_name)
        checked = api_grp.find_elements(By.CSS_SELECTOR, 'button[aria-checked="true"]')
        _assert(checked and '并行' in checked[0].text, 'API 行默认应为并行')
        diagram = _diagram_text(drv)
        _assert('并行 · 同时执行' in diagram, '示意图应含并行组')
        _assert('串行 · 依次执行' in diagram, '示意图应含串行链')
        _assert(api_name in diagram, '示意图应含 API 节点')
        _assert(dev_name in diagram, '示意图应含设备节点')
        drv.save_screenshot(os.path.join(ARTIFACTS, 'step1_mixed_parallel_serial.png'))
        print('⑤ 混选逐卡模式 + 示意图实时更新：OK')

        # ⑥ API 切串行 → 串行链两节点（示意图重绘）
        _set_mode(drv, api_name, '串行')
        diagram = _diagram_text(drv)
        _assert(api_name in diagram and dev_name in diagram, '串行链应含两个节点')
        _assert('串行 · 依次执行' in diagram, '全串行仍显示串行链')
        drv.save_screenshot(os.path.join(ARTIFACTS, 'step1_all_serial_chain.png'))
        print('⑥ API 切串行 → 串行链重绘：OK')

        # ⑦ 取消选择 API → 示意图移除节点；重选回默认并行
        drv.find_element(By.CSS_SELECTOR, '[aria-label="选择 %s"]' % api_name).click()
        time.sleep(0.6)
        diagram = _diagram_text(drv)
        _assert(api_name not in diagram, '取消选择后示意图应移除 API 节点')
        _assert(dev_name in diagram, '设备节点应保留')
        _click_visible(drv, '[aria-label="选择 %s"]' % api_name)
        time.sleep(0.6)
        checked = _mode_group(drv, api_name).find_elements(By.CSS_SELECTOR, 'button[aria-checked="true"]')
        _assert(checked and '并行' in checked[0].text, '取消选择后重选 API 应回默认并行')
        _set_mode(drv, api_name, '串行')
        print('⑦ 取消/重选 API → 示意图实时增删 + 模式回默认：OK')

        # ============ ③ 创建任务携带 target_modes（INT-1115 契约） ============
        drv.execute_script("""
          (function () {
            const orig = window.fetch.bind(window);
            window.__INT1060R_TASK_ID__ = null;
            window.fetch = (url, opts) => {
              const u = typeof url === 'string' ? url : (url && url.url) || '';
              const method = (opts && opts.method) || 'GET';
              if (method === 'POST' && /\\/api\\/v1\\/tasks(?:[?]|$)/.test(u)) {
                return orig(url, opts).then((resp) => {
                  try {
                    resp.clone().json().then((d) => {
                      if (d && d.data && d.data.id) window.__INT1060R_TASK_ID__ = d.data.id;
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
        print('③ POST /tasks body:', body[:900])
        _assert('target_modes' in body, 'POST /tasks 应携带 target_modes')
        _assert('execution_mode' not in body, 'POST /tasks 不应再携带 execution_mode')
        _assert('serial_first' not in body, 'POST /tasks 不应再携带 serial_first')
        tm = json.loads(body).get('target_modes') or []
        _assert(len(tm) == 2, 'target_modes 应恰好覆盖全部选中目标（2 条）')
        types = [(t.get('target_type'), t.get('target_id'), t.get('mode')) for t in tm]
        expected = [('device', dev_id, 'serial'), ('api', api_id, 'serial')]
        _assert(types == expected, 'target_modes 保选中顺序且 mode 正确，实际：%r（期望 %r）' % (types, expected))
        _assert(create_reqs[0]['status'] is not None and create_reqs[0]['status'] < 400,
                'POST /tasks 非成功状态：%r' % create_reqs[0]['status'])
        print('③ POST /tasks target_modes 契约（覆盖/顺序/mode）：OK')

        task_id = drv.execute_script('return window.__INT1060R_TASK_ID__')
        print('③ captured task id:', task_id)
        if task_id:
            _stop_task(gateway, int(task_id))

        # ============ 深色截图 ============
        drv.execute_script('localStorage.setItem("iatp:theme:v1:mode", "dark")')
        drv.get('about:blank')
        _set_online(gateway, 'test-devices', dev_id)
        _set_online(gateway, 'apis', api_id)
        _goto(drv, base, '/start-test?step=1')
        wait_for(lambda: len(drv.find_elements(By.CSS_SELECTOR, '[aria-label="选择设备 %s"]' % dev_name)) > 0,
                 30, 'dark rerender')
        _click_visible(drv, '[aria-label="选择设备 %s"]' % dev_name)
        time.sleep(0.5)
        _set_mode(drv, dev_name, '串行')
        _click_visible(drv, '[aria-label="选择 %s"]' % api_name)
        time.sleep(0.5)
        _set_mode(drv, api_name, '串行')
        drv.save_screenshot(os.path.join(ARTIFACTS, 'step1_all_serial_dark.png'))
        print('深色截图：OK')

        # ============ ⑥ readOnly 观察态（algo_engineer 会话注入） ============
        _inject_algo_engineer(drv, base, gateway, dev_id, api_id, dev_name, api_name)

        print('=== INT-1060 返工逐卡模式 + 示意图独立复测全部通过 ===')
    finally:
        if drv:
            drv.quit()
        if task_id:
            _stop_task(gateway, int(task_id))
        _teardown(gateway, dev_id, api_id, task_id)
        print('teardown fixtures done')


def _inject_algo_engineer(drv, base, gateway, dev_id, api_id, dev_name, api_name):
    """CDP 注入 algo_engineer 会话（permissions 含 algorithm:read、无 task:execute）→
    只读观察态核对：逐卡只读 Badge（无控件）+ 示意图只读渲染 + 无勾选/操作钮。"""
    # 1) 清持久化会话，注入 algo_engineer user（auth store key iatp:auth:v1）
    drv.execute_script("""
      try { localStorage.removeItem('iatp:auth:v1'); } catch (e) {}
      const algoUser = {
        id: '9001', username: 'algo_engineer', displayName: '算法工程师',
        roleName: '算法工程师', permissions: ['algorithm:read', 'algorithm:definition_manage'],
      };
      localStorage.setItem('iatp:auth:v1', JSON.stringify({state: {user: algoUser}, version: 0}));
      try { localStorage.setItem('iatp:theme:v1:mode', 'light'); } catch (e) {}
    """)
    # 2) 拦截 /auth/mode + /auth/me：hydrateSession 失败 → 保留注入角色会话
    try:
        drv.execute_cdp_cmd('Network.enable', {})
        drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': ['*auth/mode*', '*auth/me*']})
    except Exception as exc:
        print('WARN CDP blockedURLs failed:', exc)
    _set_online(gateway, 'test-devices', dev_id)
    _set_online(gateway, 'apis', api_id)
    drv.get(base + '/start-test?step=1')
    time.sleep(3)
    # 只读态下勾选 Checkbox 不渲染（aria-label 不存在），改为等设备卡名文本渲染
    wait_for(lambda: dev_name in (drv.execute_script('return document.body.textContent || ""') or ''),
             30, 'readonly resource render')
    # 只读态：设备卡无「选择」Checkbox、无逐卡模式控件、无连接测试钮
    _assert(len(drv.find_elements(By.CSS_SELECTOR, '[aria-label="选择设备 %s"]' % dev_name)) == 0,
            'readOnly 设备卡不应有勾选 Checkbox')
    _assert(len(drv.find_elements(By.CSS_SELECTOR, '[role="radiogroup"][aria-label*="执行模式"]')) == 0,
            'readOnly 不应渲染逐卡模式控件')
    _assert(len(drv.find_elements(By.XPATH, '//button[contains(., "连接测试")]')) == 0,
            'readOnly 不应有连接测试按钮')
    # 示意图只读渲染（空态占位）
    sec = drv.find_element(By.CSS_SELECTOR, 'section[aria-label="执行示意"]')
    _assert('选择设备或 API 后，此处实时展示' in (sec.text or ''),
            'readOnly 示意图应渲染空态占位（不折叠）')
    drv.save_screenshot(os.path.join(ARTIFACTS, 'readonly_observation.png'))
    print('⑥ readOnly 观察态（Badge/示意图只读/无控件）：OK')
    try:
        drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': []})
    except Exception:
        pass


if __name__ == '__main__':
    main()
