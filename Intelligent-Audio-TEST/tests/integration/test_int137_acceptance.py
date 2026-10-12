# -*- coding: utf-8 -*-
"""INT-137 验收补充（测试工程师）：真实 RealtimeSessionExecutor 对接 mock realtime。

AC2 执行器级证据：mock 第三方评估链路见 test_int137_mock_services.py（客户端协议层）；
本文件把被测面上移一层 —— 真实 RealtimeSessionExecutor（frame/summary 双通道、
多轮循环、聚合落库、评估入队）对接 mock_realtime_api（真实 WS 服务端替身）：
- frame 通道：mock 逐帧 ack（input_audio_buffer.append.ack 透传）逐帧可见
- summary 通道：会话收口（多轮聚合 + barge-in 统计 + 评估入队）
- AC3 执行器级：中途断连注入 → 轮次收敛失败不悬挂

替身边界与 INT-61 既有执行器集成测试一致（渲染/SPL/存储/评估 ACL 桩），
厂商 WS 从伪厂商换成 mock_services 独立替身 —— 生产组件边界全真实。
"""
import base64
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.utils.config_manager import config_manager
from shared.models.common_enums import DeviceType
import api_test_service.core.realtime_session_executor as rt_executor_module
from api_test_service.core.realtime_session_executor import RealtimeSessionExecutor
from api_test_service.infrastructure.acl import AlgorithmQueryAclRepositoryImpl
from mock_services.mock_realtime_api import MockRealtimeBehavior, MockRealtimeServer
from tests.integration.test_int61_realtime_full_chain import (
    ConcurrencyStub,
    EngineStub,
    EvaluationAclStub,
    ExecutorStub,
    PublisherStub,
    RenderServiceStub,
    SplRepoStub,
)

config_manager.config.setdefault('realtime_session', {})['chunk_duration_ms'] = 20


class RegistryStub:
    """会话亲和桩：不触 Redis（亲和语义由 INT-61 专项覆盖）"""

    def bind(self, task_id):
        return 'local', False

    def release(self, task_id):
        pass


@pytest.fixture()
def mock_rt():
    """mock Realtime 替身（barge_in 预置打断事件序列，支撑打断轮）。"""
    server = MockRealtimeServer(MockRealtimeBehavior(barge_in=True))
    server.start()
    try:
        yield server
    finally:
        server.stop()


@pytest.fixture()
def audio_pcm():
    """0.3s @24kHz s16 方波（INT-61 同构）。"""
    return (b'\x10\x27' * 3600) * 2


@pytest.fixture()
def harness(mock_rt, audio_pcm, monkeypatch):
    publisher = PublisherStub()
    eval_acl = EvaluationAclStub()
    monkeypatch.setattr(rt_executor_module, '_evaluation_acl', eval_acl)
    monkeypatch.setattr(
        AlgorithmQueryAclRepositoryImpl, 'extract_case_all_params',
        lambda self, params: {'evaluation': {}})
    import shared.infrastructure.storage as storage_mod
    monkeypatch.setattr(
        storage_mod.storage, 'save_bytes',
        lambda data, category, key, content_type=None: f'local://{category}/{key}')

    executor_stub = ExecutorStub()
    rt_executor = RealtimeSessionExecutor(executor_stub)
    rt_executor._publisher = publisher
    rt_executor._session_registry = RegistryStub()
    rt_executor._spl_repo = SplRepoStub()
    from api_test_service.domain.services.api_rms_spl_service import ApiRmsSplService
    rt_executor._spl_service = ApiRmsSplService(rt_executor._spl_repo)
    rt_executor._render_service = RenderServiceStub(audio_pcm, chunk_ms=20)

    api_config = SimpleNamespace(
        id=7, endpoint=mock_rt.url, api_endpoints=[],
        default_max_process=2, meta={'vendor': 'openai'}, max_timeout=30,
        vendor='openai')
    data = {
        'task_id': 1371, 'tc_rel_id': 1, 'test_case_id': 13710,
        'case_name': 'int137-executor-vs-mock',
        'algorithm_type': 'voice_llm',
        'device_type': DeviceType.WEBSOCKET_API.value,
        'api_configs': [api_config],
        'audio': {}, 'api_specific_config': {},
        'total_audio_duration': 0.3, 'case_algorithm_params': {}}
    case_config = {'rounds': [
        {'round_number': 1, 'audio_id': 1, 'spl': 65, 'query': '你好'},
        {'round_number': 2, 'audio_id': 1, 'spl': 65, 'is_interruption': True,
         'interruption_delay_ms': 50, 'original_topic': '打断话题'},
    ]}
    yield {
        'executor': rt_executor, 'stub': executor_stub,
        'publisher': publisher, 'eval_acl': eval_acl,
        'server': mock_rt, 'data': data, 'case_config': case_config,
    }
    from shared.models.database import remove_db_session
    remove_db_session()


class TestExecutorAgainstMockRealtime:
    """AC2：RealtimeSessionExecutor（frame/summary 双通道）对接 mock 全链。"""

    def test_frame_ack_and_summary_closeout(self, harness):
        rt_executor = harness['executor']
        ok = rt_executor.execute(task_id=1371, tc_rel_id=1,
                                 data=harness['data'],
                                 case_config=harness['case_config'])
        assert ok is True

        # mock 服务端观测：会话建立 / 逐帧 append / 两次 commit / 两次响应流
        received = harness['server'].service.state.received
        assert received[0] == 'session.update'
        assert received.count('input_audio_buffer.append') >= 20
        assert received.count('input_audio_buffer.commit') == 2
        assert harness['server'].service.state.responses_streamed == 2

        # frame 通道：mock 逐帧 ack 逐帧可见（未知事件透传，类型不变）
        frame_types = [f['type'] for f in harness['publisher'].frames]
        assert frame_types.count('input_audio_buffer.append.ack') >= 20
        # committed 经防腐层归一化（input_audio_buffer.committed → input_committed）
        assert frame_types.count('input_committed') == 2
        assert frame_types.count('ai_audio_delta') >= 5
        assert frame_types.count('ai_audio_done') == 2
        # 打断轮：AI 说话 + 打断事件序列经 mock 预置 → frame 通道可见
        assert 'user_speech_started' in frame_types
        assert 'response_cancelled' in frame_types

        # summary 收口：聚合落库（轮次明细 + barge-in 统计 + 首帧延迟实测）
        assert len(harness['stub'].result_calls) == 1
        call = harness['stub'].result_calls[0]
        assert call['success'] is True
        algo = call['aggregated']['algorithm_result']
        assert algo['round_count'] == 2
        assert algo['barge_in_total'] == 1
        assert algo['barge_in_success'] == 1
        normal_round = algo['rounds'][0]
        assert normal_round['success'] is True
        assert normal_round['answer_text'] == 'mock 回复文本'
        assert normal_round['first_frame_latency_ms'] is not None
        interrupt_round = algo['rounds'][1]
        assert interrupt_round['mode'] == 'interruption'
        assert interrupt_round['barge_in_detected'] is True
        assert interrupt_round['ai_renewed'] is True
        assert interrupt_round['success'] is True

        # summary 通道推送（会话汇总）
        assert len(harness['publisher'].summaries) == 1
        summary = harness['publisher'].summaries[0]
        assert summary['channel'] == 'realtime_summary'
        assert summary['round_count'] == 2
        assert summary['barge_in_total'] == 1

        # 会话成功 → 评估队列提交（test_type='api'，执行器语义不变）
        assert len(harness['eval_acl'].calls) == 1
        assert harness['eval_acl'].calls[0]['eval_params']['test_type'] == 'api'

    def test_disconnect_injection_converges(self, harness):
        harness['server'].set_behavior({'disconnect_after_events': 3})
        rt_executor = harness['executor']
        rt_executor.execute(task_id=1371, tc_rel_id=1,
                            data=harness['data'],
                            case_config=harness['case_config'])

        # 中途断连 → 轮次收敛失败（不悬挂）：失败点可能在推送（socket closed）
        # 或等待回复（AI 回复未在超时内完成），取决于服务端断连与客户端发送的竞态
        call = harness['stub'].result_calls[0]
        assert call['success'] is False
        rounds = call['aggregated']['algorithm_result']['rounds']
        assert rounds[0]['success'] is False
        assert rounds[0].get('error')
        assert harness['publisher'].summaries[0]['success'] is False
        assert harness['eval_acl'].calls == []
