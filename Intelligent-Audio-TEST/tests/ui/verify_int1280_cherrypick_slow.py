# -*- coding: utf-8 -*-
"""INT-1280 挑选合并向导候选加载慢 —— 慢加载可重试反馈浏览器走查（React wiring）。

环境：
- dev server: http://localhost:5315（本 run 起，/api 代理 → 真实库栈 15000/5700，主库 intelligent_audio_test）
- 真实库栈 AUTH_MODE=off（dev_user '*' 放行），候选 3614 行 candidates 单查 10–45s
- 页面: /tasks/cherry-picks → 开始挑选 → 阶段 1 选择任务

验收：
① 打开向导阶段 1 后 ~15s 仍无数据 → 慢提示「候选数据较多或后端繁忙，加载较慢」替代无限骨架屏
② 慢提示点「重新加载」→ 取消在途请求重新发起（Network 出现第二条 candidates 请求），骨架屏恢复
③ 继续等待 → 任务行最终渲染（真实数据，data-testid^=pick-task-）
④ 浅色 + 深色 + Network 证据截图

失败落 tests/ui/artifacts/int1280_cherrypick_slow/<步骤>/。
"""
import json
import os
import sys
import time
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5315')
REAL_GATEWAY = 'http://127.0.0.1:15000'  # 真实库栈网关（/health → intelligent_audio_test）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1280_cherrypick_slow')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, OSError):
        pass

os.makedirs(ARTIFACTS, exist_ok=True)


def _health():
    try:
        with urllib.request.urlopen(REAL_GATEWAY + '/health', timeout=8) as r:
            body = r.read().decode('utf-8', 'replace')
        print('REAL_GATEWAY /health:', body[:200])
        assert '"database":"intelligent_audio_test"' in body, '不是主库 intelligent_audio_test！'
    except Exception as e:
        print('REAL_GATEWAY /health ERR:', e)
        raise


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium',
                              'chromedriver', 'win64')
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
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(60)
    return drv


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 30).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(2)


def _shot(drv, name):
    sub = os.path.join(ARTIFACTS, name)
    os.makedirs(sub, exist_ok=True)
    path = os.path.join(sub, 'shot.png')
    drv.save_screenshot(path)
    print('screenshot ->', path)
    return path


def _candidates_requests(logs, after=None):
    """从 performance log 提取 /tasks/cherry-picks/candidates 请求（请求+响应）。"""
    out = []
    for entry in logs:
        try:
            msg = json.loads(entry['message'])
        except Exception:
            continue
        m = msg.get('message', {})
        method = m.get('method')
        if method == 'Network.requestWillBeSent':
            req = m.get('params', {}).get('request', {})
            url = req.get('url', '')
            if '/tasks/cherry-picks/candidates' in url:
                out.append({
                    'kind': 'request',
                    'method': req.get('method'),
                    'url': url,
                    'ts': m.get('params', {}).get('timestamp'),
                    'wall': time.time(),
                })
        elif method == 'Network.responseReceived':
            resp = m.get('params', {}).get('response', {})
            url = resp.get('url', '')
            if '/tasks/cherry-picks/candidates' in url:
                out.append({
                    'kind': 'response',
                    'status': resp.get('status'),
                    'url': url,
                    'ts': m.get('params', {}).get('timestamp'),
                })
        elif method == 'Network.loadingFinished':
            p = m.get('params', {})
            # 无 url，跳过（响应计数已含状态）
            pass
    return out


def _drain_perf(drv):
    """清空已积累的 performance log（基线隔离）。"""
    logs = drv.get_log('performance')
    return logs


def _set_theme(drv, mode):
    key = 'iatp:theme:v1:mode'
    drv.execute_script(
        "localStorage.setItem(arguments[0], arguments[1]);", key, mode)


def main():
    _health()
    drv = _driver()

    # ---------- Run A：浅色 —— 慢提示 → 重新加载 → 任务行 ----------
    _goto(drv, '/tasks/cherry-picks')
    time.sleep(1)
    _drain_perf(drv)

    # 点「开始挑选」打开向导（阶段 1 选择任务；候选查询此时发起）
    btn = WebDriverWait(drv, 20).until(
        lambda d: d.find_element(By.XPATH, "//button[contains(., '开始挑选')]"))
    # 打开向导后给 candidates 增加 3s 网络延迟，确保超过 15s 慢阈值稳定复现
    drv.execute_cdp_cmd('Network.enable', {})
    drv.execute_cdp_cmd('Network.emulateNetworkConditions', {
        'offline': False, 'latency': 3000,
        'downloadThroughput': -1, 'uploadThroughput': -1,
    })
    btn.click()
    t_open = time.time()
    print('wizard opened at t=%.1fs' % (time.time() - t_open))

    # ① 慢提示替代骨架屏（阈值 15s）
    try:
        WebDriverWait(drv, 25).until(
            lambda d: d.find_element(By.XPATH, "//*[contains(., '候选数据较多或后端繁忙，加载较慢')]"))
        print('SLOW NOTICE appeared at t=%.1fs' % (time.time() - t_open))
    except Exception:
        print('SLOW NOTICE NOT FOUND at t=%.1fs — 可能后端更快完成' % (time.time() - t_open))
        _shot(drv, 'm1_slow_notice_light')
        # 若数据已直接出来也算快加载通过；继续看是否已有任务行
        rows = drv.find_elements(By.CSS_SELECTOR, "[data-testid^='pick-task-']")
        print('task rows immediately present:', len(rows))
    _shot(drv, 'm1_slow_notice_light')

    # ② 点「重新加载」→ 新 candidates 请求；骨架屏恢复（慢提示暂时消失）
    try:
        retry = drv.find_element(By.XPATH, "//button[contains(., '重新加载')]")
        retry.click()
        time.sleep(1.5)
        notice_gone = len(drv.find_elements(
            By.XPATH, "//*[contains(., '候选数据较多或后端繁忙，加载较慢')]")) == 0
        print('after retry: slow notice gone =', notice_gone)
        _shot(drv, 'm2_after_retry')
    except Exception:
        print('retry button not found (数据可能已加载)')

    # 记录重试后性能日志增量
    time.sleep(2)
    logs2 = drv.get_log('performance')
    reqs2 = _candidates_requests(logs2)
    print('candidates request/response entries (run A):')
    for r in reqs2:
        print('  ', json.dumps(r, ensure_ascii=False)[:200])

    # ③ 等待任务行渲染（真实数据，候选聚合按 taskId；最坏给到 180s）
    rows_seen = 0
    deadline = time.time() + 180
    while time.time() < deadline:
        rows_seen = len(drv.find_elements(By.CSS_SELECTOR, "[data-testid^='pick-task-']"))
        if rows_seen > 0:
            break
        time.sleep(2)
    print('task rows rendered:', rows_seen, 'at t=%.1fs' % (time.time() - t_open))
    _shot(drv, 'm3_tasks_light')

    # 清除网络延迟
    drv.execute_cdp_cmd('Network.emulateNetworkConditions', {
        'offline': False, 'latency': 0,
        'downloadThroughput': -1, 'uploadThroughput': -1,
    })

    # ---------- Run B：深色 —— 慢提示 ----------
    _set_theme(drv, 'dark')
    _goto(drv, '/tasks/cherry-picks')
    time.sleep(1)
    _drain_perf(drv)
    drv.execute_cdp_cmd('Network.emulateNetworkConditions', {
        'offline': False, 'latency': 3000,
        'downloadThroughput': -1, 'uploadThroughput': -1,
    })
    btn2 = WebDriverWait(drv, 20).until(
        lambda d: d.find_element(By.XPATH, "//button[contains(., '开始挑选')]"))
    btn2.click()
    t_open2 = time.time()
    try:
        WebDriverWait(drv, 25).until(
            lambda d: d.find_element(By.XPATH, "//*[contains(., '候选数据较多或后端繁忙，加载较慢')]"))
        print('DARK SLOW NOTICE appeared at t=%.1fs' % (time.time() - t_open2))
    except Exception:
        print('DARK SLOW NOTICE NOT FOUND')
    _shot(drv, 'm4_slow_notice_dark')

    deadline2 = time.time() + 180
    while time.time() < deadline2:
        if len(drv.find_elements(By.CSS_SELECTOR, "[data-testid^='pick-task-']")) > 0:
            break
        time.sleep(2)
    _shot(drv, 'm5_tasks_dark')
    drv.execute_cdp_cmd('Network.emulateNetworkConditions', {
        'offline': False, 'latency': 0,
        'downloadThroughput': -1, 'uploadThroughput': -1,
    })

    drv.quit()
    print('DONE')


if __name__ == '__main__':
    main()
