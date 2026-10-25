# -*- coding: utf-8 -*-
"""INT-1932 验收夹具：宿主侧 LLM 替身（两套契约，仅验收/联调用，生产零引用）。

1) eval_server 异步任务协议（供 docker 内 evaluation_service 的 AI 复核 LLM 复检调用）：
     POST /api/create_task            -> {'code':0,'data':{'eval_task_id':...}}
     GET  /api/get_status/{id}        -> {'code':0,'data':{'status':'completed','progress':100}}
     GET  /api/get_final_result/{id}  -> {'code':0,'data':{'result':{'score','reasoning',...}}}
2) OpenAI 兼容对话端点（供浏览器端 AI 复核会话「灵犀Agent 对话」直连）：
     GET  /v1/models                  -> {'data':[{'id':'int1932-mock'}]}
     POST /v1/chat/completions        -> {'choices':[{'message':{'content': <配置文本>}}]}

行为取配置 JSON（每次请求现读，改配置不用重启）：--config <path>
  {"score": 0.86, "reasoning": "...", "chat_reply": "...", "latency_ms": 0}

用法：python tests/ui/int1932_llm_stub.py --port 5312 --config tests/ui/artifacts/int1932/stub_config.json
"""
import argparse
import json
import os
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.stdout.reconfigure(encoding='utf-8')

LOCK = threading.Lock()
TASKS = {}
CONFIG_PATH = ''
LOG_PATH = ''
DEFAULT = {
    'score': 0.86,
    'reasoning': '接线测试_INT1932：复检认为原判定成立。',
    'chat_reply': '接线测试_INT1932：已复核该用例的执行与评估结果。',
    'latency_ms': 0,
}


def load_config():
    cfg = dict(DEFAULT)
    try:
        with open(CONFIG_PATH, encoding='utf-8') as f:
            cfg.update(json.load(f) or {})
    except Exception:
        pass
    return cfg


def log(kind, detail):
    try:
        with LOCK, open(LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(json.dumps({'ts': time.strftime('%H:%M:%S'), 'kind': kind,
                                'detail': detail}, ensure_ascii=False) + '\n')
    except Exception:
        pass


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):
        pass

    def _send(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('content-type', 'application/json; charset=utf-8')
        self.send_header('content-length', str(len(data)))
        self.send_header('access-control-allow-origin', '*')
        self.send_header('access-control-allow-headers', '*')
        self.send_header('access-control-allow-methods', 'GET,POST,OPTIONS')
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        n = int(self.headers.get('content-length') or 0)
        raw = self.rfile.read(n) if n else b''
        try:
            return json.loads(raw.decode('utf-8', 'replace')) if raw else {}
        except Exception:
            return {'_raw': raw.decode('utf-8', 'replace')[:500]}

    def do_OPTIONS(self):
        self._send(200, {'ok': True})

    def do_POST(self):
        path = self.path.split('?')[0]
        body = self._body()
        cfg = load_config()
        if cfg.get('latency_ms'):
            time.sleep(float(cfg['latency_ms']) / 1000.0)
        if path == '/api/create_task':
            tid = 'int1932-' + uuid.uuid4().hex[:8]
            with LOCK:
                TASKS[tid] = dict(cfg)
            log('create_task', {'eval_task_id': tid, 'payload_keys': sorted(body)[:20]})
            self._send(200, {'code': 0, 'msg': 'success', 'data': {'eval_task_id': tid}})
            return
        if path == '/v1/chat/completions':
            log('chat_completions', {'model': body.get('model'),
                                    'messages': len(body.get('messages') or [])})
            self._send(200, {'id': 'chatcmpl-int1932', 'object': 'chat.completion',
                             'model': body.get('model') or 'int1932-mock',
                             'choices': [{'index': 0, 'finish_reason': 'stop',
                                          'message': {'role': 'assistant',
                                                      'content': cfg['chat_reply']}}]})
            return
        self._send(404, {'code': 404, 'msg': 'not found'})

    def do_GET(self):
        path = self.path.split('?')[0]
        if path == '/health':
            self._send(200, {'ok': True})
            return
        if path == '/v1/models':
            self._send(200, {'object': 'list', 'data': [{'id': 'int1932-mock',
                                                         'object': 'model'}]})
            return
        if path.startswith('/api/get_status/'):
            tid = path.rsplit('/', 1)[-1]
            log('get_status', {'eval_task_id': tid})
            self._send(200, {'code': 0, 'msg': 'success',
                             'data': {'status': 'completed', 'progress': 100}})
            return
        if path.startswith('/api/get_final_result/'):
            tid = path.rsplit('/', 1)[-1]
            with LOCK:
                cfg = TASKS.get(tid) or load_config()
            result = {
                'score': cfg['score'],
                'reasoning': cfg['reasoning'],
                'per_round': [{'round_number': 0, 'score': cfg['score']}],
            }
            log('get_final_result', {'eval_task_id': tid, 'score': cfg['score']})
            self._send(200, {'code': 0, 'msg': 'success', 'data': {'result': result}})
            return
        self._send(404, {'code': 404, 'msg': 'not found'})


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=5312)
    ap.add_argument('--host', default='0.0.0.0')
    ap.add_argument('--config', required=True)
    ap.add_argument('--log', default='')
    a = ap.parse_args()
    CONFIG_PATH = a.config
    LOG_PATH = a.log or (os.path.splitext(a.config)[0] + '_requests.log')
    if not os.path.isfile(CONFIG_PATH):
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT, f, ensure_ascii=False, indent=2)
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    print(f'stub listening on {a.host}:{a.port} config={CONFIG_PATH}', flush=True)
    srv.serve_forever()
