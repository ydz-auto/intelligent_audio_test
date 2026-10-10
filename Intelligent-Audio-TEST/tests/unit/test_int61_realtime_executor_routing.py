# -*- coding: utf-8 -*-
"""INT-61 执行器注册表路由单测 — device_type 运行时分发

覆盖：
- route_executor：websocket_api → RealtimeSessionExecutor；
  http_api → APISessionExecutor；未知类型回退 APISessionExecutor（旧任务兼容）
- _execute_single_or_multi：device_type=websocket_api 分发至 Realtime 执行器；
  http_api 数据维持既有行为（多轮会话 / 线性）
- _resolve_ws_url / _resolve_ws_headers 辅助逻辑；
  轮次音频解析接线 INT-82 后归 RoundRenderService（见 TestRoundAudioResolution）
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from types import SimpleNamespace

from shared.models.common_enums import DeviceType
from api_test_service.core.api_executor import APIExecutor
from api_test_service.core.api_session_executor import APISessionExecutor
from api_test_service.core.realtime_session_executor import RealtimeSessionExecutor


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


def _make_api_executor():
    return APIExecutor(_EngineStub())


def _api_config(api_id=7, endpoint='ws://vendor.example/realtime', meta=None,
                endpoints=None):
    return SimpleNamespace(
        id=api_id, endpoint=endpoint,
        api_endpoints=endpoints if endpoints is not None else [],
        default_max_process=2, meta=meta or {}, max_timeout=30, vendor='openai')


class TestRouteExecutor:
    def test_websocket_api_routes_to_realtime(self):
        executor = _make_api_executor()
        assert executor.route_executor(DeviceType.WEBSOCKET_API.value) is \
            executor._realtime_executor

    def test_http_api_routes_to_api_session(self):
        executor = _make_api_executor()
        assert executor.route_executor(DeviceType.HTTP_API.value) is \
            executor._session_executor

    def test_unknown_type_falls_back_to_api_session(self):
        """旧任务 device_type 缺省/未知 → APISessionExecutor（行为不变）"""
        executor = _make_api_executor()
        assert executor.route_executor('') is executor._session_executor
        assert executor.route_executor('weird_type') is executor._session_executor

    def test_registry_instances(self):
        executor = _make_api_executor()
        assert isinstance(executor._realtime_executor, RealtimeSessionExecutor)
        assert isinstance(executor._session_executor, APISessionExecutor)


class TestExecuteDispatch:
    def test_websocket_api_dispatches_to_realtime_executor(self):
        """device_type=websocket_api → Realtime 执行器（含单轮）"""
        executor = _make_api_executor()
        calls = {}
        executor._realtime_executor.execute = \
            lambda *a, **k: calls.setdefault('hit', True)

        data = {'test_case_id': 1, 'case_name': 'rt-case',
                'device_type': DeviceType.WEBSOCKET_API.value,
                'api_configs': [_api_config()], 'audio': {},
                'api_specific_config': {}, 'total_audio_duration': 1.0,
                'case_algorithm_params': {}, 'algorithm_type': 'voice_llm'}
        executor._load_case_config = lambda tc_id: {'rounds': [{'round_number': 1}]}
        executor._execute_single_or_multi(task_id=100, tc_rel_id=1, data=data)
        assert calls.get('hit') is True

    def test_http_api_keeps_legacy_behavior(self):
        """device_type=http_api 且多轮 → APISessionExecutor（既有行为不变）"""
        executor = _make_api_executor()
        calls = {'session': 0, 'realtime': 0}
        executor._session_executor.execute = \
            lambda *a, **k: calls.__setitem__('session', calls['session'] + 1)
        executor._realtime_executor.execute = \
            lambda *a, **k: calls.__setitem__('realtime', calls['realtime'] + 1)

        data = {'test_case_id': 1, 'case_name': 'api-case',
                'device_type': DeviceType.HTTP_API.value,
                'api_configs': [_api_config(endpoint='http://vendor/api')],
                'audio': {}, 'api_specific_config': {},
                'total_audio_duration': 1.0, 'case_algorithm_params': {},
                'algorithm_type': 'translation'}
        executor._load_case_config = lambda tc_id: {'rounds': [
            {'round_number': 1}, {'round_number': 2}]}
        executor._execute_single_or_multi(task_id=100, tc_rel_id=1, data=data)
        assert calls == {'session': 1, 'realtime': 0}

    def test_missing_device_type_keeps_legacy_behavior(self):
        """旧数据无 device_type → 不进 Realtime 执行器"""
        executor = _make_api_executor()
        calls = {'session': 0, 'realtime': 0}
        executor._session_executor.execute = \
            lambda *a, **k: calls.__setitem__('session', calls['session'] + 1)
        executor._realtime_executor.execute = \
            lambda *a, **k: calls.__setitem__('realtime', calls['realtime'] + 1)

        data = {'test_case_id': 1, 'case_name': 'legacy-case',
                'api_configs': [_api_config(endpoint='http://vendor/api')],
                'audio': {}, 'api_specific_config': {},
                'total_audio_duration': 1.0, 'case_algorithm_params': {},
                'algorithm_type': 'translation'}
        executor._load_case_config = lambda tc_id: {'rounds': [
            {'round_number': 1}, {'round_number': 2}]}
        executor._execute_single_or_multi(task_id=100, tc_rel_id=1, data=data)
        assert calls == {'session': 1, 'realtime': 0}


class TestWSResolutionHelpers:
    def test_resolve_ws_url_prefers_api_endpoints(self):
        cfg = _api_config(
            endpoint='http://fallback/api',
            endpoints=[{'endpoint': 'http://x'}, {'endpoint': 'wss://vendor/ws'}])
        assert RealtimeSessionExecutor._resolve_ws_url(cfg) == 'wss://vendor/ws'

    def test_resolve_ws_url_falls_back_to_endpoint(self):
        cfg = _api_config(endpoint='ws://vendor/rt')
        assert RealtimeSessionExecutor._resolve_ws_url(cfg) == 'ws://vendor/rt'

    def test_resolve_ws_url_rejects_non_ws(self):
        try:
            RealtimeSessionExecutor._resolve_ws_url(_api_config(endpoint='http://x'))
            raise AssertionError('非 WS 端点应显式报错')
        except ValueError:
            pass

    def test_resolve_ws_headers_bearer_from_api_key(self):
        cfg = _api_config(meta={'api_key': 'sk-123'})
        headers = RealtimeSessionExecutor._resolve_ws_headers(cfg)
        assert headers['Authorization'] == 'Bearer sk-123'

    def test_resolve_ws_headers_passthrough_and_no_override(self):
        cfg = _api_config(meta={
            'api_key': 'sk-123',
            'ws_headers': {'Authorization': 'Custom', 'X-Flag': '1'}})
        headers = RealtimeSessionExecutor._resolve_ws_headers(cfg)
        assert headers['Authorization'] == 'Custom'
        assert headers['X-Flag'] == '1'


class TestRoundAudioResolution:
    """轮次音频解析（INT-82 接线后归 RoundRenderService._normalize_round_audios：
    多源 audios 全量进入混音时间轴，不再单源挑选；旧 audio_id 字段合成 speaker 源）"""

    def test_all_audios_enter_mix(self):
        from api_test_service.application.round_render_service import RoundRenderService
        rc = {'audios': [
            {'audio_id': 2, 'type': 'interferer', 'spl': 55},
            {'audio_id': 1, 'type': 'speaker', 'spl': 65}]}
        assert RoundRenderService._normalize_round_audios(rc) == rc['audios']

    def test_legacy_audio_id_synthesized_as_speaker(self):
        from api_test_service.application.round_render_service import RoundRenderService
        assert RoundRenderService._normalize_round_audios({'audio_id': 9}) == [
            {'audio_id': 9, 'type': 'speaker', 'spl': 65.0}]

    def test_missing_audio_returns_empty(self):
        from api_test_service.application.round_render_service import RoundRenderService
        assert RoundRenderService._normalize_round_audios({}) == []
