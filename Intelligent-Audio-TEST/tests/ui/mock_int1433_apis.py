# -*- coding: utf-8 -*-
"""INT-1433 临时契约 mock：只代理 /api/v1/apis（真实库栈 GET/POST /apis 被 api_url
UndefinedColumn 部署缺口阻断，见 memory api-domain-backends-broken-get-apis）。

返回与 api_gateway/schemas/api.py ApiItem/ApiEndpointItem 同形的两枚 mock API
（websocket_api + http_api，status=online），POST/PUT/DELETE/health 按契约返回。
rsbuild proxy 最长前缀 /api/v1/apis 排最前，其余 /api 走真实 5700。
仅测试期使用，run 结束前停服。
"""
import json
import threading
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 5460

# 真实库栈网关 /test-devices 拉取（启动时一次），仅把本 run 自建的在线测试设备
# 状态覆写为 online（真实设备无心跳恒 offline，无法选中做混跑验证）。
REAL_API = 'http://127.0.0.1:5700'
_REAL_DEVICES = []


def _load_real_devices():
    global _REAL_DEVICES
    try:
        import base64
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.primitives import hashes, serialization
        with urllib.request.urlopen(REAL_API + '/api/v1/auth/encryption-key', timeout=15) as resp:
            keydata = json.loads(resp.read().decode('utf-8'))
        data = keydata.get('data', keydata)
        pubkey = serialization.load_pem_public_key(data['public_key'].encode())
        ct = pubkey.encrypt('JieXianTest@2026'.encode('utf-8'),
                            padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()),
                                         algorithm=hashes.SHA256(), label=None))
        form = urllib.parse.urlencode({
            'username': '接线测试_admin',
            'password_encrypted': base64.b64encode(ct).decode('utf-8'),
            'encryption_key_id': data['kid'],
        }).encode('utf-8')
        r = urllib.request.Request(REAL_API + '/api/v1/auth/login', data=form, method='POST')
        r.add_header('Content-Type', 'application/x-www-form-urlencoded')
        with urllib.request.urlopen(r, timeout=20) as resp:
            token = json.loads(resp.read().decode('utf-8'))['access_token']
        r = urllib.request.Request(REAL_API + '/api/v1/test-devices?per_page=1000', method='GET')
        r.add_header('Authorization', 'Bearer ' + token)
        with urllib.request.urlopen(r, timeout=30) as resp:
            d = json.loads(resp.read().decode('utf-8'))
        items = (d.get('data') or {}).get('items') or []
        _REAL_DEVICES = [dict(it) for it in items]
        for it in _REAL_DEVICES:
            if (it.get('name') or '').startswith('接线测试_INT1433_dev_'):
                it['status'] = 'online'
                it['last_online_at'] = '2026-10-23T04:00:00'
        print('loaded %d real devices, test device online override' % len(_REAL_DEVICES), flush=True)
    except Exception as e:
        print('real devices load failed:', str(e)[:200], flush=True)
        _REAL_DEVICES = []

SEED_APIS = [
    {
        'id': 9001,
        'name': '接线测试_INT1433_WS_mock',
        'vendor': 'mock',
        'description': 'mock websocket api for INT-1433',
        'status': 'online',
        'meta': {},
        'proxy_type': None,
        'proxy_url': None,
        'algorithm_type': 'voice_llm',
        'default_max_process': 5,
        'default_max_timeout': 60,
        'default_max_audio_duration': 300,
        'health_score': 100,
        'endpoints': [{
            'id': 'ep-9001-1', 'endpoint': 'wss://realtime.example.com/ws',
            'name': 'Realtime WS', 'max_process': 5, 'max_timeout': 60,
            'max_audio_duration': 300, 'priority': 1, 'status': 'online',
            'health_score': 100, 'description': '',
        }],
        'output_types': [],
        'device_type': 'websocket_api',
        'adapter_class': None,
        'audio_config': {},
        'rms_spl_mapping_id': None,
        'created_at': '2026-10-23T04:00:00',
        'updated_at': '2026-10-23T04:00:00',
    },
    {
        'id': 9002,
        'name': '接线测试_INT1433_HTTP_mock',
        'vendor': 'mock',
        'description': 'mock http api for INT-1433',
        'status': 'online',
        'meta': {},
        'proxy_type': None,
        'proxy_url': None,
        'algorithm_type': 'voice_llm',
        'default_max_process': 3,
        'default_max_timeout': 60,
        'default_max_audio_duration': 300,
        'health_score': 100,
        'endpoints': [{
            'id': 'ep-9002-1', 'endpoint': 'https://http.example.com/api',
            'name': 'HTTP API', 'max_process': 3, 'max_timeout': 60,
            'max_audio_duration': 300, 'priority': 1, 'status': 'online',
            'health_score': 100, 'description': '',
        }],
        'output_types': [],
        'device_type': 'http_api',
        'adapter_class': None,
        'audio_config': {},
        'rms_spl_mapping_id': None,
        'created_at': '2026-10-23T04:00:00',
        'updated_at': '2026-10-23T04:00:00',
    },
    {
        # 无显式 device_type，端点 wss:// → 建任务路由按端点协议派生 websocket_api
        # （INT-1433 deriveApiTargetDeviceType 自动派生路径）
        'id': 9003,
        'name': '接线测试_INT1433_AUTO_WS_mock',
        'vendor': 'mock',
        'description': 'mock auto-derive websocket api for INT-1433',
        'status': 'online',
        'meta': {},
        'proxy_type': None,
        'proxy_url': None,
        'algorithm_type': 'voice_llm',
        'default_max_process': 4,
        'default_max_timeout': 60,
        'default_max_audio_duration': 300,
        'health_score': 100,
        'endpoints': [{
            'id': 'ep-9003-1', 'endpoint': 'wss://auto.example.com/ws',
            'name': 'Auto WS', 'max_process': 4, 'max_timeout': 60,
            'max_audio_duration': 300, 'priority': 1, 'status': 'online',
            'health_score': 100, 'description': '',
        }],
        'output_types': [],
        'device_type': None,
        'adapter_class': None,
        'audio_config': {},
        'rms_spl_mapping_id': None,
        'created_at': '2026-10-23T04:00:00',
        'updated_at': '2026-10-23T04:00:00',
    },
]

_locker = threading.Lock()
_apis = list(SEED_APIS)
_next_id = 9100


def _ok(data=None, code=0):
    return {'success': True, 'code': code, 'message': 'Success', 'data': data}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _read_body(self):
        n = int(self.headers.get('Content-Length') or 0)
        if n <= 0:
            return None
        raw = self.rfile.read(n)
        try:
            return json.loads(raw.decode('utf-8'))
        except Exception:
            return None

    def _send(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path == '/api/v1/test-devices':
            self._send(_ok({'items': [dict(d) for d in _REAL_DEVICES],
                            'total': len(_REAL_DEVICES), 'page': 1, 'per_page': 1000}))
            return
        if path == '/api/v1/apis':
            with _locker:
                items = [dict(a) for a in _apis]
            self._send(_ok({'items': items, 'total': len(items), 'page': 1,
                            'per_page': 1000}))
            return
        # /api/v1/apis/{id}
        if path.startswith('/api/v1/apis/'):
            api_id = path.rsplit('/', 1)[-1]
            with _locker:
                match = [a for a in _apis if str(a['id']) == api_id]
            if match:
                self._send(_ok(dict(match[0])))
            else:
                self._send({'success': False, 'code': 404, 'message': 'not found',
                            'data': None}, status=404)
            return
        self._send({'success': False, 'code': 404, 'message': 'no mock route: ' + path,
                    'data': None}, status=404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = self._read_body() or {}
        if path == '/api/v1/apis':
            with _locker:
                global _next_id
                new = {'id': _next_id, 'created_at': '2026-10-23T04:00:00',
                       'updated_at': '2026-10-23T04:00:00'}
                _next_id += 1
                new.update(body)
                if 'endpoints' in body:
                    for i, ep in enumerate(body['endpoints']):
                        ep.setdefault('id', 'ep-%d-%d' % (new['id'], i))
                _apis.append(new)
                out = dict(new)
            self._send(_ok(out), status=201)
            return
        if path.startswith('/api/v1/apis/') and path.endswith('/health'):
            api_id = path.rsplit('/', 2)[-2]
            self._send(_ok({'id': int(api_id), 'status': 'online', 'health_score': 100,
                            'endpoints_status': 'ok', 'status_code': 200,
                            'response_time': '12ms', 'error': None, 'warning': None}))
            return
        self._send({'success': False, 'code': 404, 'message': 'no mock route: ' + path,
                    'data': None}, status=404)

    def do_PUT(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = self._read_body() or {}
        if path.startswith('/api/v1/apis/'):
            api_id = path.rsplit('/', 1)[-1]
            with _locker:
                for i, a in enumerate(_apis):
                    if str(a['id']) == api_id:
                        a.update(body)
                        a['updated_at'] = '2026-10-23T04:00:00'
                        out = dict(a)
                        break
                else:
                    out = None
            if out:
                self._send(_ok(out))
            else:
                self._send({'success': False, 'code': 404, 'message': 'not found',
                            'data': None}, status=404)
            return
        self._send({'success': False, 'code': 404, 'message': 'no mock route: ' + path,
                    'data': None}, status=404)

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path.startswith('/api/v1/apis/'):
            api_id = path.rsplit('/', 1)[-1]
            with _locker:
                before = len(_apis)
                _apis[:] = [a for a in _apis if str(a['id']) != api_id]
            self._send(_ok({'deleted': before - len(_apis)}))
            return
        self._send({'success': False, 'code': 404, 'message': 'no mock route: ' + path,
                    'data': None}, status=404)


if __name__ == '__main__':
    _load_real_devices()
    srv = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    print('INT-1433 /apis + /test-devices mock listening on', PORT, flush=True)
    srv.serve_forever()
