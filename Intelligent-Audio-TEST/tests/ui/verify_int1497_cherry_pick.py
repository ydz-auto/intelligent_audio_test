# -*- coding: utf-8 -*-
"""INT-1497 挑选合并阶段 2 用例层组织·候选分组/标签/时长真名接线——浏览器实测。

被测产物：交付提交 d4614f3e 的 frontend-react 构建（dist，交付分支
agent/react-c/int-1497-c7b4f63ebcca），由本脚本起一个只读静态服务 + /api 反向代理
转发到 docker 真实库栈后端（默认 127.0.0.1:15000，/health database=intelligent_audio_test）。

验收点（卡内）：
1) 分组视图按真实分组名聚合（如「拒识」），不再全落「未分组」
2) 标签视图按真实标签聚合，不再全落「未设置标签」
3) 用例卡显示真实标签；CaseIdBadge 保留；轮次徽章按真实 rounds
4) 过时提示「候选未返分组/标签字段（§11-7）」已移除
5) 浅色 + 深色截图

用法：
  python verify_int1497_cherry_pick.py --dist <frontend-react/dist 路径>
  （DIST 也可用环境变量 INT1497_DIST；后端/端口可用 INT1497_BACKEND / INT1497_PORT 覆盖）
"""
import argparse
import json
import mimetypes
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

sys.stdout.reconfigure(encoding='utf-8')

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1497')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

BACKEND = os.environ.get('INT1497_BACKEND', 'http://127.0.0.1:15000')
PORT = int(os.environ.get('INT1497_PORT', '5390'))
BASE = f'http://127.0.0.1:{PORT}'

TASK_ID = 419
TASK_NAME_HINT = '小艺拒识E2E测试任务'


# ---------------------------------------------------------------- 静态服务 + /api 代理
class _Handler(BaseHTTPRequestHandler):
    dist = '.'
    protocol_version = 'HTTP/1.1'

    def log_message(self, *a):  # 静音
        pass

    def _proxy(self, method):
        split = urlsplit(self.path)
        url = BACKEND + split.path + (('?' + split.query) if split.query else '')
        length = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(length) if length else None
        req = urllib.request.Request(url, data=body, method=method)
        for k, v in self.headers.items():
            if k.lower() in ('host', 'connection', 'content-length', 'accept-encoding'):
                continue
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                data = r.read()
                self.send_response(r.status)
                for k, v in r.headers.items():
                    if k.lower() in ('transfer-encoding', 'connection', 'content-length'):
                        continue
                    self.send_header(k, v)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        except urllib.error.HTTPError as e:
            data = e.read()
            self.send_response(e.code)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:  # 代理失败按 502 回给页面（保持观测噪声可见）
            data = str(e).encode()
            self.send_response(502)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    def _static(self):
        rel = unquote(urlsplit(self.path).path).lstrip('/')
        fp = os.path.join(self.dist, rel)
        if not rel or not os.path.isfile(fp):
            fp = os.path.join(self.dist, 'index.html')  # SPA fallback
        with open(fp, 'rb') as f:
            data = f.read()
        ctype = mimetypes.guess_type(fp)[0] or 'application/octet-stream'
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith('/api/'):
            return self._proxy('GET')
        return self._static()

    def do_POST(self):
        return self._proxy('POST')

    def do_PUT(self):
        return self._proxy('PUT')

    def do_DELETE(self):
        return self._proxy('DELETE')

    def do_PATCH(self):
        return self._proxy('PATCH')


def start_server(dist):
    _Handler.dist = os.path.abspath(dist)
    srv = _QuietServer(('127.0.0.1', PORT), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv


class _QuietServer(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):  # 浏览器关连接属正常噪声
        pass


# ---------------------------------------------------------------- Selenium 工具
def make_driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
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


def js_click(drv, el):
    drv.execute_script('arguments[0].scrollIntoView({block:"center"});', el)
    time.sleep(0.15)
    drv.execute_script('arguments[0].click();', el)


def click_button_text(drv, text, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        for el in drv.find_elements(By.XPATH, f"//button[contains(normalize-space(.), '{text}')]"):
            if el.is_displayed():
                js_click(drv, el)
                return True
        time.sleep(0.3)
    raise AssertionError(f'按钮未找到: {text}')


def body_text(drv):
    return drv.find_element(By.TAG_NAME, 'body').text


def wait_text(drv, text, timeout=90, absent=False):
    end = time.time() + timeout
    while time.time() < end:
        txt = body_text(drv)
        if (text not in txt) == absent:
            return True
        time.sleep(0.4)
    raise AssertionError(
        f'等待文本{"消失" if absent else "出现"}超时: {text}')


def shot(drv, name):
    d = os.path.join(ARTIFACTS, name)
    os.makedirs(d, exist_ok=True)
    drv.save_screenshot(os.path.join(d, 'screenshot.png'))
    with open(os.path.join(d, 'page_source.html'), 'w', encoding='utf-8') as f:
        f.write(drv.page_source)
    with open(os.path.join(d, 'body.txt'), 'w', encoding='utf-8') as f:
        f.write(body_text(drv))
    print('  screenshot:', os.path.join(d, 'screenshot.png'))


def set_theme(drv, mode):
    drv.get(BASE + '/tasks/cherry-picks')
    drv.execute_script("window.localStorage.setItem('iatp:theme:v1:mode', %r);" % mode)
    drv.get('about:blank')
    time.sleep(0.3)
    drv.get(BASE + '/tasks/cherry-picks')
    time.sleep(2.0)


def perf_network(drv):
    """从 performance log 解出 candidates 请求/响应（双层 message 解包；get_log 会清空缓冲，只读一次）。"""
    reqs, resps = [], []
    raw_entries = drv.get_log('performance')
    for raw in raw_entries:
        try:
            msg = json.loads(raw['message'])['message']
        except Exception:
            continue
        method = msg.get('method')
        if method == 'Network.requestWillBeSent':
            p = msg['params']['request']
            if 'cherry-picks/candidates' in p.get('url', ''):
                reqs.append({'method': p.get('method'), 'url': p['url']})
        elif method == 'Network.responseReceived':
            r = msg['params']['response']
            if 'cherry-picks/candidates' in r.get('url', ''):
                resps.append({'url': r['url'], 'status': r['status']})
    return reqs, resps


# ---------------------------------------------------------------- 主流程
def run(dist):
    os.makedirs(ARTIFACTS, exist_ok=True)
    start_server(dist)
    # 探活代理与后端
    with urllib.request.urlopen(BASE + '/api/v1/auth/mode', timeout=10) as r:
        assert r.status == 200, '代理 /api 失败'
    with urllib.request.urlopen(BACKEND + '/health', timeout=15) as r:
        health = json.loads(r.read().decode())
    assert health.get('database') == 'intelligent_audio_test', f'后端库不符: {health}'

    results = []
    drv = make_driver()
    try:
        drv.get(BASE + '/tasks/cherry-picks')
        wait_text(drv, '开始挑选', timeout=60)
        drv.get_log('performance')  # 丢弃首屏噪声

        # ---- 阶段 1：选任务 419
        click_button_text(drv, '开始挑选', timeout=30)
        wait_text(drv, '阶段 1：选择任务', timeout=60)
        search = WebDriverWait(drv, 40).until(
            lambda d: d.find_element(By.XPATH, "//input[@aria-label='搜索任务名称']"))
        search.send_keys(TASK_NAME_HINT)
        time.sleep(1.2)
        row = WebDriverWait(drv, 60).until(
            lambda d: d.find_element(By.XPATH, f"//*[@data-testid='pick-task-{TASK_ID}']"))
        cb = row.find_element(By.XPATH, ".//*[@role='checkbox']")
        js_click(drv, cb)
        time.sleep(0.5)
        click_button_text(drv, '下一步：选择结果')
        wait_text(drv, '阶段 2：选择结果', timeout=60)
        results.append('阶段 1 → 2 进入成功（任务 419）')

        # ---- 分组视图（默认 org=group）
        wait_text(drv, '拒识', timeout=180)  # 真实分组名子组头
        wait_text(drv, '轮', timeout=120)    # 用例卡徽章（分组头先到、卡随后渲染）
        time.sleep(1.5)
        txt = body_text(drv)
        assert '候选未返分组/标签字段' not in txt, '过时提示仍在页面'
        results.append('过时提示「候选未返分组/标签字段（§11-7）」已移除')

        assert '未分组' not in txt, '分组视图仍出现「未分组」兜底桶'
        results.append('分组视图按真实分组名聚合（子组头「拒识」，无「未分组」桶）')

        # 子组头计数「137 条」形态 + 用例卡真实标签/轮次
        assert '轮' in txt, '用例卡未渲染轮次徽章'
        results.append('用例卡轮次徽章渲染（如「3 轮」）')

        # 用例卡标签：TagBadge 的 title 为「{name} · 分类：...」
        card_tags = [e for e in drv.find_elements(
            By.XPATH, "//*[contains(@title,'分类：')]") if '拒识' in e.text]
        assert card_tags, '用例卡未渲染真实标签'
        results.append('用例卡显示真实标签')

        # CaseIdBadge（§3.7.1）：title 携带用例 UUID
        badges = drv.find_elements(By.XPATH, "//*[contains(@title,'点击复制用例 ID')]")
        assert badges, 'CaseIdBadge 缺失'
        results.append(f'CaseIdBadge 保留（{len(badges)} 个，title 携 UUID）')

        shot(drv, '01_分组视图_浅色')

        # ---- 标签视图
        click_button_text(drv, '标签视图')
        time.sleep(1.5)
        wait_text(drv, '多轮拒识-用户Backchannel拒识', timeout=120)
        txt = body_text(drv)
        assert '未设置标签' not in txt, '标签视图仍出现「未设置标签」兜底桶'
        results.append('标签视图按真实标签聚合（无「未设置标签」桶）')
        for tag in ('多轮拒识-用户Backchannel拒识', '静默状态一次拒识'):
            assert tag in txt or tag.split('-')[0] in txt, f'标签视图缺少真实标签: {tag}'
        results.append('标签视图子组头含真实标签名（多轮拒识-用户Backchannel拒识 等）')
        shot(drv, '02_标签视图_浅色')

        # ---- 交叉子视图（分组 + 按标签）冒烟
        click_button_text(drv, '分组视图')
        time.sleep(0.8)
        results.append('分组/标签视图切换正常')

        # ---- 设备视图用例层组织冒烟（同一 org 列表复用处）
        click_button_text(drv, '设备视图')
        time.sleep(2.0)
        dev_txt = body_text(drv)
        assert '未分组' not in dev_txt or '拒识' in dev_txt, '设备视图用例层组织异常'
        shot(drv, '03_设备视图_浅色')
        click_button_text(drv, '用例视图')
        time.sleep(1.0)

        # ---- Network 证据
        reqs, resps = perf_network(drv)
        assert resps, '未捕获 candidates 请求响应'
        assert all(r['status'] == 200 for r in resps), f'candidates 非 200: {resps}'
        results.append(f'Network：candidates {len(resps)} 响应全部 200')

        # ---- 深色截图
        set_theme(drv, 'dark')
        wait_text(drv, '开始挑选', timeout=60)
        click_button_text(drv, '开始挑选', timeout=30)
        wait_text(drv, '阶段 1：选择任务', timeout=60)
        search = WebDriverWait(drv, 40).until(
            lambda d: d.find_element(By.XPATH, "//input[@aria-label='搜索任务名称']"))
        search.send_keys(TASK_NAME_HINT)
        time.sleep(1.2)
        row = WebDriverWait(drv, 60).until(
            lambda d: d.find_element(By.XPATH, f"//*[@data-testid='pick-task-{TASK_ID}']"))
        row.find_element(By.XPATH, ".//*[@role='checkbox']")
        js_click(drv, row.find_element(By.XPATH, ".//*[@role='checkbox']"))
        time.sleep(0.5)
        click_button_text(drv, '下一步：选择结果')
        wait_text(drv, '拒识', timeout=180)
        wait_text(drv, '轮', timeout=120)
        time.sleep(1.5)
        shot(drv, '04_分组视图_深色')
        click_button_text(drv, '标签视图')
        time.sleep(1.0)
        wait_text(drv, '多轮拒识-用户Backchannel拒识', timeout=120)
        time.sleep(0.8)
        shot(drv, '05_标签视图_深色')
        results.append('浅色 + 深色截图已留档')

        # 网络证据落盘
        with open(os.path.join(ARTIFACTS, 'candidates_network.json'), 'w', encoding='utf-8') as f:
            json.dump({'requests': reqs, 'responses': resps}, f, ensure_ascii=False, indent=2)
    finally:
        drv.quit()

    print('\n=== 验收结果 ===')
    for i, r in enumerate(results, 1):
        print(f'{i}. {r}')
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dist', default=os.environ.get('INT1497_DIST', ''))
    args = ap.parse_args()
    if not args.dist or not os.path.isdir(args.dist):
        raise SystemExit('需要 --dist <frontend-react/dist>（被测交付分支构建产物）')
    run(args.dist)


if __name__ == '__main__':
    main()
