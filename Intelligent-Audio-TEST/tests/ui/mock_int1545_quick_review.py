# -*- coding: utf-8 -*-
"""INT-1545 契约桩代理（仅此一端点，其余全透传 docker 网关 15000）。

为什么需要：docker 15000 的 POST /tasks/results/ai-review 是**同步阻塞**实现——12 个维度逐个
等 LLM 复检（每个 30~50s，本环境无供应商→逐个超时失败），整请求 8~10 分钟，远超 dev/nginx
代理超时（实测 rsbuild 代理 120s 返 504），且返回时记录已是 failed，前端根本走不到「发起
返回 running → 轮询历史」这段逻辑。为验证本卡缺陷（轮询键错配）只把该端点替换为契约桩：
返回与真实后端同形的 item（task_id=418 = 真实记录归属任务，id=261 = 真实已落库记录），
随后弹窗对 **真实** GET /tasks/results/418/ai-review-history 轮询，由真实数据推进到错误态。

其余请求（含所有 GET 历史/任务/用例）原样转发 15000，不造数据。

用法：python tests/ui/mock_int1545_quick_review.py [--port 5347] [--upstream http://127.0.0.1:15000]
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.stdout.reconfigure(encoding='utf-8')

UPSTREAM = 'http://127.0.0.1:15000'
INITIATE_PATH = '/api/v1/tasks/results/ai-review'

# 真实记录（ai_reviews id=261，result 5622，task_id=418）——只把 status 改成 running 模拟异步执行中
REAL_RECORD = {
    'id': 261,
    'result_id': 5622,
    'task_id': 418,
    'test_case_id': '0433a0b9-27ff-4832-b1e1-8912f0805764',
    'dimension_id': 132,
    'status': 'running',
    'verdict': None,
    'confidence': None,
    'reasoning': None,
    'adopted': 0,
    'adopted_by_user_id': None,
    'adopted_at': None,
    'rejected': 0,
    'rejected_by_user_id': None,
    'rejected_at': None,
    'created_at': '2026-10-23T12:01:53.871282',
    'updated_at': None,
}

SKIP_HEADERS = {
    'host', 'connection', 'content-length', 'accept-encoding', 'transfer-encoding',
    'upgrade', 'proxy-connection', 'keep-alive', 'te', 'trailer',
}


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):  # noqa: D401
        sys.stderr.write('[stub] ' + (fmt % args) + '\n')

    def _read_body(self):
        length = int(self.headers.get('content-length') or 0)
        return self.rfile.read(length) if length else b''

    def _send_json(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('content-type', 'application/json; charset=utf-8')
        self.send_header('content-length', str(len(data)))
        self.send_header('access-control-allow-origin', '*')
        self.end_headers()
        self.wfile.write(data)

    def _proxy(self, method):
        body = self._read_body() if method in ('POST', 'PUT', 'PATCH', 'DELETE') else None
        if method == 'POST' and self.path.split('?')[0] == INITIATE_PATH:
            payload = json.loads(body or b'{}')
            result_ids = payload.get('result_ids') or [REAL_RECORD['result_id']]
            item = dict(REAL_RECORD)
            item['result_id'] = result_ids[0]
            print('[stub] initiate -> task_id=418 item id=261 (status=running)', flush=True)
            self._send_json(200, {'success': True, 'code': 0, 'message': 'Success',
                                  'data': {'items': [item], 'skipped': []}})
            return
        req = urllib.request.Request(UPSTREAM + self.path, data=body, method=method)
        for key, value in self.headers.items():
            if key.lower() not in SKIP_HEADERS:
                req.add_header(key, value)
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                raw = resp.read()
                status = resp.status
                ctype = resp.headers.get('content-type', 'application/json; charset=utf-8')
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            status = exc.code
            ctype = exc.headers.get('content-type', 'application/json; charset=utf-8')
        except Exception as exc:  # noqa: BLE001
            raw = json.dumps({'success': False, 'code': 500, 'message': str(exc)}).encode()
            status = 502
            ctype = 'application/json; charset=utf-8'
        self.send_response(status)
        self.send_header('content-type', ctype)
        self.send_header('content-length', str(len(raw)))
        self.send_header('access-control-allow-origin', '*')
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self._proxy('GET')

    def do_POST(self):
        self._proxy('POST')

    def do_PUT(self):
        self._proxy('PUT')

    def do_PATCH(self):
        self._proxy('PATCH')

    def do_DELETE(self):
        self._proxy('DELETE')

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('access-control-allow-origin', '*')
        self.send_header('access-control-allow-headers', '*')
        self.send_header('access-control-allow-methods', '*')
        self.end_headers()


def main():
    global UPSTREAM
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=5347)
    ap.add_argument('--upstream', default=UPSTREAM)
    args = ap.parse_args()
    UPSTREAM = args.upstream
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'stub proxy on http://127.0.0.1:{args.port} -> {UPSTREAM}', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
