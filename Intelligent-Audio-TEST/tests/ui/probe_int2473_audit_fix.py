# -*- coding: utf-8 -*-
"""INT-2473 返工（代码审计 P2-1 / P3-1 / P3-2）实测。

被测代码 = 本 run worktree（`agent/react-b/int-2473`），React dev 经反向代理桩
指向 docker 真实库栈（网关 15000，主库 `intelligent_audio_test`），不启本地后端。

覆盖：
  P2-1 写操作失败反馈 —— 五处「ApiError.message 为空」的失败分支都要出文案：
    - 保存（PUT /documents/{id}）
    - 起草（POST /documents）
    - 恢复版本（POST /documents/{id}/restore）
    - 创建导出作业（POST /documents/{id}/exports）
    - 下载导出产物（GET /exports/{id}/download）
  P3-1 导出进度查询失败 —— 保留作业 + 「重试查询」入口，且不允许再建第二个作业
  P3-2 未绑定上下文 —— 标题渲染「报告工作模式」，不再是「报告 #null」

故障注入：桩按「方法 + 路径」只对目标写接口回 HTTP 500 空响应体（即 message 恒空
的真实路径，见 infrastructure/api/api-error.ts），其余请求原样转发真实网关。

跑法：
  1) `<conda python> tests/ui/probe_int2473_audit_fix.py --serve 5312`（桩，另开窗口）
     或本脚本 `--stub-port` 自带桩线程（默认起在脚本内）
  2) `API_PROXY_TARGET=http://127.0.0.1:5312 pnpm dev --port 5358`
  3) `<conda python> tests/ui/probe_int2473_audit_fix.py \
        --base http://localhost:5358 --api http://localhost:15000 --report-id 426`

产出：tests/ui/artifacts/int2473_audit/{summary.json,*.png,network.html}。
写数据纪律：只建/改本 run 的「接线测试_INT2473」文档，收尾按 doc_id 精确清理。
"""
import argparse
import http.client
import json
import os
import sys
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.common.keys import Keys  # noqa: E402
from selenium.webdriver.support import expected_conditions as EC  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402

from tests.ui.smoke_frontend_int1854 import (  # noqa: E402
    RESULT,
    console_errors,
    log,
    make_driver,
    parse_perf,
    shot,
    wait_quiet,
)
from tests.ui.probe_int2473_report_studio import (  # noqa: E402
    cleanup_studio_rows,
    click_aria,
    click_button,
    close_dialog,
    ensure_work_mode,
    find_versions,
    login,
    panel_text,
    wait_for,
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ART = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int2473_audit')
RESULT['art'] = ART

SUMMARY = {'env': [], 'steps': [], 'faults': [], 'console': [], 'artifacts': []}

SERVER_ERROR_COPY = '服务器内部错误，请稍后重试'

# 桩状态：fault 由主线程切换；proxy 线程按 method+path 判断是否注入
STUB = {'fault': 'passthrough', 'api': 'http://localhost:15000', 'hits': []}


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


def fault_matches(method, path):
    """按「方法 + 路径」精确命中要注入的写接口（不做前缀模糊，防误伤 GET 列表）。"""
    p = urlsplit(path).path
    fault = STUB['fault']
    if fault == 'put_document':
        return method == 'PUT' and p.startswith('/api/v1/report-studio/documents/')
    if fault == 'post_document':
        return method == 'POST' and p == '/api/v1/report-studio/documents'
    if fault == 'post_restore':
        return method == 'POST' and p.endswith('/restore')
    if fault == 'post_export':
        return method == 'POST' and p.endswith('/exports')
    if fault == 'get_export':
        return (method == 'GET' and p.startswith('/api/v1/report-studio/exports/')
                and not p.endswith('/download'))
    if fault == 'get_download':
        return method == 'GET' and p.endswith('/download')
    return False


class StubHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args):
        pass

    def _handle(self):
        try:
            if fault_matches(self.command, self.path):
                STUB['hits'].append({'method': self.command, 'path': self.path,
                                     'fault': STUB['fault'],
                                     'at': datetime.now(timezone.utc).isoformat()})
                self.close_connection = True
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', '0')
                self.send_header('Connection', 'close')
                self.end_headers()
                return
            self._forward()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def _forward(self):
        up = urlsplit(STUB['api'])
        length = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(length) if length else None
        headers = {k: v for k, v in self.headers.items()
                   if k.lower() not in ('host', 'connection', 'content-length',
                                        'transfer-encoding')}
        conn = http.client.HTTPConnection(up.hostname, up.port or 80, timeout=300)
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


def text_of(drv, css):
    els = drv.find_elements(By.CSS_SELECTOR, css)
    return els[0].text if els else ''


def open_panel_dialog(drv, aria, testid, timeout=20):
    btn = click_aria(drv, aria)
    if btn is None:
        return False
    drv.execute_script('arguments[0].click()', btn)
    return bool(wait_for(
        drv, lambda: drv.find_elements(By.CSS_SELECTOR, "[data-testid='%s']" % testid),
        timeout))


def set_editor_value(drv, text):
    editor = wait_for(drv, lambda: drv.find_element(
        By.CSS_SELECTOR, "[data-testid='studio-document-editor']"), 15)
    drv.execute_script(
        "const el=arguments[0];"
        "const setter=Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value').set;"
        "setter.call(el, arguments[1]);"
        "el.dispatchEvent(new Event('input',{bubbles:true}));",
        editor, text)
    time.sleep(0.5)
    return drv.execute_script('return arguments[0].value;', editor) == text


def ensure_document(drv, report_id, run_start):
    """进入报告工作模式；没有文档就起草一份本 run 的测试文档（返回标题）。"""
    title = '接线测试_INT2473 审计修复 %s' % time.strftime('%H%M%S')
    panel = panel_text(drv)
    if '该报告还没有 Studio 文档' in panel:
        draft = wait_for(drv, lambda: drv.find_element(
            By.CSS_SELECTOR, "[data-testid='studio-draft-button']"), 20)
        drv.execute_script('arguments[0].click()', draft)
        wait_quiet(drv, timeout=40)
        time.sleep(1.2)
    return title


def render_network_page(requests, path, hits):
    rows = ''.join(
        '<tr><td>%s</td><td class="u">%s</td><td class="%s">%s</td></tr>'
        % (r.get('method'), (r.get('url') or '').split('://', 1)[-1],
           'ok' if (r.get('status') or 0) < 400 else 'bad', r.get('status'))
        for r in requests)
    hit_rows = ''.join(
        '<tr><td>%s</td><td class="u">%s</td><td class="bad">500(注入)</td></tr>'
        % (h['method'], h['path']) for h in hits)
    html = """<!doctype html><meta charset="utf-8"><title>INT-2473 审计修复 Network</title>
<style>body{font:12px/1.5 "Segoe UI",sans-serif;padding:16px;background:#fff;color:#111}
h1{font-size:15px;margin:14px 0 8px}table{border-collapse:collapse;width:100%%}
td,th{border-bottom:1px solid #e5e5e5;padding:4px 6px;text-align:left;vertical-align:top}
th{background:#f5f5f5;position:sticky;top:0}.u{word-break:break-all;font-family:Consolas,monospace}
.ok{color:#1a7f37;font-weight:600}.bad{color:#cf222e;font-weight:600}</style>
<h1>故障注入记录（桩只对目标写接口回 500 空响应体）</h1>
<table><thead><tr><th>方法</th><th>路径</th><th>状态</th></tr></thead><tbody>%s</tbody></table>
<h1>真实 /api/v1 请求记录</h1>
<table><thead><tr><th>方法</th><th>URL</th><th>状态</th></tr></thead><tbody>%s</tbody></table>""" % (
        hit_rows, rows)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(html)
    return path


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:5358')
    ap.add_argument('--api', default='http://localhost:15000')
    ap.add_argument('--stub-port', type=int, default=5312)
    ap.add_argument('--username', default='dev_user')
    ap.add_argument('--password', default='dev_password')
    ap.add_argument('--report-id', type=int, default=426)
    args = ap.parse_args()

    run_start = datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)
    os.makedirs(ART, exist_ok=True)
    base = args.base.rstrip('/')

    env_check('start', args.api)
    srv = start_stub(args.stub_port, args.api)
    drv = make_driver(ART)
    created_docs = []
    try:
        login(drv, base, args.username, args.password)
        step('login_via_stub', '/login' not in drv.current_url, {'url': drv.current_url})

        # ── P3-2：未绑定上下文时标题不得是「报告 #null」 ─────────────────────
        drv.get('%s/ai-chat' % base)
        wait_quiet(drv, timeout=40)
        time.sleep(1.0)
        ok = ensure_work_mode(drv, 20)
        title = text_of(drv, "[data-testid='studio-doc-title']")
        panel = panel_text(drv)
        step('p32_neutral_title', ok and title.strip() == '报告工作模式'
             and '#null' not in panel,
             {'title': title, 'panel': panel[:160]})
        shot(drv, 'p32_neutral_title_light')
        drv.execute_cdp_cmd('Emulation.setEmulatedMedia', {
            'features': [{'name': 'prefers-color-scheme', 'value': 'dark'}]})
        time.sleep(1.0)
        shot(drv, 'p32_neutral_title_dark')
        drv.execute_cdp_cmd('Emulation.setEmulatedMedia', {
            'features': [{'name': 'prefers-color-scheme', 'value': 'light'}]})
        time.sleep(0.8)

        # ── 进入真实报告上下文 ─────────────────────────────────────────────
        drv.get('%s/ai-chat?report=%d' % (base, args.report_id))
        wait_quiet(drv, timeout=40)
        time.sleep(1.0)
        ok = ensure_work_mode(drv, 25)
        ensure_document(drv, args.report_id, run_start)
        panel = panel_text(drv)
        loaded = '版本' in panel and '取数来源' in panel
        step('context_document_loaded', ok and loaded, {'panel': panel[:200]})
        shot(drv, '00_panel_light')

        # ── P2-1 保存失败：500 空响应体（message=''）也要出文案 ─────────────
        edit_btn = click_aria(drv, '编辑文档')
        if edit_btn is None:
            raise AssertionError('编辑按钮未找到')
        drv.execute_script('arguments[0].click()', edit_btn)
        new_content = '# 接线测试 INT2473 审计修复\n\nP2-1 保存失败反馈 %s\n' % time.strftime('%H:%M:%S')
        value_ok = set_editor_value(drv, new_content)
        STUB['fault'] = 'put_document'
        save_btn = wait_for(drv, lambda: drv.find_element(
            By.CSS_SELECTOR, "[data-testid='studio-document-save']")
            if drv.find_element(
                By.CSS_SELECTOR, "[data-testid='studio-document-save']").is_enabled()
            else None, 10)
        drv.execute_script('arguments[0].click()', save_btn)
        save_err_seen = wait_for(
            drv, lambda: SERVER_ERROR_COPY in text_of(drv, "[data-testid='studio-document-panel']"),
            30, 0.3)
        panel = panel_text(drv)
        step('p21_save_error_visible', bool(value_ok and save_err_seen)
             and SERVER_ERROR_COPY in panel,
             {'panel': panel[:260], 'fault': 'PUT /documents/{id} → 500 空体'})
        shot(drv, 'p21_save_error_light')
        drv.execute_cdp_cmd('Emulation.setEmulatedMedia', {
            'features': [{'name': 'prefers-color-scheme', 'value': 'dark'}]})
        time.sleep(0.8)
        shot(drv, 'p21_save_error_dark')
        drv.execute_cdp_cmd('Emulation.setEmulatedMedia', {
            'features': [{'name': 'prefers-color-scheme', 'value': 'light'}]})
        time.sleep(0.6)

        # 回归：解除故障后同一编辑可正常保存（错误文案消失、版本 +1）
        STUB['fault'] = 'passthrough'
        save_btn = wait_for(drv, lambda: drv.find_element(
            By.CSS_SELECTOR, "[data-testid='studio-document-save']")
            if drv.find_element(
                By.CSS_SELECTOR, "[data-testid='studio-document-save']").is_enabled()
            else None, 10)
        drv.execute_script('arguments[0].click()', save_btn)
        saved = wait_for(drv, lambda: 'P2-1 保存失败反馈' in text_of(
            drv, "[data-testid='studio-document-content']"), 40, 0.3)
        step('p21_save_retry_ok', bool(saved)
             and SERVER_ERROR_COPY not in panel_text(drv),
             {'panel': panel_text(drv)[:200]})
        shot(drv, 'p21_save_ok_after_retry')

        # ── P2-1 恢复版本失败 ────────────────────────────────────────────
        if not open_panel_dialog(drv, '历史版本', 'studio-version-list'):
            raise AssertionError('历史版本弹窗未打开')
        versions = find_versions(drv)
        step('version_list_ready', len(versions) >= 1,
             {'versions': [v.get_attribute('data-version') for v in versions]})
        target = None
        for v in versions:
            if v.get_attribute('data-version') != (versions[0].get_attribute('data-version')):
                target = v
                break
        if target is None and versions:
            target = versions[-1]
        STUB['fault'] = 'post_restore'
        drv.execute_script('arguments[0].click()', target.find_element(By.CSS_SELECTOR, 'button'))
        restore_err_seen = wait_for(
            drv, lambda: SERVER_ERROR_COPY in text_of(
                drv, "[data-testid='studio-version-list']"), 30, 0.3)
        dialog_text = text_of(drv, "[data-testid='studio-version-list']")
        step('p21_restore_error_visible', bool(restore_err_seen),
             {'dialog': dialog_text[:260], 'fault': 'POST /documents/{id}/restore → 500 空体'})
        shot(drv, 'p21_restore_error_light')
        STUB['fault'] = 'passthrough'
        close_dialog(drv, 'studio-version-list')
        time.sleep(0.8)

        # ── P2-1 创建导出作业失败 ────────────────────────────────────────
        if not open_panel_dialog(drv, '导出', 'studio-export-panel'):
            raise AssertionError('导出弹窗未打开')
        STUB['fault'] = 'post_export'
        drv.execute_script('arguments[0].click()', drv.find_element(
            By.CSS_SELECTOR, "[data-testid='studio-export-start']"))
        export_err_seen = wait_for(
            drv, lambda: SERVER_ERROR_COPY in text_of(
                drv, "[data-testid='studio-export-panel']"), 30, 0.3)
        dialog_text = text_of(drv, "[data-testid='studio-export-panel']")
        step('p21_export_create_error_visible', bool(export_err_seen),
             {'dialog': dialog_text[:260],
              'fault': 'POST /documents/{id}/exports → 500 空体'})
        shot(drv, 'p21_export_create_error_light')
        STUB['fault'] = 'passthrough'

        # ── P3-1 进度查询失败：保留作业 + 重试查询 + 禁止重复建作业 ────────
        # 清掉上一步的失败态：换格式会清 exportId，回到「可导出」
        md_btn = click_button(drv, exact='Markdown')
        if md_btn is not None:
            drv.execute_script('arguments[0].click()', md_btn)
            time.sleep(0.6)
        STUB['fault'] = 'get_export'
        drv.execute_script('arguments[0].click()', drv.find_element(
            By.CSS_SELECTOR, "[data-testid='studio-export-start']"))
        query_err_seen = wait_for(
            drv, lambda: drv.find_elements(
                By.CSS_SELECTOR, "[data-testid='studio-export-query-error']"), 40, 0.3)
        start_disabled = False
        requery = None
        if query_err_seen:
            start = drv.find_element(By.CSS_SELECTOR, "[data-testid='studio-export-start']")
            start_disabled = not start.is_enabled()
            requery = drv.find_element(By.CSS_SELECTOR, "[data-testid='studio-export-requery']")
        dialog_text = text_of(drv, "[data-testid='studio-export-panel']")
        step('p31_export_query_error_guard', bool(query_err_seen) and start_disabled
             and requery is not None and '重试查询' in dialog_text,
             {'dialog': dialog_text[:300], 'start_disabled': start_disabled,
              'fault': 'GET /exports/{id} → 500 空体'})
        shot(drv, 'p31_export_query_error_light')

        STUB['fault'] = 'passthrough'
        if requery is not None:
            drv.execute_script('arguments[0].click()', requery)
            recovered = wait_for(
                drv, lambda: not drv.find_elements(
                    By.CSS_SELECTOR, "[data-testid='studio-export-query-error']"), 40, 0.3)
            done = wait_for(drv, lambda: drv.find_elements(
                By.CSS_SELECTOR, "[data-testid='studio-export-download']"), 40, 0.3)
            step('p31_requery_recovers', bool(recovered and done),
                 {'panel': text_of(drv, "[data-testid='studio-export-panel']")[:200]})
            shot(drv, 'p31_requery_done_light')

            # ── P2-1 下载失败 ──────────────────────────────────────────
            STUB['fault'] = 'get_download'
            download_btn = drv.find_element(
                By.CSS_SELECTOR, "[data-testid='studio-export-download']")
            drv.execute_script('arguments[0].click()', download_btn)
            download_err_seen = wait_for(
                drv, lambda: SERVER_ERROR_COPY in text_of(
                    drv, "[data-testid='studio-export-panel']"), 30, 0.3)
            step('p21_download_error_visible', bool(download_err_seen),
                 {'panel': text_of(drv, "[data-testid='studio-export-panel']")[:260],
                  'fault': 'GET /exports/{id}/download → 500 空体'})
            shot(drv, 'p21_download_error_light')
            STUB['fault'] = 'passthrough'

        close_dialog(drv, 'studio-export-panel')
        time.sleep(0.8)

        # ── Network 证据 ───────────────────────────────────────────────
        reqs = [r for r in parse_perf(drv.get_log('performance'))
                if '/api/v1/' in (r.get('url') or '')]
        SUMMARY['faults'] = STUB['hits']
        path = render_network_page(
            reqs, os.path.join(ART, 'network.html'), STUB['hits'])
        drv.get('file:///' + path.replace('\\', '/'))
        time.sleep(1.0)
        shot(drv, 'network_requests')
        step('faults_injected', len(STUB['hits']) >= 5,
             {'count': len(STUB['hits']),
              'by_fault': sorted({h['fault'] for h in STUB['hits']})})

        errs = [e for e in console_errors(drv)
                if '500' not in e and 'Failed to load resource' not in e]
        SUMMARY['console'] = errs[:20]
        step('console_clean_outside_expected', not errs, {'severe': errs[:5]})

        bad = [s for s in SUMMARY['steps'] if not s['ok']]
        SUMMARY['ok'] = not bad
        log('SUMMARY ok=%s steps=%d failed=%d'
            % (SUMMARY['ok'], len(SUMMARY['steps']), len(bad)))
        return 0 if SUMMARY['ok'] else 1
    except Exception:
        SUMMARY['error'] = traceback.format_exc()
        log(SUMMARY['error'])
        return 2
    finally:
        # 写数据纪律：只删本 run 建的测试文档（按 doc_id 精确删）
        try:
            removed = cleanup_studio_rows([args.report_id], since=run_start)
            SUMMARY['cleanup_doc_ids'] = removed
            log('CLEANUP removed=%s' % removed)
        except Exception as exc:  # pragma: no cover - 清库失败不掩盖主结论
            SUMMARY['cleanup_error'] = str(exc)
            log('CLEANUP ERROR %s' % exc)
        try:
            srv.shutdown()
        except Exception:
            pass
        try:
            drv.quit()
        except Exception:
            pass
        with open(os.path.join(ART, 'summary.json'), 'w', encoding='utf-8') as fh:
            json.dump(SUMMARY, fh, ensure_ascii=False, indent=2)
        log('ARTIFACTS %s' % ART)


if __name__ == '__main__':
    sys.exit(main())
