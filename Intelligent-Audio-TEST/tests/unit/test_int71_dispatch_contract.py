# -*- coding: utf-8 -*-
"""INT-71：执行分发 gRPC 契约与 API 链路正确性

锁定四项修复：
1. device_type/device_id 进出站契约贯通：task_service 经 ACL 仓储
   StartAPITest 下发（含精确 case_ids）→ servicer 解析 → 命令 →
   start_task → executor 按 device_type 路由
2. core 层无 stub 直调（ACL 红线）：case_execution 经 ACL 仓储出站
3. input_type=audio 时被测 API 收到真实音频：执行侧携带混音产物引用，
   adapter 侧经统一存储层解析为真实字节，缺失即轮次失败不静默空发送
"""
import json
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import inspect
import tempfile
from types import SimpleNamespace

import pytest

from shared.proto import api_test_service_pb2 as api_pb


# ==================== 1. ACL 出站契约（task_service → StartAPITest） ====================

class TestAclStartApiTestContract:
    """ApiTestAclRepository.start_api_test 出站请求必须携带完整路由契约。"""

    def _patch_stub(self, monkeypatch, capture):
        def _start(req, *a, **k):
            capture['req'] = req
            return SimpleNamespace(success=True, message='ok',
                                   data=json.dumps({'success': True}))
        stub = SimpleNamespace(StartAPITest=_start)
        import shared.clients.grpc_clients as grpc_clients
        monkeypatch.setattr(grpc_clients, 'get_api_test_service_stub',
                            lambda: stub)
        return stub

    def test_request_carries_routing_contract(self, monkeypatch):
        from task_service.infrastructure.acl.report_acl_repository import (
            api_test_acl_repository,
        )
        capture = {}
        self._patch_stub(monkeypatch, capture)

        api_test_acl_repository.start_api_test(
            task_id=31, case_ids=[401],
            device_type='websocket_api', device_id='7')

        req = capture['req']
        assert isinstance(req, api_pb.StartAPITestRequest)
        assert req.task_id == '31'
        assert req.device_type == 'websocket_api'
        assert req.device_id == '7'
        assert list(req.case_ids) == [401]

    def test_instance_target_uses_direct_stub(self, monkeypatch):
        """会话亲和场景经 dispatch_target 直连绑定实例。"""
        from task_service.infrastructure.acl.report_acl_repository import (
            api_test_acl_repository,
        )
        capture = {}

        def _start(req, *a, **k):
            capture['req'] = req
            return SimpleNamespace(success=True, message='ok', data='')
        direct_stub = SimpleNamespace(StartAPITest=_start)

        import shared.clients.grpc_instance_client as instance_client
        monkeypatch.setattr(
            instance_client, 'get_api_test_service_stub_for_instance',
            lambda host, grpc_port: direct_stub)

        api_test_acl_repository.start_api_test(
            task_id=31, case_ids=[401],
            device_type='websocket_api', device_id='7',
            dispatch_target={'host': 'inst-b.host', 'grpc_port': 50071})

        assert capture['req'].device_type == 'websocket_api'

    def test_failure_response_raises(self, monkeypatch):
        from task_service.infrastructure.acl.report_acl_repository import (
            api_test_acl_repository,
        )
        import shared.clients.grpc_clients as grpc_clients
        monkeypatch.setattr(grpc_clients, 'get_api_test_service_stub', lambda: (
            SimpleNamespace(StartAPITest=lambda req: SimpleNamespace(
                success=False, message='任务已在运行中', data=''))))

        with pytest.raises(RuntimeError, match='任务已在运行中'):
            api_test_acl_repository.start_api_test(
                task_id=31, case_ids=[401], device_type='http_api')


# ==================== 2. ACL 红线（core 层无 stub 直调） ====================

class TestCoreNoDirectStub:
    """case_execution（core 层）不得直触 gRPC stub / pb2（ACL 红线）。"""

    def test_case_execution_module_has_no_grpc_imports(self):
        import task_service.core.execution_engine.mixins.case_execution as mod
        src = inspect.getsource(mod)
        assert 'api_test_service_pb2' not in src, \
            'core 层禁止直连 pb2（须经 ACL 仓储出站）'
        assert 'grpc_clients' not in src and 'grpc_instance_client' not in src, \
            'core 层禁止直取 gRPC stub（须经 ACL 仓储出站）'

    def test_execute_api_case_routes_via_acl(self, monkeypatch):
        """_execute_api_case 经 ACL start_api_test 分发并透传路由决策。"""
        import task_service.core.execution_engine.mixins.case_execution as mod

        calls = {}

        def _fake_start(task_id, case_ids, device_type='', device_id='',
                        dispatch_target=None):
            calls.update(task_id=task_id, case_ids=list(case_ids),
                         device_type=device_type, device_id=device_id,
                         dispatch_target=dispatch_target)
            return {'success': True}

        monkeypatch.setattr(mod.api_test_acl_repository, 'start_api_test',
                            _fake_start)
        monkeypatch.setattr(mod, 'create_db_session',
                            lambda: SimpleNamespace(
                                get=lambda *a: None, close=lambda: None))

        eng = SimpleNamespace(utc_plus_8=None, _log=lambda **k: None)
        ok = mod.CaseExecutionMixin._execute_api_case(
            eng, 'task-1', 401,
            dispatch_target={'host': 'h', 'grpc_port': 1},
            device_type='websocket_api', device_id='7')

        assert ok is True
        assert calls == {'task_id': 'task-1', 'case_ids': [401],
                         'device_type': 'websocket_api', 'device_id': '7',
                         'dispatch_target': {'host': 'h', 'grpc_port': 1}}


# ==================== 3. servicer 入站解析 → 命令 → start_task ====================

class TestStartAPITestInbound:
    """StartAPITest servicer 解析 case_ids/device_type/device_id 并贯通到应用层。"""

    def test_servicer_parses_full_contract(self, monkeypatch):
        from api_test_service.interfaces.grpc.servicers import APITestServiceServicer
        from api_test_service.application.commands.api_test_commands import (
            StartAPITestCommand,
        )
        from api_test_service.application import handlers as handlers_pkg

        captured = {}

        def _fake_handle(command):
            captured['command'] = command
            return {'success': True, 'message': 'ok'}

        monkeypatch.setattr(handlers_pkg.start_api_test_handler, 'handle',
                            _fake_handle)

        req = api_pb.StartAPITestRequest(
            task_id='31', device_type='websocket_api', device_id='7',
            case_ids=[401])
        resp = APITestServiceServicer().StartAPITest(req, context=None)

        assert resp.success is True
        cmd = captured['command']
        assert isinstance(cmd, StartAPITestCommand)
        assert cmd.task_id == '31'
        assert cmd.device_type == 'websocket_api'
        assert cmd.device_id == '7'
        assert list(cmd.case_ids) == [401]

    def test_handler_delegates_to_start_task(self, monkeypatch):
        from api_test_service.application.handlers.command_handlers import (
            StartAPITestCommand, start_api_test_handler,
        )
        from api_test_service.core import api_test_service as core_svc

        captured = {}

        def _fake_start_task(task_id, case_ids, api_ids,
                             device_type='', device_id=''):
            captured.update(task_id=task_id, case_ids=list(case_ids),
                            device_type=device_type, device_id=device_id)
            return {'success': True}

        monkeypatch.setattr(core_svc.api_test_service, 'start_task',
                            _fake_start_task)
        start_api_test_handler.handle(StartAPITestCommand(
            task_id=31, case_ids=[401],
            device_type='websocket_api', device_id='7'))

        assert captured == {'task_id': 31, 'case_ids': [401],
                            'device_type': 'websocket_api', 'device_id': '7'}


# ==================== 4. start_task → executor 路由贯通 ====================

class TestStartTaskRoutesByDeviceType:
    """start_task 携带的 device_type/device_id 透传到 executor（按设备类型路由）。"""

    def test_device_routing_reaches_executor(self, monkeypatch):
        from api_test_service.core.api_test_service import api_test_service
        api_test_service.init_app()
        api_test_service._running_tasks.clear()

        monkeypatch.setattr(api_test_service, '_affinity_forward_start',
                            lambda *a, **k: None)

        captured = {}

        def _fake_execute(task_id, tc_rel_id, device_type=None, device_id=None):
            captured.update(task_id=task_id, tc_rel_id=tc_rel_id,
                            device_type=device_type, device_id=device_id)
            return True

        monkeypatch.setattr(api_test_service.api_executor, 'execute_api_case',
                            _fake_execute)

        result = api_test_service.start_task(
            31, [401], [], device_type='websocket_api', device_id='9')
        assert result['success'] is True

        for _ in range(200):
            if 31 not in api_test_service._running_tasks:
                break
            import time
            time.sleep(0.02)

        assert captured == {'task_id': 31, 'tc_rel_id': 401,
                            'device_type': 'websocket_api', 'device_id': '9'}

    def test_override_wins_over_row_value(self, monkeypatch):
        """调度侧路由决策优先于 TaskCase 行值（行值兜底兼容旧调用）。"""
        from api_test_service.core import api_executor as executor_mod

        tc_row = {'id': 401, 'test_case_id': 'c-1', 'task_id': 31,
                  'execution_status': 'queued', 'device_type': 'http_api',
                  'device_id': '5'}

        class _FakeTaskDataAcl:
            def get_task_case_by_ids(self, task_id, case_ids=None):
                return [SimpleNamespace(result_data=dict(tc_row))]

            def update_task_case_status(self, **k):
                return True

            def get_task_by_id(self, task_id):
                return SimpleNamespace(result_data={'id': 31, 'type': 'api'})

        class _FakeTestcaseAcl:
            def get_test_case_detail(self, case_id):
                return SimpleNamespace(result_data={
                    'id': 'c-1', 'name': 'case', 'config': {}})

        class _FakeApiConfig:
            id = 1
            api_url = 'http://api'
            api_endpoints = []
            default_max_process = 1
            meta = {}
            max_timeout = 30
            vendor = None

        monkeypatch.setattr(executor_mod, '_task_data_acl', _FakeTaskDataAcl())
        monkeypatch.setattr(executor_mod, '_testcase_acl', _FakeTestcaseAcl())
        monkeypatch.setattr(executor_mod, 'dto_to_dict',
                            lambda d: getattr(d, 'result_data', d))

        executor = executor_mod.APIExecutor.__new__(executor_mod.APIExecutor)
        executor._thread_ctx = SimpleNamespace(current_test_case_id=None)
        monkeypatch.setattr(executor, '_log', lambda *a, **k: None)
        monkeypatch.setattr(executor, '_handle_control', lambda task_id: None)
        monkeypatch.setattr(executor, '_get_api_configs',
                            lambda task_id: [_FakeApiConfig()])
        monkeypatch.setattr(executor, '_get_audio_data',
                            lambda *a, **k: (b'', 0, ''))

        # 调度侧决策优先于行值
        ok, data = executor._validate_and_get_data(
            31, 401, device_type='websocket_api', device_id='9')
        assert ok is True
        assert data['device_type'] == 'websocket_api'
        assert data['device_id'] == '9'

        # 无决策时回退行值
        ok2, data2 = executor._validate_and_get_data(31, 401)
        assert ok2 is True
        assert data2['device_type'] == 'http_api'
        assert data2['device_id'] == '5'


# ==================== 5. 音频链路（input_type=audio 真实送达） ====================

class TestAudioInputWiring:
    """非实时路径音频不再空发送：执行侧携带混音产物引用，adapter 读真实字节。"""

    def test_send_via_adapter_carries_audio_path(self, monkeypatch):
        import api_test_service.core.api_session_executor as executor_mod

        captured = {}

        class _FakeRoundDto:
            pass

        def _fake_send_round(req):
            captured['req'] = req
            return _FakeRoundDto()

        monkeypatch.setattr(executor_mod._adapter_acl, 'send_round',
                            _fake_send_round)
        monkeypatch.setattr(executor_mod, 'dto_to_dict', lambda dto: {})

        ex = executor_mod.APISessionExecutor.__new__(
            executor_mod.APISessionExecutor)
        ex._executor = SimpleNamespace(_log=lambda *a, **k: None)

        session = SimpleNamespace(
            session_id='s-1', session_timeout=10,
            get_context=lambda: [], get_context_for_request=lambda: [])
        api_config = SimpleNamespace(id=1, meta={}, api_endpoints=[],
                                     api_url='http://api')
        result = ex._send_via_adapter(
            task_id=31, algorithm_type='voice_llm', session=session,
            round_number=1, total_rounds=1,
            rendered_headers={}, rendered_body={},
            api_specific_config={}, meta={},
            api_config=api_config, timeout=20,
            input_text='', input_type='audio', start_time=0.0,
            input_audio_path='local://audios/31/1/rendered/round_1.wav')

        assert result['success'] is True
        assert captured['req'].input_data == \
            'local://audios/31/1/rendered/round_1.wav'
        assert captured['req'].input_type == 'audio'

    def test_send_via_adapter_fails_loud_without_audio(self, monkeypatch):
        """音频轮次缺混音产物 → 轮次失败，拒绝静默空发送。"""
        import api_test_service.core.api_session_executor as executor_mod

        ex = executor_mod.APISessionExecutor.__new__(
            executor_mod.APISessionExecutor)
        ex._executor = SimpleNamespace(_log=lambda *a, **k: None)
        session = SimpleNamespace(
            session_id='s-1', session_timeout=10,
            get_context=lambda: [], get_context_for_request=lambda: [])

        with pytest.raises(ValueError, match='拒绝空音频发送'):
            ex._send_via_adapter(
                task_id=31, algorithm_type='voice_llm', session=session,
                round_number=1, total_rounds=1,
                rendered_headers={}, rendered_body={},
                api_specific_config={}, meta={},
                api_config=SimpleNamespace(id=1, meta={}),
                timeout=20, input_text='', input_type='audio',
                start_time=0.0, input_audio_path='')

    def test_round_request_wires_context_audio(self, monkeypatch):
        """_send_round_request 把轮次混音产物路径传给 adapter 发送。"""
        import api_test_service.core.api_session_executor as executor_mod

        ex = executor_mod.APISessionExecutor.__new__(
            executor_mod.APISessionExecutor)
        ex._executor = SimpleNamespace(_log=lambda *a, **k: None)

        monkeypatch.setattr(
            ex, '_build_round_context', lambda **k: {
                'input_text': '', 'input_audio': 'local://audios/mix.wav'})
        monkeypatch.setattr(
            executor_mod.vendor_adapter_registry, 'create_from_config',
            lambda *a, **k: SimpleNamespace(
                render_request_parts=lambda ctx: ({}, {})))

        captured = {}

        def _fake_send_via_adapter(self_, *a, **k):
            captured['input_audio_path'] = k.get('input_audio_path')
            return {'success': True}

        monkeypatch.setattr(executor_mod.APISessionExecutor,
                            '_send_via_adapter', _fake_send_via_adapter)

        ex._send_round_request(
            task_id=31, api_config=SimpleNamespace(id=1, meta={}),
            api_specific_config={}, session=SimpleNamespace(session_timeout=10),
            round_number=1, round_config={'input_type': 'audio'},
            case_algorithm_params=None, algorithm_type='voice_llm',
            case_config=None, total_rounds=1)

        assert captured['input_audio_path'] == 'local://audios/mix.wav'


class TestAdapterAudioResolution:
    """adapter 侧音频引用解析：存储引用/裸路径/字节，失败抛错不静默。"""

    def test_storage_ref_resolved_via_storage_layer(self, monkeypatch):
        from api_adapter_service.adapters.audio_input import resolve_audio_bytes
        import shared.infrastructure.storage as storage_mod

        monkeypatch.setattr(storage_mod.storage, 'load_bytes',
                            lambda path: b'STORED-AUDIO')
        assert resolve_audio_bytes('local://audios/x.wav') == b'STORED-AUDIO'
        assert resolve_audio_bytes('oss://audios/x.wav') == b'STORED-AUDIO'

    def test_bare_path_read_from_disk(self, tmp_path):
        from api_adapter_service.adapters.audio_input import resolve_audio_bytes
        f = tmp_path / 'a.wav'
        f.write_bytes(b'RAW-AUDIO')
        assert resolve_audio_bytes(str(f)) == b'RAW-AUDIO'

    def test_bytes_passthrough(self):
        from api_adapter_service.adapters.audio_input import resolve_audio_bytes
        assert resolve_audio_bytes(b'\x00\x01') == b'\x00\x01'

    def test_invalid_input_raises(self):
        from api_adapter_service.adapters.audio_input import resolve_audio_bytes
        with pytest.raises(ValueError):
            resolve_audio_bytes('')
        with pytest.raises(OSError):
            resolve_audio_bytes(os.path.join(
                tempfile.gettempdir(), 'no-such-audio-file-int71.wav'))

    def test_http_adapter_uploads_real_bytes(self, monkeypatch):
        from api_adapter_service.adapters.http_adapter import HttpAdapter
        import shared.infrastructure.storage as storage_mod

        monkeypatch.setattr(storage_mod.storage, 'load_bytes',
                            lambda path: b'REAL-AUDIO-BYTES')
        adapter = HttpAdapter({'base_url': 'http://api'})
        files, _data = adapter._build_audio_payload(
            's-1', 'local://audios/x.wav', 'zh', 'en', [], [], {}, '', 1, 1, 't')
        assert files['audio'][1] == b'REAL-AUDIO-BYTES'
