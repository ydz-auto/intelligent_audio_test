# -*- coding: utf-8 -*-
"""INT-1060 /start-test 执行模式控件（并行/串行 + 串行优先侧）浏览器实测。

覆盖验收标准：
  ① 执行参数区出现「执行模式」控件，默认并行；混选设备+API 时可切换串行并显示优先侧选择
  ② 纯设备 / 纯 API 时置灰 + 提示「仅混选设备与 API 时可用」
  ③ 创建任务请求实测携带 execution_mode/serial_first（Network 证据，POST /tasks）
  ④ 浅色 + 深色截图

用法：python verify_int1060_exec_mode.py --base http://localhost:5391
输出：tests/ui/artifacts/int1060/*.png
"""
import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
import winreg

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1060')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

DEVICE_NAME = '接线测试_INT1060_device'
API_NAME = '接线测试_INT1060_api'
DEVICE_ID = 140
API_ID = 301


def _set_device_online(gateway):
    """常驻栈 device_monitor 周期健康检查会把假设备翻回 offline（5 分钟周期）——
    交互前先 PUT 置 online，保证浏览器拉到的资源列表是可勾选在线态。"""
    req = urllib.request.Request(
        gateway + '/api/v1/test-devices/%d' % DEVICE_ID,
        data=json.dumps({'status': 'online'}).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='PUT')
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as exc:
        print('WARN set device online failed:', exc)
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
    options.add_argument('--window-size=1600,1000')
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


def count_api_calls(reqs, path, methods=None):
    return [r for r in reqs if path in r.get('url', '') and (not methods or r.get('method') in methods)]


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


def _click_button(drv, text, timeout=15):
    """点可见未禁用的 button（含文字匹配）；scroll+click，动画就绪防点击被吞。"""
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


def _radio(drv, name):
    els = drv.find_elements(By.CSS_SELECTOR, 'input[type=radio][name="%s"]' % name)
    assert len(els) == 2, 'radio[name=%s] 数量异常: %d' % (name, len(els))
    return els


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:5391')
    ap.add_argument('--gateway', default='http://localhost:5000')
    args = ap.parse_args()
    base = args.base.rstrip('/')
    gateway = args.gateway.rstrip('/')
    os.makedirs(ARTIFACTS, exist_ok=True)

    assert _set_device_online(gateway), '测试设备置 online 失败（无法验证混选态）'

    drv = _driver()
    try:
        drv.set_page_load_timeout(60)
        # ============ 浅色：/start-test?step=1 执行模式控件 ============
        drv.get(base + '/')
        time.sleep(2)
        drv.execute_script('localStorage.setItem("iatp:theme:v1:mode", "light")')
        _set_device_online(gateway)
        _goto(drv, base, '/start-test?step=1')
        wait_for(lambda: len(drv.find_elements(By.CSS_SELECTOR, '[aria-label="选择设备 %s"]' % DEVICE_NAME)) > 0,
                 30, 'resource page renders')

        # ① 默认并行 + 未混选置灰 + 提示
        mpar, mser = _radio(drv, 'execution-mode')
        assert mpar.is_selected(), '默认应选中「并行」'
        assert not mser.is_selected(), '默认不应选中「串行」'
        assert mpar.get_attribute('disabled') is not None, '未混选时「并行」应置灰'
        assert mser.get_attribute('disabled') is not None, '未混选时「串行」应置灰'
        assert '仅混选设备与 API 时可用' in drv.find_element(By.TAG_NAME, 'body').text, '缺少置灰提示'
        assert len(drv.find_elements(By.CSS_SELECTOR, 'input[name=serial-first]')) == 0, '串行未选时不应显示优先侧'
        drv.save_screenshot(os.path.join(ARTIFACTS, 'step1_mode_default_disabled.png'))
        print('① 默认并行 + 未混选置灰提示：OK')

        # ② 纯设备选中：仍置灰
        dev_cb = drv.find_element(By.CSS_SELECTOR, '[aria-label="选择设备 %s"]' % DEVICE_NAME)
        assert dev_cb.get_attribute('aria-disabled') != 'true', '测试设备应在线可勾选'
        _click_visible(drv, '[aria-label="选择设备 %s"]' % DEVICE_NAME)
        time.sleep(0.8)
        mpar, mser = _radio(drv, 'execution-mode')
        assert mser.get_attribute('disabled') is not None, '纯设备选中时「串行」仍应置灰'
        assert '仅混选设备与 API 时可用' in drv.find_element(By.TAG_NAME, 'body').text, '纯设备仍应提示'
        drv.save_screenshot(os.path.join(ARTIFACTS, 'step1_device_only_disabled.png'))
        print('② 纯设备选中仍置灰：OK')

        # ③ 混选：控件可操作（默认并行）
        api_cb = drv.find_element(By.CSS_SELECTOR, '[aria-label="选择 %s"]' % API_NAME)
        assert api_cb.get_attribute('aria-disabled') != 'true', '测试 API 应在线可勾选'
        _click_visible(drv, '[aria-label="选择 %s"]' % API_NAME)
        time.sleep(0.8)
        mpar, mser = _radio(drv, 'execution-mode')
        assert mpar.get_attribute('disabled') is None, '混选后「并行」应可操作'
        assert mser.get_attribute('disabled') is None, '混选后「串行」应可操作'
        assert '仅混选设备与 API 时可用' not in drv.find_element(By.TAG_NAME, 'body').text, '混选后应移除提示'
        assert mpar.is_selected(), '混选后默认仍应并行'
        drv.save_screenshot(os.path.join(ARTIFACTS, 'step1_mixed_enabled_parallel.png'))
        print('③ 混选后控件可操作（默认并行）：OK')

        # ④ 切换串行 → 串行优先侧显示（默认设备先）
        drv.execute_script('arguments[0].scrollIntoView({block:"center"});', mser)
        time.sleep(0.3)
        mser.click()
        time.sleep(0.8)
        sd, sa = _radio(drv, 'serial-first')
        assert sd.is_selected(), '串行优先侧默认应「设备先」'
        assert not sa.is_selected(), '串行优先侧默认不应「API 先」'
        assert '同一用例设备侧与 API 侧不重叠' in drv.find_element(By.TAG_NAME, 'body').text, '串行说明缺失'
        drv.save_screenshot(os.path.join(ARTIFACTS, 'step1_serial_device_first.png'))
        # 切 API 先 → 切回设备先
        drv.execute_script('arguments[0].scrollIntoView({block:"center"});', sa)
        time.sleep(0.3)
        sa.click()
        time.sleep(0.6)
        sd, sa = _radio(drv, 'serial-first')
        assert sa.is_selected(), '切「API 先」应选中'
        drv.save_screenshot(os.path.join(ARTIFACTS, 'step1_serial_api_first.png'))
        sd.click()
        time.sleep(0.6)
        sd, sa = _radio(drv, 'serial-first')
        assert sd.is_selected(), '切回「设备先」应选中'
        print('④ 串行优先侧切换（API先→设备先）：OK')

        # ============ ③ 创建任务携带 execution_mode/serial_first ============
        # filterAll 模式（默认）启动：校验链 cases:[] 空用例报错被过滤，无需手动勾选用例；
        # 任务以当前筛选全量圈定用例（共享库全量），创建后立即 stop 最小化干扰。
        # window.fetch 打点：捕获 POST /tasks 响应 task id（真实请求照常发出，供 Network 证据）
        drv.execute_script("""
          (function () {
            const orig = window.fetch.bind(window);
            window.__INT1060_TASK_ID__ = null;
            window.fetch = (url, opts) => {
              const u = typeof url === 'string' ? url : (url && url.url) || '';
              const method = (opts && opts.method) || 'GET';
              if (method === 'POST' && /\\/api\\/v1\\/tasks(?:[?]|$)/.test(u)) {
                return orig(url, opts).then((resp) => {
                  try {
                    resp.clone().json().then((d) => {
                      if (d && d.data && d.data.id) window.__INT1060_TASK_ID__ = d.data.id;
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
        drv.save_screenshot(os.path.join(ARTIFACTS, 'task_name_dialog.png'))
        dlg.find_element(By.XPATH, ".//button[contains(., '开始测试')]").click()
        # 等 POST /tasks 创建（start 紧随其后）
        time.sleep(2.5)
        reqs = collect_requests(drv)
        create_reqs = [r for r in reqs
                       if r['method'] == 'POST' and '/api/v1/tasks' in r['url']
                       and (r['url'].rstrip('/').endswith('/tasks') or '/tasks?' in r['url'])]
        print('⑥ POST /tasks candidates:', [(r['method'], r['url'].split('/api/v1')[1], r['status']) for r in create_reqs])
        assert create_reqs, '未捕获 POST /tasks（创建任务请求缺失）'
        body = create_reqs[0]['postData'] or ''
        print('⑥ POST /tasks body:', body[:500])
        assert '"execution_mode":"serial"' in body, 'POST /tasks 缺 execution_mode=serial'
        assert '"serial_first":"device"' in body, 'POST /tasks 缺 serial_first=device'
        assert '"device_ids":[' in body and '"api_ids":[' in body, 'POST /tasks 缺 device_ids/api_ids'
        assert create_reqs[0]['status'] is not None and create_reqs[0]['status'] < 400, \
            'POST /tasks 非成功状态：%r' % create_reqs[0]['status']
        print('③ POST /tasks 携带 execution_mode/serial_first：OK')

        # 任务 id 捕获 → 立即停止（最小化共享库干扰）
        task_id = drv.execute_script('return window.__INT1060_TASK_ID__')
        print('⑥ captured task id:', task_id)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'task_launch_submitted.png'))
        if task_id:
            _stop_task(gateway, int(task_id))
            print('⑥ 已停止测试任务', task_id)

        # ============ 深色截图 ============
        drv.execute_script('localStorage.setItem("iatp:theme:v1:mode", "dark")')
        drv.get('about:blank')
        _set_device_online(gateway)
        _goto(drv, base, '/start-test?step=1')
        wait_for(lambda: len(drv.find_elements(By.CSS_SELECTOR, 'input[name=execution-mode]')) == 2,
                 25, 'dark rerender')
        # 深色下重新勾选设备+API+串行（刷新丢内存态）
        _click_visible(drv, '[aria-label="选择设备 %s"]' % DEVICE_NAME)
        time.sleep(0.6)
        _click_visible(drv, '[aria-label="选择 %s"]' % API_NAME)
        time.sleep(0.6)
        mpar, mser = _radio(drv, 'execution-mode')
        assert mser.get_attribute('disabled') is None, '深色下混选应可操作'
        mser.click()
        time.sleep(0.6)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'step1_serial_dark.png'))
        print('④ 深色截图：OK')

        print('=== INT-1060 执行模式控件实测全部通过 ===')
        if task_id:
            print('NOTE cleanup: stop task id', task_id)
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
