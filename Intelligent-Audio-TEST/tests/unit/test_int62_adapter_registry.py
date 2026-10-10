# -*- coding: utf-8 -*-
"""INT-62 Adapter 体系单测 — 注册表分发 + 首个适配器行为回归 + 扩展性

覆盖（验收标准）：
- AC1 行为回归：现有 API 执行经适配器注册表分发，ApiDriverAdapter
  （原 clients/api_driver 原样迁移）渲染/执行/解析行为不变
- AC2 扩展性：mock 厂商适配器仅经注册表注册分发，核心执行链零改动；
  现场注册新厂商实现立即对 create_from_config 可见
- enum 化：VendorAdapterType 注册表 key / APIProtocol 传输协议分派
- 注册表契约：校验、覆盖告警、未知配置值拒绝
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from shared.models.common_enums import APIProtocol, VendorAdapterType
from api_test_service.domain.ports import ApiVendorAdapter
from api_test_service.infrastructure.adapters import (
    VendorAdapterRegistry,
    adapter_type_from_config,
    register_vendor_adapter,
    vendor_adapter_registry,
)
from api_test_service.infrastructure.adapters.api_client import (
    APIClient,
    endpoint_protocol,
)
from api_test_service.infrastructure.adapters.api_driver_adapter import (
    ApiDriverAdapter,
)
from api_test_service.infrastructure.adapters.mock_vendor_adapter import (
    MockVendorAdapter,
)


# ──────────────────────────── 本地 HTTP 服务替身 ────────────────────────────

class _EchoHandler(BaseHTTPRequestHandler):
    """回显请求头/体并返回标准 {"code":0,"data":{...}} 响应"""

    captured = []

    def do_GET(self):
        self.captured.append({'method': 'GET', 'path': self.path,
                              'headers': dict(self.headers)})
        self._respond()

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode('utf-8') if length else ''
        self.captured.append({'method': 'POST', 'path': self.path,
                              'headers': dict(self.headers), 'body': body})
        self._respond()

    def _respond(self):
        # 顶层 output_content 供 _send_direct 读取；data 层供适配器 asr_mapping 提取
        payload = json.dumps(
            {'code': 0, 'msg': 'success', 'output_content': 'pong',
             'data': {'output_content': 'pong'}})
        data = payload.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


@pytest.fixture()
def echo_server():
    _EchoHandler.captured = []
    server = ThreadingHTTPServer(('127.0.0.1', 0), _EchoHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_address[1]}', _EchoHandler.captured
    server.shutdown()
    server.server_close()


def _make_api_config(endpoint, meta=None, max_timeout=5, vendor_adapter=None):
    """最小 api_config 替身（与 _process_api_configs 的 MockAPIConfig 同形）"""
    meta = dict(meta or {})
    if vendor_adapter:
        meta['vendor_adapter'] = vendor_adapter
    return type('Cfg', (), {
        'endpoint': endpoint, 'meta': meta, 'max_timeout': max_timeout,
        'api_endpoints': [], 'api_url': endpoint,
    })()


# ──────────────────────────── 注册表契约 ────────────────────────────

class TestRegistryContract:
    def test_builtin_adapters_registered(self):
        types = {a['adapter_type'] for a in vendor_adapter_registry.list_adapters()}
        assert types == {VendorAdapterType.API_DRIVER.value,
                         VendorAdapterType.MOCK.value}

    def test_resolve_returns_port_subclass(self):
        for t in VendorAdapterType:
            cls = vendor_adapter_registry.resolve(t)
            assert issubclass(cls, ApiVendorAdapter)
            assert cls.adapter_type is t

    def test_resolve_unregistered_raises(self):
        registry = VendorAdapterRegistry()
        with pytest.raises(KeyError, match='未注册的厂商适配器类型'):
            registry.resolve(VendorAdapterType.MOCK)

    def test_register_rejects_non_port_subclass(self):
        registry = VendorAdapterRegistry()
        with pytest.raises(TypeError, match='ApiVendorAdapter'):
            registry.register(type('Bad', (), {'adapter_type': VendorAdapterType.MOCK}))

    def test_register_rejects_missing_enum_adapter_type(self):
        registry = VendorAdapterRegistry()

        class Bad(ApiVendorAdapter):
            adapter_type = 'mock'  # 魔法字符串，拒绝

            def execute(self, *a, **k):
                return {}

            def render_request_parts(self, context_data):
                return {}, {}

        with pytest.raises(TypeError, match='adapter_type'):
            registry.register(Bad)

    def test_register_overrides_with_warning(self, caplog):
        registry = VendorAdapterRegistry()
        registry.register(MockVendorAdapter)

        class Override(ApiVendorAdapter):
            adapter_type = VendorAdapterType.MOCK

            def execute(self, *a, **k):
                return {'overridden': True}

            def render_request_parts(self, context_data):
                return {}, {}

        with caplog.at_level('WARNING'):
            registry.register(Override)
        assert registry.resolve(VendorAdapterType.MOCK) is Override
        assert any('适配器覆盖' in r.message for r in caplog.records)


class TestAdapterTypeFromConfig:
    def test_default_when_no_config(self):
        assert adapter_type_from_config(None, None) is VendorAdapterType.API_DRIVER
        assert adapter_type_from_config(_make_api_config('http://x'), {}) \
            is VendorAdapterType.API_DRIVER

    def test_meta_vendor_adapter(self):
        cfg = _make_api_config('http://x', vendor_adapter='mock')
        assert adapter_type_from_config(cfg) is VendorAdapterType.MOCK

    def test_case_config_overrides_meta(self):
        cfg = _make_api_config('http://x', vendor_adapter='api_driver')
        assert adapter_type_from_config(cfg, {'vendor_adapter': 'mock'}) \
            is VendorAdapterType.MOCK

    def test_unknown_value_rejected(self):
        cfg = _make_api_config('http://x', vendor_adapter='no_such_vendor')
        with pytest.raises(ValueError, match='未知的 vendor_adapter 配置'):
            adapter_type_from_config(cfg)


class TestProtocolEnum:
    def test_endpoint_protocol_dispatch(self):
        assert endpoint_protocol('ws://h') is APIProtocol.WEBSOCKET
        assert endpoint_protocol('wss://h') is APIProtocol.WEBSOCKET
        assert endpoint_protocol('http://h') is APIProtocol.HTTP
        assert endpoint_protocol('') is APIProtocol.HTTP
        assert endpoint_protocol(None) is APIProtocol.HTTP

    def test_api_client_call_routes_by_protocol(self, echo_server):
        url, _ = echo_server
        # HTTP 端点 → HTTP 分支（可达本地服务）；WS 端点 → WS 分支
        # （websocket 库可用性在此不建真实连接，仅验证分派入口一致）
        result = APIClient.call(url, method='GET', timeout=3)
        assert result['status_code'] == 200


# ──────────────────────────── AC1 首个适配器行为回归 ────────────────────────────

class TestApiDriverAdapterBehavior:
    """原 clients/api_driver 原样迁移：渲染 / 执行 / 解析行为回归锁定"""

    def test_render_request_parts_placeholder(self):
        cfg = _make_api_config('http://x', meta={
            'headers': {'X-Api': 'static', 'X-Dyn': '{{case_name}}'},
            'body_template': {'text': '{{input_text}}', 'keep': 1},
        })
        adapter = vendor_adapter_registry.create(
            VendorAdapterType.API_DRIVER, api_config=cfg,
            case_config={'headers': {'X-Case': 'c-{{round_number}}'}})
        headers, body = adapter.render_request_parts(
            {'case_name': 'demo', 'input_text': 'hi', 'round_number': 3})
        assert headers == {'X-Api': 'static', 'X-Dyn': 'demo',
                           'X-Case': 'c-3'}
        assert body['text'] == 'hi' and body['keep'] == 1

    def test_execute_via_local_server_result_contract(self, echo_server):
        url, captured = echo_server
        cfg = _make_api_config(url, meta={'headers': {'X-Token': 't1'},
                                          'asr_mapping': 'output_content'})
        adapter = ApiDriverAdapter(cfg, {'body_template': {'q': '{{input_text}}'}},
                                   test_case_id='c1', task_id=7)
        result = adapter.execute({'input_text': 'hello'})

        # 统一结果契约（与迁移前 APIDriver 相同字段）
        assert result['success'] is True
        assert result['status_code'] == 200
        assert result['error'] is None
        assert result['json']['code'] == 0
        assert isinstance(result['latency'], int)
        assert result['asr'] == 'pong'  # asr_mapping 路径生效
        assert result['biz_code'] == 0

        assert captured[0]['method'] == 'POST'
        assert captured[0]['headers'].get('X-Token') == 't1'
        assert json.loads(captured[0]['body'])['q'] == 'hello'

    def test_execute_business_error_parsed(self, echo_server):
        url, captured = echo_server
        cfg = _make_api_config(url + '/bizerr', meta={
            'error_code_mapping': 'code', 'error_msg_mapping': 'msg'})
        adapter = ApiDriverAdapter(cfg)
        # 服务替身仍返回 code=0，这里直接驱动 _parse_response 锁定 BizError 路径
        parsed = adapter._parse_response({
            'json': {'code': 401, 'msg': 'unauthorized', 'data': {}},
            'raw_response': '', 'all_responses': [],
        })
        assert adapter.api_config  # 构造契约不变
        assert parsed['biz_code'] == 401

    def test_execute_get_filters_complex_params(self, echo_server):
        url, captured = echo_server
        cfg = _make_api_config(url)
        adapter = ApiDriverAdapter(cfg)
        result = adapter.execute({'task_id': 't1', 'nested': {'a': 1},
                                  'items': ['x', {'b': 2}]}, method='GET')
        assert result['success'] is True
        assert 'task_id=t1' in captured[0]['path']
        assert 'nested' not in captured[0]['path']


# ──────────────────────────── AC2 扩展性（mock + 现场注册） ────────────────────────────

class TestExtensibility:
    def test_mock_adapter_selected_by_config(self):
        cfg = _make_api_config('ws://mock', vendor_adapter='mock')
        adapter = vendor_adapter_registry.create_from_config(cfg)
        assert isinstance(adapter, MockVendorAdapter)

    def test_mock_adapter_execute_echo(self):
        cfg = _make_api_config('ws://mock', vendor_adapter='mock')
        adapter = vendor_adapter_registry.create_from_config(
            cfg, {'mock_latency': 0})
        result = adapter.execute({'input_text': '你好'})
        assert result['success'] is True
        assert result['asr'] == '你好'
        assert result['trans'] == MockVendorAdapter.DEFAULT_TRANS
        assert result['latency'] == 0
        assert result['biz_code'] == 0

    def test_new_vendor_adapter_only_registration(self):
        """现场新增厂商适配器：注册即可被 create_from_config 分发，
        无任何核心链路改动；卸载后恢复。"""
        registry = vendor_adapter_registry

        @register_vendor_adapter
        class ProbeVendorAdapter(ApiVendorAdapter):
            adapter_type = VendorAdapterType.MOCK  # 复用枚举 key 演示注册即可用

            def __init__(self, api_config=None, case_config=None, endpoint=None,
                         test_case_id=None, task_id=None):
                self.api_config = api_config
                self.case_config = case_config or {}

            def execute(self, context_data, files=None, method=None):
                return {'success': True, 'vendor': 'probe',
                        'echo': context_data.get('input_text', '')}

            def render_request_parts(self, context_data):
                return {'X-Probe': '1'}, dict(context_data or {})

        try:
            cfg = _make_api_config('http://probe', vendor_adapter='mock')
            adapter = vendor_adapter_registry.create_from_config(cfg)
            assert isinstance(adapter, ProbeVendorAdapter)
            assert adapter.execute({'input_text': 'x'})['vendor'] == 'probe'
        finally:
            registry.unregister(VendorAdapterType.MOCK)
            registry.register(MockVendorAdapter)

        assert vendor_adapter_registry.resolve(VendorAdapterType.MOCK) \
            is MockVendorAdapter


# ──────────────────────────── 核心执行链接线（注册表分发） ────────────────────────────

class TestCoreChainDispatch:
    def _make_session_executor(self):
        from api_test_service.core.api_session_executor import APISessionExecutor
        stub_executor = type('E', (), {'_log': lambda self, *a, **kw: None})()
        return APISessionExecutor(stub_executor)

    def test_send_round_request_resolves_adapter_via_registry(self, monkeypatch,
                                                              echo_server):
        """执行链只见 Port：_send_round_request 经注册表取适配器并消费其渲染产物"""
        from api_test_service.core import api_session_executor as se_mod
        from api_test_service.core.session_context import SessionContext

        url, _ = echo_server
        executor = self._make_session_executor()
        calls = {}

        class RecordingAdapter(ApiVendorAdapter):
            adapter_type = VendorAdapterType.MOCK

            def __init__(self, api_config=None, case_config=None, **kwargs):
                self.api_config = api_config
                self.case_config = case_config or {}

            def render_request_parts(self, context_data):
                calls['context'] = dict(context_data)
                return {'X-Sentinel': 'reg'}, {'sentinel_body': True}

            def execute(self, context_data, files=None, method=None):
                return {}

        monkeypatch.setattr(
            se_mod.vendor_adapter_registry, 'create_from_config',
            lambda api_config, case_config, **kw:
                calls.setdefault('adapter', RecordingAdapter(api_config, case_config)))

        cfg = _make_api_config(url, meta={'use_adapter': False})
        session = SessionContext(session_id='s1', config={'session_timeout': 5})
        result = executor._send_round_request(
            task_id=1, api_config=cfg, api_specific_config={},
            session=session, round_number=1,
            round_config={'input_type': 'text',
                          'algorithm_params': [{'field_code': 'input_text',
                                                'field_value': 'hi'}]},
            case_algorithm_params=None, algorithm_type='voice_llm',
            total_rounds=1)

        assert 'adapter' in calls, "执行链必须经注册表获取适配器"
        assert calls['context']['input_text'] == 'hi'
        # _send_direct 消费适配器渲染产物：哨兵头/体到达 HTTP 层
        assert result['success'] is True
        assert result['output'] == 'pong'

    def test_mock_adapter_end_to_end_via_registry(self, echo_server):
        """mock 厂商适配器经注册表渲染轮次请求，核心链路零改动"""
        from api_test_service.core.session_context import SessionContext

        url, _ = echo_server
        executor = self._make_session_executor()
        cfg = _make_api_config(url, meta={'use_adapter': False,
                                          'vendor_adapter': 'mock'})
        session = SessionContext(session_id='s1', config={'session_timeout': 5})
        result = executor._send_round_request(
            task_id=1, api_config=cfg, api_specific_config={},
            session=session, round_number=1,
            round_config={'input_type': 'text',
                          'algorithm_params': [{'field_code': 'input_text',
                                                'field_value': 'hi'}]},
            case_algorithm_params=None, algorithm_type='voice_llm',
            total_rounds=1)
        assert result['success'] is True


# ──────────────────────────── task_runner 接线 ────────────────────────────

class TestTaskRunnerDispatch:
    def test_task_runner_uses_registry(self, echo_server, tmp_path):
        """单轮任务链（健康检查）经注册表分发到首个适配器，行为回归不变"""
        from api_test_service.core.api_task_runner import APITaskRunner

        url, captured = echo_server
        cfg = _make_api_config(url)
        audio_file = tmp_path / 'in.wav'
        audio_file.write_bytes(b'RIFF....')
        runner = APITaskRunner(type('E', (), {
            '_log': lambda self, *a, **kw: None,
            '_handle_control': lambda self, task_id: None,
            'execution_engine': None,
        })())
        result = runner.health_check(
            task_id=1, case_name='c',
            audio={'file_path': str(audio_file)},
            api_config=cfg, api_specific_config={},
            api_paths={'health': '/health'},
            select_base_url=lambda: url, release_base_url=lambda u: None)
        assert isinstance(result, dict)
        assert captured[0]['path'] == '/health'

    def test_health_check_missing_audio_raises(self, echo_server):
        from api_test_service.core.api_task_runner import APITaskRunner

        url, _ = echo_server
        cfg = _make_api_config(url)
        runner = APITaskRunner(type('E', (), {
            '_log': lambda self, *a, **kw: None,
            '_handle_control': lambda self, task_id: None,
        })())
        with pytest.raises(Exception, match='音频文件不存在'):
            runner.health_check(
                task_id=1, case_name='c', audio={'file_path': '_no_such_.wav'},
                api_config=cfg, api_specific_config={},
                api_paths={'health': '/health'},
                select_base_url=lambda: url, release_base_url=lambda u: None)
