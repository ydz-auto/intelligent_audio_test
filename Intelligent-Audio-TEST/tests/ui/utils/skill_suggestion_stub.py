# -*- coding: utf-8 -*-
"""「沉淀为 Skill」建议卡真栈探针的反向代理桩（INT-2550 打回补验用）。

为什么需要桩：后端的 `skill_draft_suggested` 事件只在「run 正常结束且本次调用
≥2 个工具」时下发；当前 docker 真栈没有可用的 LLM 供应商、库里也没有 ≥2 个
工具的 run，无法在真栈上自然造出这条事件。本桩只接管
`GET /api/v1/agent/runs/{id}/events`（SSE），其余请求（登录、会话、建 run、
Skill 列表等）**原样转发** `http://127.0.0.1:15000`，所以页面数据仍是真栈的。

用法：
  python tests/ui/utils/skill_suggestion_stub.py --port 18791
  # 前端另起：API_PROXY_TARGET=http://127.0.0.1:18791 pnpm dev --port 5352
  python tests/ui/probe_int2550_skill_suggestion.py --base http://localhost:5352 --api http://localhost:15000

帧格式与网关一致：`id: n` + `event: <type>` + `data: <平铺 snake_case JSON>`，
run_started → message_delta → skill_draft_suggested → run_finished(SUCCEEDED)。
"""
import argparse
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx

UPSTREAM = 'http://127.0.0.1:15000'
SSE_RE = re.compile(r'^/api/v1/agent/runs/([^/]+)/events')
HOP_HEADERS = {
    'host', 'content-length', 'connection', 'transfer-encoding',
    'content-encoding', 'accept-encoding',
}

SUGGESTED_NAME = 'studio-export-report'
SUGGESTED_DESCRIPTION = '基于本次 run 的执行流程沉淀的 Skill 草案'
SUGGESTED_TOOLS = ['report_get_facts', 'studio_request_export']

_lock = threading.Lock()
HITS = {'sse': 0, 'forward': 0}


def sse_body(run_id: str) -> bytes:
    """按网关 SSE 帧口径生成建议事件流（type 与载荷字段平铺）。"""
    now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

    def frame(seq, event_type, payload):
        data = {'run_id': run_id, 'sequence': seq, 'type': event_type,
                'timestamp': now, **payload}
        return 'id: %d\nevent: %s\ndata: %s\n\n' % (
            seq, event_type, json.dumps(data, ensure_ascii=False))

    frames = [
        frame(1, 'run_started', {'status': 'RUNNING', 'session_id': ''}),
        frame(2, 'message_delta', {
            'message_id': 'm-probe-1',
            'delta': '已整理本次导出流程，可以把这套步骤沉淀为可复用的 Skill。',
        }),
        frame(3, 'skill_draft_suggested', {
            'suggested_name': SUGGESTED_NAME,
            'description': SUGGESTED_DESCRIPTION,
            'tools_used': SUGGESTED_TOOLS,
            'source_skill': None,
            'created': False,
            'requires_confirmation': True,
        }),
        frame(4, 'run_finished', {'status': 'SUCCEEDED'}),
    ]
    return ''.join(frames).encode('utf-8')


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):  # 静音默认 stderr，调用方只看自己的日志
        pass

    def _write(self, status, headers, body: bytes):
        self.send_response(status)
        for key, value in headers:
            if key.lower() in HOP_HEADERS:
                continue
            self.send_header(key, value)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Connection', 'close')
        self.end_headers()
        if body:
            self.wfile.write(body)
        self.close_connection = True

    def _handle(self):
        matched = SSE_RE.match(self.path.split('?')[0])
        if self.command == 'GET' and matched:
            body = sse_body(matched.group(1))
            with _lock:
                HITS['sse'] += 1
            print('[stub] SSE skill_draft_suggested run=%s (%d bytes)'
                  % (matched.group(1), len(body)), flush=True)
            self._write(200, [
                ('Content-Type', 'text/event-stream; charset=utf-8'),
                ('Cache-Control', 'no-cache'),
                ('X-Accel-Buffering', 'no'),
            ], body)
            return

        length = int(self.headers.get('Content-Length') or 0)
        payload = self.rfile.read(length) if length else None
        headers = {k: v for k, v in self.headers.items()
                   if k.lower() not in HOP_HEADERS}
        try:
            with httpx.Client(timeout=90, trust_env=False) as client:
                resp = client.request(self.command, UPSTREAM + self.path,
                                      headers=headers, content=payload)
        except Exception as exc:  # noqa: BLE001
            body = json.dumps({'detail': 'stub upstream error: %s' % exc},
                              ensure_ascii=False).encode('utf-8')
            self._write(502, [('Content-Type', 'application/json')], body)
            return
        with _lock:
            HITS['forward'] += 1
        self._write(resp.status_code, list(resp.headers.items()), resp.content)

    do_GET = _handle
    do_POST = _handle
    do_PUT = _handle
    do_DELETE = _handle
    do_PATCH = _handle


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=18791)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print('[stub] listening 127.0.0.1:%d → %s' % (args.port, UPSTREAM),
          flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
