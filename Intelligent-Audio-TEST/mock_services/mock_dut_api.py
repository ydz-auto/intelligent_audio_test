# -*- coding: utf-8 -*-
"""被测 API DUT 替身 — 单轮被测协议 + voice_llm chat（INT-1169/1176）。

api_adapter_service 删除后，冒烟/走查/UI 测试的「被测 DUT 模拟」由本服务承担：
- /health（GET）                         健康检查
- /api/create_task（POST）               单轮异步任务创建
- /api/get_status/{task_id}（GET）       任务状态查询
- /api/get_final_result/{task_id}（GET） 最终结果查询
- /api/get_frame_results/{task_id}（GET）帧结果查询
- /api/delete_task/{task_id}（DELETE）   删除任务
- /chat（POST）                          voice_llm 多轮会话（MockDialogAdapter
                                         行为：文本回显 + 轮询预设 + 每会话计数）

行为对齐 api_adapter_service 的 MockDialogAdapter（轮询预设 zh/en 逐轮取模、
文本输入回显为 ASR、随机 200-800ms 延迟、每会话轮次计数）。单轮协议响应
格式对齐 api_task_runner 契约（{code: 0, data: {task_id/status/answer}}）。

独立可运行（仅标准库，端口取 shared/config/service_ports.py 注册值）：
    python mock_services/mock_dut_api.py [--port 5096]
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from shared.config.service_ports import MOCK_DUT_API_HTTP_PORT  # noqa: E402

DEFAULT_PORT = MOCK_DUT_API_HTTP_PORT

MOCK_RESPONSES = {
    'zh': [
        '你好，有什么可以帮助你的？',
        '好的，我明白了。',
        '今天的天气不错。',
        '让我帮你查一下。',
        '已经为你设置好了。',
        '抱歉，我没有听懂，请再说一遍。',
        '好的，正在为你处理。',
        '还有其他需要帮助的吗？',
    ],
    'en': [
        'Hello, how can I help you?',
        'OK, I understand.',
        'The weather is nice today.',
        'Let me check that for you.',
        'It has been set up for you.',
        "Sorry, I didn't catch that. Could you repeat?",
        'OK, processing your request.',
        'Is there anything else I can help with?',
    ],
}


class MockDutState:
    """运行态：任务库（task_id → {status, final_result}）+ 每会话轮次计数。"""

    def __init__(self):
        self.tasks: dict = {}
        self.session_rounds: dict = {}  # session_id -> round count
        self.hits: dict = {}


class MockDutService:
    """被测 DUT 行为：单轮协议 + voice_llm chat（MockDialogAdapter 等价）。"""

    def __init__(self, state: MockDutState):
        self._state = state

    def health(self) -> dict:
        self._count('health')
        return {'code': 0, 'msg': 'success', 'status': 'healthy'}

    def create_task(self, body: dict) -> dict:
        self._count('create_task')
        task_id = f'dut-{uuid.uuid4().hex[:8]}'
        # 立即完成（被测 DUT 替身同步返回终态）
        self._state.tasks[task_id] = {
            'task_id': task_id,
            'status': 'completed',
            'result_type': 'single_turn',
            'asr_text': '',
            'trans_text': '',
            'output': '今天天气怎么样',
            'latency': 0.0,
            'raw_response': {'mock_dut': True},
            'output_audio_path': None,
        }
        return {'code': 0, 'msg': 'success', 'data': {'task_id': task_id}}

    def get_status(self, task_id: str) -> dict:
        self._count('get_status')
        task = self._state.tasks.get(task_id)
        if not task:
            return {'code': 4004, 'msg': 'task not found'}
        return {'code': 0, 'msg': 'success',
                'data': {'task_id': task_id, 'status': task['status'],
                         'progress': 100}}

    def get_final_result(self, task_id: str) -> dict:
        self._count('get_final_result')
        task = self._state.tasks.get(task_id)
        if not task:
            return {'code': 4004, 'msg': 'result not found'}
        return {'code': 0, 'msg': 'success', 'data': {
            'answer': task['output'],
            'asr_text': task['asr_text'],
            'trans_text': task['trans_text'],
            'output': task['output'],
            'output_audio_path': task['output_audio_path'],
        }}

    def get_frame_results(self, task_id: str) -> dict:
        self._count('get_frame_results')
        return {'code': 0, 'msg': 'success', 'data': []}

    def delete_task(self, task_id: str) -> dict:
        self._count('delete_task')
        self._state.tasks.pop(task_id, None)
        return {'code': 0, 'msg': f'task {task_id} deleted'}

    def chat(self, body: dict) -> dict:
        """voice_llm chat：MockDialogAdapter 行为（回显/预设/每会话计数）。"""
        self._count('chat')
        session_id = body.get('session_id', '')
        input_type = body.get('input', {}).get('type', 'text') if isinstance(
            body.get('input'), dict) else 'text'
        input_text = body.get('input', {}).get('text', '') if isinstance(
            body.get('input'), dict) else ''
        round_number = body.get('round', 0)

        if session_id not in self._state.session_rounds:
            self._state.session_rounds[session_id] = 0
        idx = self._state.session_rounds[session_id]
        self._state.session_rounds[session_id] += 1

        zh_responses = MOCK_RESPONSES['zh']
        en_responses = MOCK_RESPONSES['en']
        asr_text = zh_responses[idx % len(zh_responses)]
        trans_text = en_responses[idx % len(en_responses)]

        if input_type == 'text' and input_text:
            asr_text = input_text

        simulated_latency = random.uniform(0.2, 0.8)
        time.sleep(simulated_latency)

        return {
            'code': 0,
            'msg': 'success',
            'asr_text': asr_text,
            'trans_text': trans_text,
            'output': asr_text,
            'session_id': session_id,
            'latency': round(simulated_latency, 3),
            'raw_response': {'mock': True, 'round': round_number,
                             'input_type': input_type},
        }

    def _count(self, key: str):
        self._state.hits[key] = self._state.hits.get(key, 0) + 1


class MockDutRequestHandler(BaseHTTPRequestHandler):
    """HTTP 请求分发：单轮协议 + /chat + /health + /__control。"""

    def do_GET(self):  # noqa: N802
        self._dispatch('GET')

    def do_POST(self):  # noqa: N802
        self._dispatch('POST')

    def do_DELETE(self):  # noqa: N802
        self._dispatch('DELETE')

    def _dispatch(self, method: str):
        path = self.path.split('?')[0].rstrip('/') or '/'
        service = self.server.service  # type: ignore[attr-defined]
        body = None
        if method == 'POST':
            length = int(self.headers.get('Content-Length') or 0)
            raw = self.rfile.read(length) if length else b''
            try:
                body = json.loads(raw.decode('utf-8')) if raw else {}
            except ValueError:
                body = {}

        if method == 'GET' and path == '/health':
            data = service.health()
        elif method == 'POST' and path == '/chat':
            data = service.chat(body or {})
        elif method == 'POST' and path == '/api/create_task':
            data = service.create_task(body or {})
        elif method == 'GET' and path.startswith('/api/get_status/'):
            data = service.get_status(path.rsplit('/', 1)[-1])
        elif method == 'GET' and path.startswith('/api/get_final_result/'):
            data = service.get_final_result(path.rsplit('/', 1)[-1])
        elif method == 'GET' and path.startswith('/api/get_frame_results/'):
            data = service.get_frame_results(path.rsplit('/', 1)[-1])
        elif method == 'DELETE' and path.startswith('/api/delete_task/'):
            data = service.delete_task(path.rsplit('/', 1)[-1])
        elif method == 'GET' and path == '/__control':
            data = {'code': 0, 'data': {'hits': service._state.hits}}
        else:
            self._send({'code': 404, 'msg': f'not found: {method} {path}'}, 404)
            return
        self._send(data, 200)

    def _send(self, data: dict, status: int = 200):
        payload = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):  # noqa: A002
        # 静默请求日志（stdout 已由外层打印启动信息）
        pass


class MockDutServer:
    """ThreadingHTTPServer 包装：程序化 start/stop（in-process 测试 + 独立运行）。"""

    def __init__(self, host: str = '127.0.0.1', port: int = DEFAULT_PORT):
        self.service = MockDutService(MockDutState())
        self._httpd = ThreadingHTTPServer((host, port), MockDutRequestHandler)
        self._httpd.service = self.service  # type: ignore[attr-defined]
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return self._httpd.server_address[1]

    def start(self):
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread:
            self._thread.join(timeout=5)

    def serve_forever(self):
        self._httpd.serve_forever()


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description='被测 API DUT 替身（单轮协议 + voice_llm chat，INT-1176）')
    ap.add_argument('--host', default='0.0.0.0', help='绑定地址')
    ap.add_argument('--port', type=int, default=DEFAULT_PORT,
                    help=f'监听端口（默认 {DEFAULT_PORT}）')
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    server = MockDutServer(args.host, args.port)
    print(f'[mock_dut_api] listening on http://{args.host}:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.stop()


if __name__ == '__main__':
    main()
