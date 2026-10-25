# -*- coding: utf-8 -*-
"""INT-1790（A2）E2E 取证：SSE mock 流 + 真实 StreamSessionExecutor + 真实算法服务。

在 api_test_service 容器内跑（同 compose 网络，算法服务走容器名），用于卡面
可测验收 1/2/3：

1. 推 3 个事件（含 1 个句子结束标记）→ 轮次 / 句子边界与配置一致，rounds[i].output 有值；
2. 评估入参有值（输出字段经真实 algorithm_service 的 field_mappings 提取 / 映射）；
3. 断线重连与空闲超时各触发一次，行为符合卡面约定且不挂死。

结果持久化链路（APIResultProcessor / ACL）用替身记录入参——该链路与 WS 会话
共用同一实现、本卡未改；本脚本只验证新代码产出的轮次与评估入参。
"""
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

sys.path.insert(0, os.environ.get('INT1790_CODE_ROOT', '/app'))

EVIDENCE = {}


# ─────────────── mock SSE 服务（容器内 127.0.0.1） ───────────────

class _Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.0'

    def do_GET(self):
        mode = self.server.mode
        self.server.req_log.append(
            (mode, self.headers.get('Last-Event-ID'), self.server.hits))
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        try:
            if mode == 'normal':
                for chunk in (
                        'data: {"asr_result": "你"}\n\n',
                        'data: {"asr_result": "好"}\n\n',
                        'data: {"asr_result": "世界", "is_sentence_end": true}\n\n',
                        'data: {"asr_result": "再见", "is_sentence_end": true,'
                        ' "session_finished": true}\n\n'):
                    self.wfile.write(chunk.encode())
                    self.wfile.flush()
                    time.sleep(0.02)
            elif mode == 'idle':
                self.wfile.write(b'data: {"asr_result": "a", "is_sentence_end": false}\n\n')
                self.wfile.flush()
                time.sleep(self.server.hold_seconds)
            elif mode == 'reconnect':
                n = self.server.hits
                self.server.hits += 1
                if n == 0:   # 首次连接：发一条后断流（挂住不发）
                    self.wfile.write(
                        b'id: 1\ndata: {"asr_result": "a", "is_sentence_end": false}\n\n')
                    self.wfile.flush()
                    time.sleep(self.server.hold_seconds)  # 断流：不再发送
                else:
                    self.server.last_event_id = self.headers.get('Last-Event-ID')
                    self.wfile.write(
                        b'id: 2\ndata: {"asr_result": "b", "is_sentence_end": true,'
                        b' "session_finished": true}\n\n')
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def log_message(self, *args):
        pass


def _serve(mode, hold_seconds=2.0):
    srv = ThreadingHTTPServer(('127.0.0.1', 0), _Handler)
    srv.daemon_threads = True
    srv.mode = mode
    srv.hold_seconds = hold_seconds
    srv.hits = 0
    srv.last_event_id = None
    srv.req_log = []
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f'http://127.0.0.1:{srv.server_address[1]}/stream'


# ─────────────── 执行器替身（只记录产出） ───────────────

class _Concurrency:
    def acquire(self, *args, **kwargs):
        return True

    def release(self, *args, **kwargs):
        pass


class _Engine:
    def _emit_progress(self, task_id, force=False):
        pass


class _ResultProcessor:
    def __init__(self):
        self.calls = []

    def create_multi_round_test_result(self, **kwargs):
        self.calls.append(kwargs)
        return 'probe-result-1'

    def update_task_case_failure(self, task_id, tc_rel_id, error_msg):
        self.calls.append({'failure': error_msg})


class _Executor:
    def __init__(self):
        self.logs = []
        self._concurrency = _Concurrency()
        self.execution_engine = _Engine()
        self._result_processor = _ResultProcessor()

    def _log(self, level='INFO', content='', **kwargs):
        self.logs.append(f'[{level}] {content}')

    def _handle_control(self, task_id):
        pass

    def _is_case_removed(self, task_id, test_case_id):
        return False


def _api_config(url, meta, max_timeout=5):
    return SimpleNamespace(
        id=5, endpoint=url, api_endpoints=[], default_max_process=1,
        meta=meta, max_timeout=max_timeout, vendor=None, protocol='sse',
        streaming=True, proxy_type=None, proxy_url=None)


def _run_case(mode, meta_extra=None, hold_seconds=2.0):
    from api_test_service.core import stream_session_executor as module

    srv, url = _serve(mode, hold_seconds=hold_seconds)
    meta = {
        'asr_mapping': 'asr_result',
        'trans_mapping': 'translation_result',
        'sentence_end_mapping': 'is_sentence_end',
        'session_end_mapping': 'session_finished',
        'append_mode': True,
        'sse': {'idle_timeout_ms': 300},
    }
    meta.update(meta_extra or {})
    executor_stub = _Executor()
    executor = module.StreamSessionExecutor(executor_stub)
    data = {
        'task_id': 1, 'test_case_id': 2, 'case_name': 'INT-1790-SSE-probe',
        'algorithm_type': 'int1790_probe', 'protocol': 'sse',
        'api_configs': [_api_config(url, meta)],
        'api_specific_config': {}, 'case_algorithm_params': {},
    }
    started = time.time()
    executor.execute(1, 100, data, {'rounds': [], 'reference_params': {}})
    elapsed = round(time.time() - started, 3)
    srv.shutdown()
    srv.server_close()
    call = executor_stub._result_processor.calls[0]
    return {
        'mode': mode,
        'elapsed_seconds': elapsed,
        'result_success': call.get('success'),
        'error': call.get('aggregated', {}).get('error'),
        'round_count': call.get('aggregated', {}).get('round_count'),
        'rounds': [
            {k: r.get(k) for k in ('round_number', 'success', 'event_count',
                                   'answer_text', 'sentence_end', 'session_end',
                                   'output')}
            for r in call.get('aggregated', {}).get('algorithm_result', {}).get('rounds', [])
        ],
        'session_summary': call.get('aggregated', {}).get('session_summary'),
        'last_event_id': getattr(srv, 'last_event_id', None),
        'server_requests': list(getattr(srv, 'req_log', [])),
        'logs': executor_stub.logs[-6:],
    }


def main():
    from shared.utils.dto_utils import dto_to_dict
    from api_test_service.core.eval_output_collector import _algo_acl
    from api_test_service.core import stream_session_executor as module

    # 评估入队：记录入参，不向真实 evaluation_service 投递探针结果
    evaluations = []
    module.submit_case_evaluation = lambda **kw: evaluations.append(kw)
    EVIDENCE['_evaluations'] = evaluations

    # 真实算法服务：输出声明 / 字段映射（评估入参的来源）
    mappings = dto_to_dict(_algo_acl.get_field_mappings('int1790_probe')) or {}
    api_defs = ((mappings.get('original') or {}).get('api') or {}).get('output') or {}
    eval_defs = ((mappings.get('original') or {}).get('evaluation') or {}).get('output') or {}
    EVIDENCE['algorithm_service_field_mappings'] = {
        'algorithm_type': 'int1790_probe', 'protocol': 'sse',
        'api_output_codes': sorted(api_defs.keys()) if isinstance(api_defs, dict) else [],
        'eval_output_targets': sorted(eval_defs.keys()) if isinstance(eval_defs, dict) else [],
    }

    EVIDENCE['normal_stream'] = _run_case('normal')
    EVIDENCE['idle_timeout'] = _run_case('idle', hold_seconds=2.0)
    EVIDENCE['reconnect'] = _run_case(
        'reconnect', hold_seconds=2.0,
        meta_extra={'sse': {'idle_timeout_ms': 300, 'reconnect_enabled': True,
                            'retry_ms': 10, 'max_reconnect_attempts': 2}})

    print(json.dumps(EVIDENCE, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
