# -*- coding: utf-8 -*-
"""INT-61 执行器注册表路由单测 — INT-1799 改为按执行道（streaming）分发

覆盖：
- route_executor：ExecutionLane.STREAMING → RealtimeSessionExecutor；
  NON_STREAMING → APISessionExecutor；历史 device_type 值作等价别名；
  未知/None → ValueError（删除静默回退）
- _execute_single_or_multi：streaming=true 分流式道；streaming=false 且多轮 →
  APISessionExecutor；单轮 → 线性（rounds 不再推断流式性）
- _resolve_ws_url / _resolve_ws_headers 辅助逻辑；
  轮次音频解析接线 INT-82 后归 RoundRenderService（见 TestRoundAudioResolution）
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from types import SimpleNamespace

import pytest

from shared.models.common_enums import DeviceType, ExecutionLane
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
                endpoints=None, protocol='websocket', streaming=True):
    return SimpleNamespace(
        id=api_id, endpoint=endpoint,
        api_endpoints=endpoints if endpoints is not None else [],
        default_max_process=2, meta=meta or {}, max_timeout=30, vendor='openai',
        protocol=protocol, streaming=streaming)


class TestRouteExecutor:
    def test_streaming_lane_routes_to_realtime(self):
        executor = _make_api_executor()
        assert executor.route_executor(ExecutionLane.STREAMING) is executor._realtime_executor
        assert executor.route_executor(ExecutionLane.STREAMING.value) is executor._realtime_executor

    def test_non_streaming_lane_routes_to_api_session(self):
        executor = _make_api_executor()
        assert executor.route_executor(ExecutionLane.NON_STREAMING) is executor._session_executor
        assert executor.route_executor('non_streaming') is executor._session_executor

    def test_legacy_device_type_still_accepted(self):
        """老调用方传 device_type：确定性映射到道（不是未知值静默回退）"""
        executor = _make_api_executor()
        assert executor.route_executor(DeviceType.WEBSOCKET_API.value) is executor._realtime_executor
        assert executor.route_executor(DeviceType.HTTP_API.value) is executor._session_executor

    def test_unknown_lane_raises(self):
        """未知 / 空 lane 一律抛错（删除「未知类型回退 APISessionExecutor」）"""
        executor = _make_api_executor()
        for bad in ('', None, 'weird_type', 'physical'):
            with pytest.raises(ValueError):
                executor.route_executor(bad)

    def test_registry_instances(self):
        executor = _make_api_executor()
        assert isinstance(executor._realtime_executor, RealtimeSessionExecutor)
        assert isinstance(executor._session_executor, APISessionExecutor)


class TestExecuteDispatch:
    def test_streaming_true_dispatches_to_realtime_executor(self):
        """streaming=true → 流式道（Realtime 会话策略），与 rounds 无关"""
        executor = _make_api_executor()
        calls = {}
        executor._realtime_executor.execute = \
            lambda *a, **k: calls.setdefault('hit', True)

        data = {'test_case_id': 1, 'case_name': 'rt-case',
                'streaming': True, 'protocol': 'websocket',
                'api_configs': [_api_config()], 'audio': {},
                'api_specific_config': {}, 'total_audio_duration': 1.0,
                'case_algorithm_params': {}, 'algorithm_type': 'voice_llm'}
        executor._load_case_config = lambda tc_id: {'rounds': [{'round_number': 1}]}
        executor._execute_single_or_multi(task_id=100, tc_rel_id=1, data=data)
        assert calls.get('hit') is True

    def test_streaming_true_with_unsupported_protocol_rejected(self):
        """未知协议 + streaming=true → 显式报错，不得静默走非流式

        A2（INT-1790）后 websocket / sse / http / grpc 四种协议都有流式策略，
        「未上线」只剩注册表外的协议值，故用 mqtt 验证同一道报错口径。
        """
        executor = _make_api_executor()
        data = {'test_case_id': 1, 'case_name': 'mqtt-stream',
                'streaming': True, 'protocol': 'mqtt',
                'api_configs': [_api_config(protocol='mqtt')], 'audio': {},
                'api_specific_config': {}, 'total_audio_duration': 1.0,
                'case_algorithm_params': {}, 'algorithm_type': 'translation'}
        executor._load_case_config = lambda tc_id: {'rounds': [{'round_number': 1}]}
        with pytest.raises(ValueError, match='实现未上线'):
            executor._execute_single_or_multi(task_id=100, tc_rel_id=1, data=data)

    def test_non_streaming_multi_round_uses_session(self):
        """streaming=false 且多轮 → APISessionExecutor（零回归，rounds 只决定道内策略）"""
        executor = _make_api_executor()
        calls = {'session': 0, 'realtime': 0}
        executor._session_executor.execute = \
            lambda *a, **k: calls.__setitem__('session', calls['session'] + 1)
        executor._realtime_executor.execute = \
            lambda *a, **k: calls.__setitem__('realtime', calls['realtime'] + 1)

        data = {'test_case_id': 1, 'case_name': 'api-case',
                'streaming': False, 'protocol': 'http',
                'api_configs': [_api_config(endpoint='http://vendor/api',
                                            protocol='http', streaming=False)],
                'audio': {}, 'api_specific_config': {},
                'total_audio_duration': 1.0, 'case_algorithm_params': {},
                'algorithm_type': 'translation'}
        executor._load_case_config = lambda tc_id: {'rounds': [
            {'round_number': 1}, {'round_number': 2}]}
        executor._execute_single_or_multi(task_id=100, tc_rel_id=1, data=data)
        assert calls == {'session': 1, 'realtime': 0}

    def test_missing_streaming_defaults_to_non_streaming(self):
        """旧数据无 streaming 键 → 非流式道（布尔缺省 false），不进 Realtime"""
        executor = _make_api_executor()
        calls = {'session': 0, 'realtime': 0}
        executor._session_executor.execute = \
            lambda *a, **k: calls.__setitem__('session', calls['session'] + 1)
        executor._realtime_executor.execute = \
            lambda *a, **k: calls.__setitem__('realtime', calls['realtime'] + 1)

        data = {'test_case_id': 1, 'case_name': 'legacy-case',
                'api_configs': [_api_config(endpoint='http://vendor/api',
                                            protocol='http', streaming=False)],
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
        # INT-1361：api_url 移除后仅 api_endpoints 为端点来源，
        # endpoint 顶层回退已删除；仅剩顶层 endpoint 时显式报错
        cfg = _api_config(endpoint='ws://vendor/rt')
        try:
            RealtimeSessionExecutor._resolve_ws_url(cfg)
            raise AssertionError('缺 api_endpoints 的 WS 端点应显式报错')
        except ValueError:
            pass

        cfg_eps = _api_config(endpoint='ws://fallback/rt',
                              endpoints=[{'endpoint': 'ws://vendor/rt'}])
        assert RealtimeSessionExecutor._resolve_ws_url(cfg_eps) == 'ws://vendor/rt'

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
