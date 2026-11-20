# -*- coding: utf-8 -*-
"""INT-2473 返工 P2-2 残留实测：任务 → 报告「解析失败但 message 为空」不得冒充暂无报告。

复核结论（INT-2473 评论 01a1d732）实测两条 message 恒空的路径都会落错分支：
  - fetch 网络层失败（ApiError.isNetworkError=true, message=''）
  - HTTP 500 空响应体（message=''）
本次修复：`features/ai-chat/index.tsx` 的解析失败文案改走 `ApiError.userMessage`
（错误码 > 服务端 message > detail > HTTP 兜底 > 网络兜底，保证非空）；
面板分支判断由 `resolveError ?` 改为 `resolveError !== null`。

跑法（环境铁律：docker 栈，不启动本地后端）：
  1) 本脚本自起反向代理桩（默认 127.0.0.1:5311）：只对
     `/api/v1/reports/by_task/` 按当前模式注入故障，其余请求原样转发真实网关。
  2) React dev server 指向桩（dev 代理 /api → 桩）：
     `API_PROXY_TARGET=http://127.0.0.1:5311 pnpm dev --port 5337`
  3) `<conda python> tests/ui/probe_int2473_p22_resolve_error.py \
        --base http://localhost:5337 --api http://localhost:15000`

逐模式断言（任务 #451 = 已完成但该任务无报告）：
  - http500_empty / network_abort：面板必须出现「任务关联报告解析失败 + 重试」，
    **不得**出现「该任务暂无关联报告」（复核缺陷场景）。network_abort 由桩断链，
    dev 代理会把它转成 504 空响应体——同样是 message 为空的路径；
    `isNetworkError` 真网络文案由 `lib/__tests__/task-report-error.test.ts` 单测覆盖。
  - http500_message：错误块显示服务端 message；
  - passthrough：真实 404 仍落「该任务暂无关联报告」（修复未误伤正常分支）。

产出：tests/ui/artifacts/int2473_p22/{summary.json,*.png,network.html}。
写数据纪律：本脚本只读真实库（只发 GET /reports/by_task 与页面加载请求），不写库。
"""
import argparse
import http.client
import json
import os
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.support import expected_conditions as EC  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402

from tests.ui.smoke_frontend_int1854 import (  # noqa: E402
    RESULT,
    body_text,
    console_errors,
    log,
    make_driver,
    parse_perf,
    shot,
    wait_quiet,
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ART = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int2473_p22')
RESULT['art'] = ART

SUMMARY = {'env': [], 'steps': [], 'stub_hits': [], 'console': [], 'artifacts': []}

# 桩状态：mode 由主线程切换，代理线程在请求到达时读取
STUB = {'mode': 'passthrough', 'api': 'http://localhost:15000', 'hits': []}
BYPASS_PREFIX = '/api/v1/reports/by_task/'


def step(name, ok, detail=None):
    rec = {'step': name, 'ok': bool(ok), 'detail': detail or {}}
    SUMMARY['steps'].append(rec)
    log('STEP %s -> %s %s' % (name, 'PASS' if ok else 'FAIL',
                              json.dumps(detail or {}, ensure_ascii=False)[:400]))
    return rec


def env_check(tag, api):
    import urllib.request
    with urllib.request.urlopen(api.rstrip('/') + '/health', timeout=20) as resp:
        health = json.loads(resp.read().decode('utf-8'))
    SUMMARY['env'].append({'tag': tag, 'health': health})
    log('ENV[%s] database=%s' % (tag, health.get('database')))
    assert health.get('database') == 'intelligent_audio_test', '环境串库: %s' % health


# ── 反向代理桩 ────────────────────────────────────────────────
class StubHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args):  # 静默，避免每请求刷屏
        pass

    def _inject(self):
        """命中 by_task：按 mode 注入故障；返回 True 表示已自行响应。"""
        mode = STUB['mode']
        STUB['hits'].append({'path': self.path, 'mode': mode,
                             'at': datetime.now(timezone.utc).isoformat()})
        self.close_connection = True
        if mode == 'network_abort':
            # 不回任何响应直接断链 → 浏览器 fetch 抛 TypeError → ApiError(isNetworkError)
            try:
                self.connection.close()
            except Exception:
                pass
            return True
        if mode == 'http500_empty':
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', '0')
            self.send_header('Connection', 'close')
            self.end_headers()
            return True
        if mode == 'http500_message':
            raw = json.dumps({'message': '报告服务暂不可用'}, ensure_ascii=False).encode('utf-8')
            self.send_response(500)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(raw)
            return True
        return False

    def _forward(self):
        up = urlsplit(STUB['api'])
        length = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(length) if length else None
        headers = {k: v for k, v in self.headers.items()
                   if k.lower() not in ('host', 'connection', 'content-length',
                                        'transfer-encoding')}
        conn = http.client.HTTPConnection(up.hostname, up.port or 80, timeout=180)
        try:
            conn.request(self.command, self.path, body=body, headers=headers)
            resp = conn.getresponse()
            self.send_response(resp.status)
            for k, v in resp.getheaders():
                if k.lower() in ('content-length', 'connection', 'transfer-encoding',
                                 'keep-alive'):
                    continue
                self.send_header(k, v)
            self.send_header('Connection', 'close')
            self.end_headers()
            self.close_connection = True
            is_stream = 'text/event-stream' in (resp.getheader('Content-Type') or '')
            reader = resp.read1 if is_stream else resp.read
            while True:
                chunk = reader(16384) if is_stream else resp.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        finally:
            conn.close()

    def _handle(self):
        try:
            if self.path.startswith(BYPASS_PREFIX) and self._inject():
                return
            self._forward()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    do_GET = _handle
    do_POST = _handle
    do_PUT = _handle
    do_PATCH = _handle
    do_DELETE = _handle


def start_stub(port, api):
    STUB['api'] = api
    srv = ThreadingHTTPServer(('127.0.0.1', port), StubHandler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, name='stub', daemon=True).start()
    log('STUB listening on 127.0.0.1:%d -> %s' % (port, api))
    return srv


# ── 页面操作 ──────────────────────────────────────────────────
def click_button(drv, contains=None, exact=None):
    for b in drv.find_elements(By.TAG_NAME, 'button'):
        try:
            if not b.is_displayed() or not b.is_enabled():
                continue
        except Exception:
            continue
        text = (b.text or '').strip()
        if exact and text == exact:
            return b
        if contains and contains in text:
            return b
    return None


def wait_for(drv, predicate, timeout=30, interval=0.3):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            value = predicate()
            if value:
                return value
        except Exception:
            pass
        time.sleep(interval)
    return None


def panel_text(drv):
    els = drv.find_elements(By.CSS_SELECTOR, "[data-testid='studio-document-panel']")
    return els[0].text if els else ''


def login(drv, base, username, password):
    drv.get(base + '/login')
    try:
        WebDriverWait(drv, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type=password]')))
    except Exception:
        drv.execute_script('window.localStorage.clear()')
        drv.get(base + '/login')
        WebDriverWait(drv, 45).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type=password]')))
    time.sleep(1.0)
    u = [e for e in drv.find_elements(By.CSS_SELECTOR, 'input')
         if e.get_attribute('type') in (None, 'text', 'email') and e.is_displayed()][0]
    p = [e for e in drv.find_elements(By.CSS_SELECTOR, 'input[type=password]')
         if e.is_displayed()][0]
    u.clear(); u.send_keys(username)
    p.clear(); p.send_keys(password)
    btns = [b for b in drv.find_elements(By.TAG_NAME, 'button')
            if b.is_displayed() and b.text.strip() in ('登 录', '登录')]
    if not btns:
        btns = [b for b in drv.find_elements(By.CSS_SELECTOR, 'button[type=submit]')
                if b.is_displayed()]
    drv.execute_script('arguments[0].click()', btns[0])
    WebDriverWait(drv, 45).until(lambda d: '/login' not in d.current_url)
    time.sleep(2.0)


def open_task_context(drv, base, task_id, wait_text, timeout=45):
    """打开 task 上下文页面的报告工作模式，等面板出现 wait_text。返回 (panel, ok)。"""
    drv.get('%s/ai-chat?task=%d' % (base, task_id))
    wait_quiet(drv, timeout=40)
    time.sleep(1.0)
    toggle = wait_for(drv, lambda: click_button(drv, contains='报告工作模式'), 40, 0.3)
    if toggle is None:
        return panel_text(drv), False
    drv.execute_script('arguments[0].click()', toggle)
    wait_quiet(drv, timeout=40)
    ok = wait_for(drv, lambda: wait_text in panel_text(drv), timeout, 0.3)
    return panel_text(drv), bool(ok)


def render_network_page(requests, path, title):
    rows = ''.join(
        '<tr><td>%s</td><td class="u">%s</td><td class="%s">%s</td></tr>'
        % (r.get('method'), (r.get('url') or '').split('://', 1)[-1],
           'ok' if (r.get('status') or 0) < 400 else 'bad', r.get('status'))
        for r in requests)
    html = """<!doctype html><meta charset="utf-8"><title>%s</title>
<style>body{font:12px/1.5 "Segoe UI",sans-serif;padding:16px;background:#fff;color:#111}
h1{font-size:15px;margin:0 0 8px}table{border-collapse:collapse;width:100%%}
td,th{border-bottom:1px solid #e5e5e5;padding:4px 6px;text-align:left;vertical-align:top}
th{background:#f5f5f5;position:sticky;top:0}.u{word-break:break-all;font-family:Consolas,monospace}
.ok{color:#1a7f37;font-weight:600}.bad{color:#cf222e;font-weight:600}</style>
<h1>%s</h1>
<table><thead><tr><th>方法</th><th>URL</th><th>状态</th></tr></thead><tbody>%s</tbody></table>""" % (
        title, title, rows)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(html)
    return path


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:5337')
    ap.add_argument('--api', default='http://localhost:15000')
    ap.add_argument('--stub-port', type=int, default=5311)
    ap.add_argument('--username', default='dev_user')
    ap.add_argument('--password', default='dev_password')
    ap.add_argument('--task-without-report-id', type=int, default=451)
    ap.add_argument('--task-with-report-id', type=int, default=460)
    ap.add_argument('--report-id', type=int, default=426)
    args = ap.parse_args()

    os.makedirs(ART, exist_ok=True)
    base = args.base.rstrip('/')

    srv = start_stub(args.stub_port, args.api)
    env_check('start', args.api)
    drv = make_driver(ART)
    try:
        # 代理链自检：登录也经桩转发（证明非目标请求转发忠实）
        login(drv, base, args.username, args.password)
        step('login_via_stub', '/login' not in drv.current_url, {'url': drv.current_url})

        # 1) HTTP 500 空响应体（复核缺陷场景之首）
        STUB['mode'] = 'http500_empty'
        panel, ok = open_task_context(drv, base, args.task_without_report_id,
                                      '任务关联报告解析失败')
        step('http500_empty_error_block', ok
             and '任务关联报告解析失败' in panel
             and '该任务暂无关联报告' not in panel
             and '未绑定报告上下文' not in panel
             and '重试' in panel,
             {'panel': panel[:260], 'expect': '服务器内部错误，请稍后重试'})
        shot(drv, 'p22_http500_empty_light')

        # 2) 网络层失败（断链 → fetch TypeError → isNetworkError）
        STUB['mode'] = 'network_abort'
        panel, ok = open_task_context(drv, base, args.task_without_report_id,
                                      '任务关联报告解析失败')
        step('network_abort_error_block', ok
             and '任务关联报告解析失败' in panel
             and '该任务暂无关联报告' not in panel
             and '重试' in panel,
             {'panel': panel[:260],
              'expect': '桩断链后由 dev 代理回 504 空响应体，文案同样不能为空'})
        shot(drv, 'p22_network_abort_light')

        # 3) HTTP 500 + 服务端 message（对照组：错误块显示服务端文案）
        STUB['mode'] = 'http500_message'
        panel, ok = open_task_context(drv, base, args.task_without_report_id,
                                      '任务关联报告解析失败')
        step('http500_message_error_block', ok
             and '报告服务暂不可用' in panel
             and '该任务暂无关联报告' not in panel,
             {'panel': panel[:260]})
        shot(drv, 'p22_http500_message_light')

        # 4) passthrough：真实 404 仍落「该任务暂无关联报告」（修复未误伤）
        STUB['mode'] = 'passthrough'
        panel, ok = open_task_context(drv, base, args.task_without_report_id,
                                      '该任务暂无关联报告')
        step('passthrough_task_no_report', ok and '该任务暂无关联报告' in panel
             and '任务关联报告解析失败' not in panel,
             {'panel': panel[:260]})
        shot(drv, 'p22_passthrough_no_report_light')

        # 5) passthrough + 任务有报告：来源卡「任务 #y → 报告 #x」，文档区正常
        panel, ok = open_task_context(drv, base, args.task_with_report_id, '取数来源')
        step('passthrough_task_with_report',
             ok and ('→ 报告 #%d' % args.report_id) in panel,
             {'panel': panel[:260]})
        shot(drv, 'p22_task_with_report_light')

        # 深色：错误态在深色主题下同样成立（系统主题走 CDP prefers-color-scheme）
        drv.execute_cdp_cmd('Emulation.setEmulatedMedia', {
            'features': [{'name': 'prefers-color-scheme', 'value': 'dark'}]})
        STUB['mode'] = 'http500_empty'
        panel, ok = open_task_context(drv, base, args.task_without_report_id,
                                      '任务关联报告解析失败')
        step('http500_empty_error_block_dark', ok and '任务暂无关联报告' not in panel,
             {'panel': panel[:200],
              'html_dark': drv.execute_script(
                  "return document.documentElement.classList.contains('dark')")})
        shot(drv, 'p22_http500_empty_dark')
        drv.execute_cdp_cmd('Emulation.setEmulatedMedia', {
            'features': [{'name': 'prefers-color-scheme', 'value': 'light'}]})

        # Network 记录（真实 /api/v1 请求 + 注入命中）
        reqs = [r for r in parse_perf(drv.get_log('performance'))
                if '/api/v1/' in (r.get('url') or '')]
        SUMMARY['stub_hits'] = STUB['hits']
        path = render_network_page(
            reqs, os.path.join(ART, 'p22_network.html'),
            'INT-2473 P2-2 返工 · 真实 /api/v1 请求与故障注入记录')
        drv.get('file:///' + path.replace('\\', '/'))
        time.sleep(1.0)
        shot(drv, 'p22_network_requests')
        step('by_task_injected', any(
            h['mode'] != 'passthrough' for h in STUB['hits']),
            {'hits': len(STUB['hits'])})

        errs = [e for e in console_errors(drv)
                if 'by_task' not in e and '500' not in e]
        SUMMARY['console'] = errs[:20]
        step('console_clean_outside_expected', not errs, {'severe': errs[:5]})

        bad = [s for s in SUMMARY['steps'] if not s['ok']]
        SUMMARY['ok'] = not bad
        log('SUMMARY ok=%s steps=%d failed=%d'
            % (SUMMARY['ok'], len(SUMMARY['steps']), len(bad)))
        srv.shutdown()
        return 0 if SUMMARY['ok'] else 1
    except Exception:
        SUMMARY['error'] = traceback.format_exc()
        log(SUMMARY['error'])
        try:
            srv.shutdown()
        except Exception:
            pass
        return 2
    finally:
        try:
            drv.quit()
        except Exception:
            pass
        with open(os.path.join(ART, 'summary.json'), 'w', encoding='utf-8') as fh:
            json.dump(SUMMARY, fh, ensure_ascii=False, indent=2)
        log('ARTIFACTS %s' % ART)


if __name__ == '__main__':
    sys.exit(main())
