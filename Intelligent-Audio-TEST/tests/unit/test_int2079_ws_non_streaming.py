# -*- coding: utf-8 -*-
"""INT-2079 / A4 单测：WS 非实时执行器落地（websocket + streaming=false 请求-响应式）

覆盖（卡面验收）：
- 可用矩阵放开：(websocket, false) 可写（CRUD create/update 不再 400）；
- ExecutionLane 路由：lane_of(False)=NON_STREAMING + protocol=websocket →
  非流式道会话执行器（APISessionExecutor，无 DUT 任务协议，一轮 = 一次请求-响应）；
- WebSocketAdapter 请求-响应语义：发请求消息 → 等响应（连接 → 发 → 收 → 断开）；
- 建任务执行全链：executor → 注册表分发 → WebSocketAdapter → mock WS 请求-响应
  服务 → 采字段 → 聚合 → 评估提交；
- 失败收敛：超时 / 服务端提前断开 / 协议错误帧。
"""
import os
from types import SimpleNamespace

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.models.common_enums import (
    AVAILABLE_PROTOCOL_STREAMING,
    ExecutionLane,
    is_protocol_streaming_available,
)
from mock_services.mock_ws_request_response_api import (
    MockWsRequestResponseBehavior,
    MockWsRequestResponseServer,
)


# ──────────────────────────── mock WS 请求-响应服务 ────────────────────────────

@pytest.fixture
def ws_rr_server():
    server = MockWsRequestResponseServer(
        MockWsRequestResponseBehavior(answer_text='mock 请求-响应回复文本'), port=0)
    server.start()
    yield server
    server.stop()


@pytest.fixture
def ws_rr_server_keepalive():
    """响应后保持连接（不关闭），由客户端静默超时收敛。"""
    server = MockWsRequestResponseServer(
        MockWsRequestResponseBehavior(answer_text='keepalive 回复',
                                      close_after_response=False), port=0)
    server.start()
    yield server
    server.stop()


def _api_cfg(url, meta=None, **extra):
    meta = dict(meta or {})
    return SimpleNamespace(
        id=7, endpoint=url,
        api_endpoints=[{'endpoint': url}],
        default_max_process=2, meta=meta, max_timeout=5,
        vendor='mock', protocol='websocket', streaming=False,
        proxy_type=None, proxy_url=None,
        **extra)


# ──────────────────────────── 可用矩阵 / 写侧 ────────────────────────────

class TestAvailabilityAndCrud:
    def test_websocket_false_available(self):
        assert ('websocket', False) in AVAILABLE_PROTOCOL_STREAMING
        assert is_protocol_streaming_available('websocket', False)

    def test_websocket_true_unchanged(self):
        assert is_protocol_streaming_available('websocket', True)

    def test_create_websocket_false_succeeds(self, monkeypatch):
        from api_test_service.application import api_crud_service as mod
        captured = {}

        def _fake_create(data):
            captured.update(data)
            return SimpleNamespace(id=11)

        monkeypatch.setattr(mod.api_test_repository, 'create_api', _fake_create)
        monkeypatch.setattr(mod, 'refresh_stats_cache', lambda: None)
        monkeypatch.setattr(mod.APICrudService, '_publish_config_changed',
                            staticmethod(lambda *a, **k: None))

        result = mod.APICrudService.create({
            'name': 'ws-rr-demo', 'meta': {},
            'protocol': 'websocket', 'streaming': False})
        assert result['success'] is True and result['code'] == 201
        assert captured['protocol'] == 'websocket'
        assert captured['streaming'] is False

    def test_update_http_false_to_websocket_false_allowed(self, monkeypatch):
        from api_test_service.application import api_crud_service as mod
        api = SimpleNamespace(id=1, protocol='http', streaming=False,
                              proxy_type=None, proxy_url=None,
                              default_max_process=5, default_max_timeout=30,
                              default_max_audio_duration=60, api_endpoints=[])
        monkeypatch.setattr(mod.api_test_repository, 'get_api', lambda _id: api)
        result = mod.APICrudService.update(1, {
            'protocol': 'websocket', 'streaming': False})
        # 合并后组合 (websocket, false) 已上线 → 校验通过（后续字段写入仍走仓储）
        assert '实现未上线' not in result['message']
        assert result['code'] in (200, 400)  # 400 只能来自别的校验，不能是组合未上线


# ──────────────────────────── 执行道路由 ────────────────────────────

class _EngineStub:
    stop_flags = {}
    pause_flags = {}
    api_entry_lock = __import__('threading').Lock()
    api_entry_status = {}
    round_progress_cache = {}

    def _emit_progress(self, task_id, force=False):
        pass


class TestRouting:
    def _executor(self):
        from api_test_service.core.api_executor import APIExecutor
        executor = APIExecutor(_EngineStub())
        return executor

    def test_websocket_false_routes_to_non_streaming_lane(self):
        """streaming=false + protocol=websocket → 非流式道会话执行器（一轮=一次往返）"""
        executor = self._executor()
        calls = {'session': 0, 'realtime': 0}
        executor._session_executor.execute = \
            lambda *a, **k: calls.__setitem__('session', calls['session'] + 1)
        executor._realtime_executor.execute = \
            lambda *a, **k: calls.__setitem__('realtime', calls['realtime'] + 1)

        data = {'test_case_id': 1, 'case_name': 'ws-rr-case',
                'streaming': False, 'protocol': 'websocket',
                'api_configs': [_api_cfg('ws://vendor/ws')], 'audio': {},
                'api_specific_config': {}, 'total_audio_duration': 1.0,
                'case_algorithm_params': {}, 'algorithm_type': 'translation'}
        executor._load_case_config = lambda tc_id: {'rounds': [{'round_number': 1}]}
        executor._execute_single_or_multi(task_id=100, tc_rel_id=1, data=data)
        assert calls == {'session': 1, 'realtime': 0}

    def test_websocket_false_single_round_also_session(self):
        """streaming=false + websocket 单轮也走会话执行器（无 DUT 任务协议）"""
        executor = self._executor()
        calls = {'session': 0}
        executor._session_executor.execute = \
            lambda *a, **k: calls.__setitem__('session', calls['session'] + 1)

        data = {'test_case_id': 1, 'case_name': 'ws-rr-single',
                'streaming': False, 'protocol': 'websocket',
                'api_configs': [_api_cfg('ws://vendor/ws')], 'audio': {},
                'api_specific_config': {}, 'total_audio_duration': 1.0,
                'case_algorithm_params': {}, 'algorithm_type': 'translation'}
        executor._load_case_config = lambda tc_id: {'rounds': []}
        executor._execute_single_or_multi(task_id=100, tc_rel_id=1, data=data)
        assert calls == {'session': 1}

    def test_websocket_false_empty_rounds_runs_one_round(self):
        """websocket+false 空 rounds → 按 1 轮执行（对齐 gRPC unary 口径）"""
        from api_test_service.core.api_executor import APIExecutor
        executor = object.__new__(APIExecutor)
        logs = []
        executor._log = lambda level='INFO', content='', **kw: logs.append((level, content))
        executor._load_case_config = lambda test_case_id: {}
        captured = {}

        class _Route:
            def execute(self, task_id, tc_rel_id, data, case_config):
                captured['rounds'] = case_config.get('rounds')
                return True

        executor.route_executor = lambda lane: _Route()

        data = {'test_case_id': 1, 'case_name': 'ws-rr-empty',
                'algorithm_type': 'translation', 'streaming': False,
                'protocol': 'websocket', 'api_configs': [], 'api_specific_config': {},
                'audio': {}, 'total_audio_duration': 0}
        assert executor._execute_single_or_multi(1, 2, data) is True
        assert captured['rounds'] == [{}]
        assert any(level == 'WARNING' and 'rounds 为空' in content
                   for level, content in logs)


# ──────────────────────────── 注册表分发 ────────────────────────────

class TestRegistryResolution:
    def test_create_from_config_resolves_websocket_adapter(self):
        from api_test_service.infrastructure.adapters import vendor_adapter_registry
        from api_test_service.infrastructure.adapters.websocket_adapter import (
            WebSocketAdapter,
        )
        adapter = vendor_adapter_registry.create_from_config(
            _api_cfg('ws://vendor/ws', meta={}))
        assert isinstance(adapter, WebSocketAdapter)


# ──────────────────────────── WebSocketAdapter 请求-响应 ────────────────────────────

class TestWebSocketAdapter:
    def _adapter(self, url, meta=None, body_template=None):
        from api_test_service.infrastructure.adapters.websocket_adapter import (
            WebSocketAdapter,
        )
        cfg = _api_cfg(url, meta=meta or {})
        return WebSocketAdapter(
            cfg, case_config={'body_template': body_template or {
                'input_text': '{{input_text}}',
                'round_number': '{{round_number}}',
            }}, test_case_id='c1', task_id=7)

    def test_request_response_round_trip(self, ws_rr_server):
        """发请求消息 → 等响应：一轮一次往返，output 取到 mock 回复文本"""
        adapter = self._adapter(ws_rr_server.url)
        result = adapter.execute_voice_llm_chat(
            session_id='s1', input_type='text', input_data='你好',
            round_number=1, total_rounds=1, task_type='translation', timeout=5)
        assert result['success'] is True
        assert result['output'] == 'mock 请求-响应回复文本'
        assert result['asr'] == 'mock 请求-响应回复文本'
        assert result['raw_response']['code'] == 0
        # 服务端确实收到渲染后的请求体
        reqs = ws_rr_server.service.state.snapshot()['received_requests']
        assert reqs == [{'input_text': '你好', 'round_number': '1'}]

    def test_execute_port_round_trip(self, ws_rr_server):
        """Port execute（非 voice_llm 载荷）同样走请求-响应"""
        adapter = self._adapter(ws_rr_server.url, body_template={'q': '{{input_text}}'})
        result = adapter.execute({'input_text': 'ping'})
        assert result['success'] is True
        assert result['output'] == 'mock 请求-响应回复文本'
        reqs = ws_rr_server.service.state.snapshot()['received_requests']
        assert reqs == [{'q': 'ping'}]

    def test_session_end_mapping_early_convergence(self, ws_rr_server):
        """响应携带 session_end=true → 客户端提前收敛（不再空等）"""
        ws_rr_server.set_behavior({'session_end': True, 'close_after_response': False})
        adapter = self._adapter(ws_rr_server.url)
        result = adapter.execute_voice_llm_chat(
            session_id='s1', input_type='text', input_data='hi',
            round_number=1, total_rounds=1, task_type='translation', timeout=5)
        assert result['success'] is True

    def test_keepalive_quiet_timeout(self, ws_rr_server_keepalive):
        """服务端响应后保持连接：首响应后静默超时收敛（不无限等待）"""
        adapter = self._adapter(
            ws_rr_server_keepalive.url, meta={'recv_timeout': 0.3})
        result = adapter.execute_voice_llm_chat(
            session_id='s1', input_type='text', input_data='hi',
            round_number=1, total_rounds=1, task_type='translation', timeout=5)
        assert result['success'] is True
        assert result['output'] == 'keepalive 回复'

    def test_disconnect_before_response_fails(self, ws_rr_server):
        """服务端收到请求即断开（不响应）→ 用例失败并写明原因"""
        ws_rr_server.set_behavior({'disconnect_before_response': True})
        adapter = self._adapter(ws_rr_server.url)
        result = adapter.execute_voice_llm_chat(
            session_id='s1', input_type='text', input_data='hi',
            round_number=1, total_rounds=1, task_type='translation', timeout=5)
        assert result['success'] is False
        assert result['error']

    def test_protocol_error_frame(self, ws_rr_server):
        """协议错误帧 → 按 error 载荷归一，success=False"""
        ws_rr_server.set_behavior({'protocol_error': True})
        adapter = self._adapter(ws_rr_server.url)
        result = adapter.execute_voice_llm_chat(
            session_id='s1', input_type='text', input_data='hi',
            round_number=1, total_rounds=1, task_type='translation', timeout=5)
        assert result['success'] is False
        assert 'mock_protocol_error' in str(result['raw_response'])

    def test_render_request_parts_placeholders(self):
        adapter = self._adapter(
            'ws://vendor/ws', meta={'ws_headers': {'X-Flag': '{{round_number}}'}},
            body_template={'text': '{{input_text}}'})
        headers, body = adapter.render_request_parts(
            {'input_text': 'hi', 'round_number': '3'})
        assert headers['X-Flag'] == '3'
        assert body == {'text': 'hi'}


# ──────────────────────────── 会话执行器全链（发请求→等响应→采字段→聚合→评估） ────────────────────────────

class _EngineStub:
    stop_flags = {}
    pause_flags = {}
    api_entry_lock = __import__('threading').Lock()
    api_entry_status = {}
    round_progress_cache = {}

    def _emit_progress(self, task_id, force=False):
        pass

    def notify_case_completed(self, task_id):
        pass

    def update_case_round_progress(self, task_id, tc_rel_id, current, total):
        pass


class _ResultProcessor:
    """捕获 create_multi_round_test_result（评估入参 = aggregated.algorithm_result）"""

    def __init__(self):
        self.calls = []

    def create_multi_round_test_result(self, task_id, test_case_id, api_config_id,
                                       algorithm_type, aggregated, success):
        self.calls.append({'task_id': task_id, 'test_case_id': test_case_id,
                           'api_config_id': api_config_id, 'success': success,
                           'algorithm_result': aggregated.get('algorithm_result', {})})
        return 207901

    def update_task_case_failure(self, *a, **k):
        pass


class _ExecutorStub:
    def __init__(self):
        self.execution_engine = _EngineStub()
        self._concurrency = SimpleNamespace(
            acquire=lambda *a, **k: True, release=lambda *a, **k: None)
        self._result_processor = _ResultProcessor()

    def _handle_control(self, task_id):
        pass

    def _log(self, *a, **k):
        pass


class TestSessionExecutorFullChain:
    def test_ws_request_response_full_chain(self, ws_rr_server, monkeypatch):
        """WS 非实时全链：executor → 注册表 → WebSocketAdapter → mock WS →
        响应解析 → 轮次结果 → 聚合 → 评估提交（发请求 → 等响应 → 采字段）"""
        import api_test_service.core.api_session_executor as se_mod
        from api_test_service.core.api_session_executor import APISessionExecutor
        from api_test_service.core.session_context import SessionContext

        executor = APISessionExecutor(_ExecutorStub())
        # 评估 ACL 桩：捕获提交入参
        eval_calls = []
        monkeypatch.setattr(
            se_mod, '_evaluation_acl',
            SimpleNamespace(submit_evaluate_case=lambda **k: eval_calls.append(k)))
        # 算法参数提取桩
        monkeypatch.setattr(
            se_mod, '_algo_acl',
            SimpleNamespace(extract_case_all_params=lambda params: SimpleNamespace()))
        monkeypatch.setattr(
            se_mod, 'dto_to_dict', lambda dto: {'evaluation': {'threshold': 0.8}})

        cfg = _api_cfg(ws_rr_server.url, meta={'use_adapter': True})
        session = SessionContext(session_id='s-int2079', config={'session_timeout': 5})
        round_config = {'round_number': 1, 'input_type': 'text',
                        'algorithm_params': [{'field_code': 'input_text',
                                              'field_value': '你好'}]}
        result = executor._send_round_request(
            task_id=1, api_config=cfg, api_specific_config={}, session=session,
            round_number=1, round_config=round_config,
            case_algorithm_params={}, algorithm_type='translation',
            total_rounds=1)
        assert result['success'] is True
        # INT-1746：轮次文本输出落 answer_text；output 为映射后的 dict（零声明按 meta 兜底）
        assert result['answer_text'] == 'mock 请求-响应回复文本'
        assert result['output'].get('output') == 'mock 请求-响应回复文本'
        assert result['round_number'] == 1

        # 聚合 → 落库（result_processor 捕获 algorithm_result）→ 评估提交
        aggregated = executor._aggregate_round_results([result], session, api_config=cfg)
        rp = executor._executor._result_processor
        result_id = rp.create_multi_round_test_result(
            task_id=1, test_case_id=9, api_config_id=cfg.id,
            algorithm_type='translation', aggregated=aggregated, success=True)
        assert result_id == 207901
        assert rp.calls[0]['algorithm_result']['success_count'] == 1

        executor._submit_evaluation(
            1, result_id, 9, 'case', {'reference_params': {}}, {},
            'translation', aggregated, cfg.id, device_type='websocket_api')
        assert len(eval_calls) == 1
        assert eval_calls[0]['result_id'] == result_id
        assert eval_calls[0]['eval_params']['device_type'] == 'websocket_api'
        assert eval_calls[0]['algorithm_result']['text_output'] == 'mock 请求-响应回复文本'
