# -*- coding: utf-8 -*-
"""INT-1280 独立验收（测试工程师）：挑选合并向导候选加载慢 —— 慢加载可重试反馈。

环境：
- dev server: http://localhost:5315（本 run 起，rsbuild 代理 → 真实库栈网关 15000，auth off，主库 intelligent_audio_test）
- 真实库栈候选 3614 行，candidates 单查当前 ~60s（网关 gRPC DEADLINE_EXCEEDED → 400/203）
- 页面: /tasks/cherry-picks → 开始挑选 → 阶段 1 选择任务

验收（按卡内标准）：
① 候选查询在途超过 15s 阈值仍无数据 → 慢提示「候选数据较多或后端繁忙，加载较慢」替代无限骨架屏
② 点「重新加载」→ 取消在途并换键重发：Network 出现第二条 candidates 请求，慢提示消失（骨架屏恢复）
③ 不再无限骨架屏：继续等待要么任务行渲染（真实数据），要么查询失败进入错误态（有重试入口）
④ 并发合并：向导挂载 candidates 请求 = 2 条（主查询 + 共享选项），非 4 条
⑤ 浅色 + 深色 + Network 证据截图

失败落 tests/ui/artifacts/int1280_cherrypick_slow_tester/<步骤>/。
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
GATEWAYS = ['http://127.0.0.1:15000', 'http://127.0.0.1:5700']
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1280_cherrypick_slow_tester')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, OSError):
        pass

os.makedirs(ARTIFACTS, exist_ok=True)


def _health():
    for gw in GATEWAYS:
        try:
            with urllib.request.urlopen(gw + '/health', timeout=8) as r:
                body = r.read().decode('utf-8', 'replace')
            print(f'{gw} /health:', body[:160])
            assert '"database":"intelligent_audio_test"' in body, f'{gw} 不是主库！'
        except Exception as e:
            print(f'{gw} /health ERR:', e)
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
    # auth off 时被重定向到 /login → 说明网关不是 off 或会话缺失
    if '/login' in drv.current_url:
        print('WARN: redirected to login:', drv.current_url)


def _shot(drv, name):
    sub = os.path.join(ARTIFACTS, name)
    os.makedirs(sub, exist_ok=True)
    path = os.path.join(sub, 'shot.png')
    drv.save_screenshot(path)
    print('screenshot ->', path)
    return path


def _candidates_requests(logs, after_ts=None):
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
    return out


def _drain_perf(drv):
    drv.get_log('performance')
    return True


def _set_theme(drv, mode):
    drv.execute_script(
        "localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", mode)


def _open_wizard(drv):
    """导航到挑选合并页并点「开始挑选」打开向导，返回打开时刻（time.time）。"""
    _goto(drv, '/tasks/cherry-picks')
    time.sleep(1)
    _drain_perf(drv)
    btn = WebDriverWait(drv, 20).until(
        lambda d: d.find_element(By.XPATH, "//button[contains(., '开始挑选')]"))
    t0 = time.time()
    btn.click()
    print(f'wizard opened at t={t0}')
    return t0


def _wait_slow_notice(drv, t0, timeout=25):
    try:
        WebDriverWait(drv, timeout).until(
            lambda d: d.find_element(
                By.XPATH, "//*[contains(., '候选数据较多或后端繁忙，加载较慢')]"))
        print(f'SLOW NOTICE appeared at t={time.time() - t0:.1f}s')
        return True
    except Exception:
        print(f'SLOW NOTICE NOT FOUND within {timeout}s')
        return False


def _wait_terminal_state(drv, t0, timeout=90):
    """等待任务行渲染或错误态（非无限骨架屏）；返回 ('rows'|'error'|'timeout', rows)"""
    rows = 0
    deadline = time.time() + timeout
    while time.time() < deadline:
        rows = len(drv.find_elements(By.CSS_SELECTOR, "[data-testid^='pick-task-']"))
        if rows > 0:
            print(f'task rows rendered: {rows} at t={time.time() - t0:.1f}s')
            return 'rows', rows
        # 错误态：isError 文案（查询失败后替代慢提示/骨架屏）
        if drv.find_elements(By.XPATH, "//*[contains(., '加载失败')]") or \
           drv.find_elements(By.XPATH, "//*[contains(., '获取候选数据失败')]"):
            print(f'ERROR STATE at t={time.time() - t0:.1f}s')
            return 'error', rows
        time.sleep(2)
    print(f'timeout after {timeout}s, rows={rows}')
    return 'timeout', rows


def main():
    _health()
    drv = _driver()

    # 先落一个真实页面再写主题（data: URL 无 localStorage）
    drv.get(BASE + '/')
    WebDriverWait(drv, 30).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(2)

    # ---------- Run A：浅色 —— 自然慢加载（不加人工延迟） ----------
    _set_theme(drv, 'light')
    t0 = _open_wizard(drv)

    # 记录打开向导后首批 candidates 请求（并发合并证据）
    logs_mount = drv.get_log('performance')
    mount_reqs = _candidates_requests(logs_mount)
    req_urls = [r['url'] for r in mount_reqs if r['kind'] == 'request']
    print(f'Run A mount candidates requests: {len(req_urls)}')
    for u in dict.fromkeys(req_urls):
        print('   ', u[:120])
    with open(os.path.join(ARTIFACTS, 'm1_mount_requests.json'), 'w',
              encoding='utf-8') as f:
        json.dump(mount_reqs, f, ensure_ascii=False, indent=1)

    # ① 慢提示（自然慢查询，阈值 15s）
    slow1 = _wait_slow_notice(drv, t0)
    _shot(drv, 'm1_slow_notice_light')

    # ② 点「重新加载」→ 新 candidates 请求 + 慢提示消失（骨架屏恢复）
    new_reqs_before = len(_candidates_requests(drv.get_log('performance')))
    if slow1:
        try:
            retry = drv.find_element(By.XPATH, "//button[contains(., '重新加载')]")
            retry.click()
            time.sleep(2)
            notice_gone = len(drv.find_elements(
                By.XPATH, "//*[contains(., '候选数据较多或后端繁忙，加载较慢')]")) == 0
            print('after retry: slow notice gone =', notice_gone)
            _shot(drv, 'm2_after_retry_light')
        except Exception as e:
            print('retry button not found:', e)
        # 重试后的性能日志增量
        time.sleep(2)
        logs2 = drv.get_log('performance')
        reqs2 = _candidates_requests(logs2, after_ts=new_reqs_before)
        new_reqs = [r for r in reqs2 if r['kind'] == 'request']
        print(f'Run A post-retry new candidates requests: {len(new_reqs)}')
        for r in new_reqs:
            print('   ', json.dumps(r, ensure_ascii=False)[:160])
        with open(os.path.join(ARTIFACTS, 'm2_retry_requests.json'), 'w',
                  encoding='utf-8') as f:
            json.dump(reqs2, f, ensure_ascii=False, indent=1)

    # ③ 终态：任务行 or 错误态（不再无限骨架屏）
    state_a, rows_a = _wait_terminal_state(drv, t0, timeout=90)
    _shot(drv, 'm3_terminal_light')

    # ---------- Run B：深色 —— 加 3s 延迟保证超阈值稳定复现 ----------
    _set_theme(drv, 'dark')
    _goto(drv, '/tasks/cherry-picks')
    time.sleep(1)
    _drain_perf(drv)
    drv.execute_cdp_cmd('Network.enable', {})
    drv.execute_cdp_cmd('Network.emulateNetworkConditions', {
        'offline': False, 'latency': 3000,
        'downloadThroughput': -1, 'uploadThroughput': -1,
    })
    btn2 = WebDriverWait(drv, 20).until(
        lambda d: d.find_element(By.XPATH, "//button[contains(., '开始挑选')]"))
    t0b = time.time()
    btn2.click()
    print(f'dark wizard opened at t={t0b}')
    slow2 = _wait_slow_notice(drv, t0b)
    _shot(drv, 'm4_slow_notice_dark')
    state_b, rows_b = _wait_terminal_state(drv, t0b, timeout=90)
    _shot(drv, 'm5_terminal_dark')
    drv.execute_cdp_cmd('Network.emulateNetworkConditions', {
        'offline': False, 'latency': 0,
        'downloadThroughput': -1, 'uploadThroughput': -1,
    })

    drv.quit()

    print()
    print('=== SUMMARY ===')
    print(f'Run A (light): slow_notice={slow1}, terminal={state_a} rows={rows_a}')
    print(f'Run B (dark):  slow_notice={slow2}, terminal={state_b} rows={rows_b}')
    print(f'Run A mount candidates requests: {len(req_urls)} (expect 2, not 4)')
    print('DONE')


if __name__ == '__main__':
    main()
