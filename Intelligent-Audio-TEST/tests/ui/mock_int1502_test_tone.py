# -*- coding: utf-8 -*-
"""INT-1502 环境缺口旁路：/spl/test-tone 契约桩 + 其余请求透传 5700 真实库栈。

为什么需要：本机 Windows 音频栈卡死（Audiosrv StartPending，audio_service 返回
`pyaudio shadow fixture (INT-95)`），后端 POST /spl/test-tone 恒 400「没有找到可用的
播放设备」——播放成功态（200 → 播放中 → stop）在真实栈上无法产生。此桩仅替换这两个
端点的响应（严格按 api_gateway/schemas/spl.py PlayTestToneData / StopTestToneData
的真实 envelope 形状），其余所有请求（登录、/spl、/playback-devices…）原样透传
5700 真实库栈，用于验证前端接线（播放态与停止请求）。

用法：
  python tests/ui/mock_int1502_test_tone.py --port 5810 --target http://127.0.0.1:5700
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TEST_TONE_OK = {
    'success': True,
    'code': 0,
    'message': '测试音频已在 1 个设备上播放',
    'data': {
        'devices': [
            {'device': '接线测试_SPL音箱', 'gain_db': -10.0, 'final_dbfs': -40.0, 'target_spl': 55.0},
        ],
        'duration': 5.0,
    },
}
TEST_TONE_STOP_OK = {
    'success': True,
    'code': 0,
    'message': '已停止 1 个测试音任务',
    'data': {'stopped_count': 1},
}

HOP_HEADERS = {'host', 'connection', 'content-length', 'accept-encoding', 'transfer-encoding'}

TARGET = 'http://127.0.0.1:5700'


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):  # noqa: A003
        sys.stderr.write('[stub] %s - %s\n' % (self.address_string(), fmt % args))

    def _send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        length = int(self.headers.get('Content-Length') or 0)
        return self.rfile.read(length) if length else b''

    def _proxy(self, method, body):
        url = TARGET + self.path
        req = urllib.request.Request(url, data=body if body else None, method=method)
        for key, value in self.headers.items():
            if key.lower() in HOP_HEADERS:
                continue
            req.add_header(key, value)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
                status = resp.status
                headers = resp.headers
        except urllib.error.HTTPError as exc:
            data = exc.read()
            status = exc.code
            headers = exc.headers
        except Exception as exc:  # noqa: BLE001
            self._send_json({'success': False, 'code': 500, 'message': f'上游不可达: {exc}'}, 502)
            return
        self.send_response(status)
        for key, value in headers.items():
            if key.lower() in HOP_HEADERS:
                continue
            self.send_header(key, value)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        self._proxy('GET', b'')

    def do_PUT(self):  # noqa: N802
        self._proxy('PUT', self._body())

    def do_DELETE(self):  # noqa: N802
        self._proxy('DELETE', self._body())

    def do_PATCH(self):  # noqa: N802
        self._proxy('PATCH', self._body())

    def do_POST(self):  # noqa: N802
        body = self._body()
        path = self.path.split('?', 1)[0]
        if path == '/api/v1/spl/test-tone':
            sys.stderr.write('[stub] test-tone body=%s\n' % body.decode('utf-8', 'replace'))
            self._send_json(TEST_TONE_OK)
            return
        if path == '/api/v1/spl/test-tone/stop':
            sys.stderr.write('[stub] test-tone/stop body=%s\n' % body.decode('utf-8', 'replace'))
            self._send_json(TEST_TONE_STOP_OK)
            return
        self._proxy('POST', body)


def main():
    global TARGET
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=5810)
    ap.add_argument('--target', default='http://127.0.0.1:5700')
    args = ap.parse_args()
    TARGET = args.target.rstrip('/')
    srv = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'stub listening on 127.0.0.1:{args.port} -> {TARGET}')
    srv.serve_forever()


if __name__ == '__main__':
    main()
