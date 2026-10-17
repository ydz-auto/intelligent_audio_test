# -*- coding: utf-8 -*-
"""INT-644 前端静态服务 + /api 反向代理（内置 dist 直出）。

用法：python tests/ui/utils/serve_dist_int644.py <dist_dir> <port> <api_target>
  - dist_dir: frontend-react/dist（pnpm build 产物）
  - port:     5300-5399 空闲端口
  - api_target: 后端网关，如 http://127.0.0.1:8500
"""
import http.server
import os
import socketserver
import sys
import urllib.error
import urllib.request

DIST = sys.argv[1]
PORT = int(sys.argv[2])
API_TARGET = sys.argv[3]

MIME = {
    '.html': 'text/html; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.png': 'image/png',
    '.svg': 'image/svg+xml',
    '.jpg': 'image/jpeg',
    '.woff2': 'font/woff2',
    '.ttf': 'font/ttf',
    '.ico': 'image/x-icon',
}


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIST, **kwargs)

    def do_GET(self):
        if self.path.startswith('/api'):
            return self._proxy()
        return self._serve_static()

    def do_POST(self):
        if self.path.startswith('/api'):
            return self._proxy()
        self.send_error(405)

    def do_PUT(self):
        if self.path.startswith('/api'):
            return self._proxy()
        self.send_error(405)

    def do_DELETE(self):
        if self.path.startswith('/api'):
            return self._proxy()
        self.send_error(405)

    def _serve_static(self):
        p = self.path.split('?')[0]
        if p == '/':
            p = '/index.html'
        fp = os.path.join(DIST, p.lstrip('/'))
        if os.path.isfile(fp):
            ext = os.path.splitext(fp)[1]
            with open(fp, 'rb') as f:
                body = f.read()
            self.send_response(200)
            self.send_header('Content-Type', MIME.get(ext, 'application/octet-stream'))
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        # SPA fallback：非 /api 路径回 index.html（前端路由）
        with open(os.path.join(DIST, 'index.html'), 'rb') as f:
            body = f.read()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _proxy(self):
        target = API_TARGET + self.path
        length = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(length) if length else None
        req = urllib.request.Request(target, data=body, method=self.command)
        for h in ('Content-Type', 'Accept', 'Authorization'):
            if self.headers.get(h):
                req.add_header(h, self.headers[h])
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
                self.send_response(resp.status)
                ct = resp.headers.get('Content-Type', 'application/json')
                self.send_header('Content-Type', ct)
                self.send_header('Content-Length', str(len(data)))
                # 回传网关认证模式头（前端 AuthModeMismatchBanner 依赖）
                if resp.headers.get('X-Auth-Mode'):
                    self.send_header('X-Auth-Mode', resp.headers['X-Auth-Mode'])
                self.end_headers()
                self.wfile.write(data)
        except urllib.error.HTTPError as e:
            data = e.read()
            self.send_response(e.code)
            self.send_header('Content-Type', e.headers.get('Content-Type', 'application/json'))
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self.send_response(502)
            self.send_header('Content-Type', 'application/json')
            body = ('{"success":false,"message":"proxy error: %s"}' % str(e)).encode()
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def log_message(self, fmt, *args):
        sys.stdout.write('[%s] %s\n' % (self.command, self.path))


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == '__main__':
    print('serving dist=%s on :%d, api->%s' % (DIST, PORT, API_TARGET), flush=True)
    Server(('0.0.0.0', PORT), Handler).serve_forever()
