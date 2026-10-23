# -*- coding: utf-8 -*-
"""INT-1437 临时验证 mock（不提交/用毕即停）：只服务 /api/v1/apis 家族，镜像
后端 INT-1177/1178 密钥池契约：GET 返回 api_keys_summary（完整 key 不回显）、
POST/PUT 接受 api_keys 数组、未传 api_keys 保留既有池。其余请求经 dev proxy 走
真实库栈 5700。"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

# 内存「库」：seed 一条已配 2 密钥的 API（验证编辑回显摘要）与一条单值 API
APIS = []
COUNTER = [100]


def _endpoint(ep_id, url, summary):
    return {
        'id': ep_id, 'endpoint': url, 'name': '主端点',
        'max_process': 5, 'max_timeout': 30, 'max_audio_duration': 60,
        'status': 'online', 'health_score': 90, 'priority': 1,
        'description': None, 'api_keys_summary': summary,
    }


def _seed():
    APIS.append({
        'id': 1, 'name': '演示密钥池API', 'vendor': 'openai', 'description': 'seeded 2 密钥',
        'status': 'online', 'meta': {}, 'proxy_type': None, 'proxy_url': None,
        'algorithm_type': 'voice_llm', 'default_max_process': 5,
        'default_max_timeout': 30, 'default_max_audio_duration': 60,
        'health_score': 90, 'output_types': None, 'device_type': None,
        'adapter_class': None, 'audio_config': None, 'rms_spl_mapping_id': None,
        'created_at': '2026-10-23T10:00:00', 'updated_at': '2026-10-23T10:00:00',
        'endpoints': [
            _endpoint('ep-1', 'https://ep.example.com/v1/asr', {'count': 2, 'tails': ['ab12', 'cd34']}),
        ],
        # 写侧镜像：既有池（供「留空保存保留」语义）
        '_pool': {'https://ep.example.com/v1/asr': ['sk-full-secret-1', 'sk-full-secret-2']},
    })
    APIS.append({
        'id': 2, 'name': '演示单值API', 'vendor': 'openai', 'description': '仅 meta.api_key',
        'status': 'online', 'meta': {'api_key': 'sk-single-xxx'}, 'proxy_type': None, 'proxy_url': None,
        'algorithm_type': 'voice_llm', 'default_max_process': 5,
        'default_max_timeout': 30, 'default_max_audio_duration': 60,
        'health_score': 90, 'output_types': None, 'device_type': None,
        'adapter_class': None, 'audio_config': None, 'rms_spl_mapping_id': None,
        'created_at': '2026-10-23T10:00:00', 'updated_at': '2026-10-23T10:00:00',
        'endpoints': [
            _endpoint('ep-2', 'https://ep.example.com/v2/asr', None),
        ],
        '_pool': {},
    })


def _to_public(api):
    # 读侧剥离完整 key：只保留 api_keys_summary
    out = {k: v for k, v in api.items() if not k.startswith('_')}
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get('Content-Length', 0))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode('utf-8'))
        except Exception:
            return {}

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/v1/apis':
            q = parse_qs(parsed.query)
            keyword = q.get('keyword', [''])[0]
            items = [_to_public(a) for a in APIS]
            if keyword:
                items = [a for a in items if keyword in (a.get('name') or '')]
            self._send(200, {'success': True, 'code': 0, 'data': {
                'items': items, 'total': len(items), 'page': 1, 'per_page': 1000, 'pages': 1}})
        else:
            self._send(404, {'success': False, 'code': 404, 'message': 'not found'})

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/v1/apis':
            body = self._read_body()
            COUNTER[0] += 1
            api_id = COUNTER[0]
            endpoints = body.get('endpoints') or []
            public_eps, pool = [], {}
            for ep in endpoints:
                keys = ep.get('api_keys')
                summary = {'count': len(keys), 'tails': [k[-4:] for k in keys]} if keys else None
                public_eps.append(_endpoint(str(api_id) + '-' + str(len(public_eps) + 1),
                                            ep.get('endpoint'), summary))
                if keys:
                    pool[ep.get('endpoint')] = keys
            api = {
                'id': api_id, 'name': body.get('name'), 'vendor': body.get('vendor'),
                'description': body.get('description'), 'status': body.get('status', 'offline'),
                'meta': body.get('meta') or {}, 'proxy_type': body.get('proxy_type'),
                'proxy_url': body.get('proxy_url'), 'algorithm_type': body.get('algorithm_type'),
                'default_max_process': body.get('default_max_process'),
                'default_max_timeout': body.get('default_max_timeout'),
                'default_max_audio_duration': body.get('default_max_audio_duration'),
                'health_score': body.get('health_score'), 'output_types': None, 'device_type': None,
                'adapter_class': None, 'audio_config': None, 'rms_spl_mapping_id': None,
                'created_at': '2026-10-23T11:00:00', 'updated_at': '2026-10-23T11:00:00',
                'endpoints': public_eps, '_pool': pool,
            }
            APIS.append(api)
            self._send(200, {'success': True, 'code': 0, 'data': {'id': api_id}})
        else:
            self._send(404, {'success': False, 'code': 404, 'message': 'not found'})

    def do_PUT(self):
        parsed = urlparse(self.path)
        prefix = '/api/v1/apis/'
        if parsed.path.startswith(prefix):
            try:
                api_id = int(parsed.path[len(prefix):])
            except ValueError:
                self._send(400, {'success': False, 'code': 400, 'message': 'bad id'})
                return
            body = self._read_body()
            api = next((a for a in APIS if a['id'] == api_id), None)
            if api is None:
                self._send(404, {'success': False, 'code': 404, 'message': 'not found'})
                return
            if 'name' in body:
                api['name'] = body['name']
            if 'endpoints' in body:
                public_eps, new_pool = [], dict(api.get('_pool') or {})
                for ep in body['endpoints']:
                    keys = ep.get('api_keys')
                    url = ep.get('endpoint')
                    if keys is None:
                        # 未显式传 api_keys → 保留既有池（后端按 endpoint URL 匹配）
                        existing = api.get('_pool', {}).get(url)
                        keys = existing if existing else None
                    else:
                        new_pool[url] = keys
                    summary = {'count': len(keys), 'tails': [k[-4:] for k in keys]} if keys else None
                    public_eps.append(_endpoint(str(api_id) + '-' + str(len(public_eps) + 1), url, summary))
                api['endpoints'] = public_eps
                api['_pool'] = new_pool
            self._send(200, {'success': True, 'code': 0, 'data': None})
        else:
            self._send(404, {'success': False, 'code': 404, 'message': 'not found'})

    def do_DELETE(self):
        parsed = urlparse(self.path)
        prefix = '/api/v1/apis/'
        if parsed.path.startswith(prefix):
            try:
                api_id = int(parsed.path[len(prefix):])
            except ValueError:
                self._send(400, {'success': False, 'code': 400, 'message': 'bad id'})
                return
            global APIS
            APIS = [a for a in APIS if a['id'] != api_id]
            self._send(200, {'success': True, 'code': 0, 'data': None})
        else:
            self._send(404, {'success': False, 'code': 404, 'message': 'not found'})


def main():
    _seed()
    port = int(__import__('os').environ.get('MOCK_APIS_PORT', '5701'))
    srv = HTTPServer(('127.0.0.1', port), Handler)
    print('INT-1437 mock /apis listening on %d' % port, flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
