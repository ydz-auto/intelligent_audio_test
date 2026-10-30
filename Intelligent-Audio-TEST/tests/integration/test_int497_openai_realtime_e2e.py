# -*- coding: utf-8 -*-
"""INT-497 OpenAI Realtime 适配器端到端集成测试（验收标准 4）

链路（服务边界内全部真实组件，外部系统以替身仿真）：
    MockRealtimeServer（真实 mock 被测产品，mock_services/mock_realtime_api.py）
    → RealtimeSessionExecutor（真实执行器）
    → vendor_adapter_registry 严格分发（fallback=False）→ OpenAIRealtimeAdapter
      （真实品牌适配器，组合复用 RealtimeWSClient 传输/状态机）
    → 轮次混音 / 双通道推送 / 结果落库 / 评估队列：桩替身捕获

覆盖（对照验收标准 4）：
- 配置 vendor_adapter='openai_realtime' → 执行链经注册表分发使用适配器
  （resolve 调用 (realtime, openai, fallback=False) 被记录，验证最小接线）
- WS 会话建立（session.update → session.updated）、音频帧收发（append × N +
  commit）、事件流转（ai_audio_delta/done、user_speech_started、response_cancelled）
- 建用例（rounds 正常轮 + 打断轮）→ 执行（execute）→ 评估（evaluation ACL 收到
  algorithm_result，device_type='websocket_api'）→ 出结果（multi_round result + summary 推送）
- 超时/错误路径：断连注入收敛 connection_closed、协议错误注入 pre_process 失败
- 隔离库口径（INT-246）：pytest 会话守卫拒绝共享业务库；用例内 mock/会话
  teardown 清理，主线程 scoped session 移除防污染

外部系统以替身仿真（生产中为真实外部系统，测试只替换系统边界）：
- 轮次混音：RenderService 消费桩（逐 chunk s16 PCM，真实混音链路见 INT-67 专项）
- 跨服务 gRPC（task/algorithm/evaluation）：ACL 桩
- 双通道推送 / 结果落库 / AI 音频归档：桩捕获
"""
import base64
import os
import time

import pytest

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from types import SimpleNamespace

from shared.models.common_enums import (
    AdapterProtocol,
    AdapterVendor,
    DeviceType,
    RealtimeFrameType,
)
from shared.utils.config_manager import config_manager
import api_test_service.core.realtime_session_executor as rt_executor_module
from api_test_service.core.realtime_session_executor import RealtimeSessionExecutor
from api_test_service.domain.repositories.acl.audio_render_acl_repository import (
    RenderChunkDTO,
)
from mock_services.mock_realtime_api import MockRealtimeBehavior, MockRealtimeServer

# 测试提速：20ms 切片推送
config_manager.config.setdefault('realtime_session', {})['chunk_duration_ms'] = 20


# ── 替身 ──────────────────────────────────────────────────

class ConcurrencyStub:
    def acquire(self, api_id, task_id, tc_rel_id, max_process=None, timeout=None):
        return True

    def release(self, api_id, task_id):
        pass


class EngineStub:
    def update_case_round_progress(self, task_id, tc_rel_id, current, total):
        pass

    def _emit_progress(self, task_id, force=False):
        pass


class ExecutorStub:
    """RealtimeSessionExecutor 依赖的 APIExecutor 最小表面（鸭子类型）"""

    def __init__(self):
        self.execution_engine = EngineStub()
        self._concurrency = ConcurrencyStub()
        self.result_calls = []
        self.failure_calls = []

    def _handle_control(self, task_id):
        pass

    def _is_task_stopped(self, task_id):
        return False

    def _log(self, level='INFO', content='', **kwargs):
        pass

    class _ResultProcessor:
        def __init__(self, outer):
            self._outer = outer

        def create_multi_round_test_result(self, task_id, test_case_id,
                                           api_config_id, algorithm_type,
                                           aggregated, success, tc_rel_id=None):
            self._outer.result_calls.append({
                'task_id': task_id, 'test_case_id': test_case_id,
                'api_config_id': api_config_id, 'aggregated': aggregated,
                'success': success, 'tc_rel_id': tc_rel_id})
            return 555

        def update_task_case_failure(self, task_id, tc_rel_id, error_msg,
                                     utc_plus_8=None):
            self._outer.failure_calls.append(error_msg)

    @property
    def _result_processor(self):
        return self._ResultProcessor(self)


class PublisherStub:
    def __init__(self):
        self.frames = []
        self.summaries = []

    def publish_frame(self, task_id, test_case_id, session_id, round_number,
                      seq, frame):
        self.frames.append({'task_id': task_id, 'test_case_id': test_case_id,
                            'session_id': session_id, 'round_number': round_number,
                            'seq': seq, 'channel': 'realtime_frame', **frame})

    def publish_summary(self, task_id, test_case_id, session_id, summary):
        self.summaries.append({'task_id': task_id, 'test_case_id': test_case_id,
                               'session_id': session_id,
                               'channel': 'realtime_summary', **summary})


class EvaluationAclStub:
    def __init__(self):
        self.calls = []

    def submit_evaluate_case(self, task_id, result_id, test_case_id,
                             algorithm_result, eval_params, device_type=None):
        self.calls.append({'task_id': task_id, 'result_id': result_id,
                           'test_case_id': test_case_id,
                           'device_type': device_type,
                           'algorithm_result': algorithm_result,
                           'eval_params': eval_params})
        return True


class SplRepoStub:
    def get_default_mapping(self, api_id):
        return None


class RenderServiceStub:
    """RenderService 消费桩：按 chunk 时长产出 s16 chunk 流（INT-82 接线替身）"""

    def __init__(self, audio_pcm: bytes, chunk_ms: int = 20):
        self._audio_pcm = audio_pcm
        self._chunk_ms = chunk_ms
        self.stream_calls = []

    def stream_round_chunks(self, api_config, round_config, case_config, task_id):
        self.stream_calls.append({
            'api_id': getattr(api_config, 'id', None),
            'round_config': round_config, 'case_config': case_config,
            'task_id': task_id,
        })
        rate = 24000
        window_bytes = int(rate * self._chunk_ms / 1000) * 2  # s16 每窗字节
        pcm = self._audio_pcm
        windows = []
        for i in range(0, len(pcm), window_bytes):
            seg = pcm[i:i + window_bytes]
            if len(seg) < window_bytes:
                seg = seg + b'\x00' * (window_bytes - len(seg))
            windows.append(seg)
        return iter([
            RenderChunkDTO(sequence=idx, data_b64=base64.b64encode(w).decode('ascii'),
                           is_last=idx == len(windows) - 1, message='')
            for idx, w in enumerate(windows)
        ])


# ── 夹具 ──────────────────────────────────────────────────

@pytest.fixture()
def mock_rt():
    """真实 mock Realtime 服务器（barge_in 预置打断事件，barge_in=true 契约）"""
    server = MockRealtimeServer(MockRealtimeBehavior(barge_in=True))
    server.start()
    try:
        yield server
    finally:
        server.stop()
        server.service.state.reset()
        server.service.behavior = MockRealtimeBehavior()


@pytest.fixture()
def audio_pcm():
    """0.3s @24kHz s16 正弦替代（方波便于 RMS 断言）"""
    return (b'\x10\x27' * 3600) * 2  # 幅值 0x2710=10000，7200 样本


@pytest.fixture()
def harness(mock_rt, audio_pcm, monkeypatch):
    publisher = PublisherStub()
    eval_acl = EvaluationAclStub()
    rt_executor_module._evaluation_acl = eval_acl

    from api_test_service.infrastructure.acl import AlgorithmQueryAclRepositoryImpl
    monkeypatch.setattr(
        AlgorithmQueryAclRepositoryImpl, 'extract_case_all_params',
        lambda self, params: {'evaluation': {}})
    import shared.infrastructure.storage as storage_mod
    monkeypatch.setattr(
        storage_mod.storage, 'save_bytes',
        lambda data, category, key, content_type=None: f'local://{category}/{key}')

    # 记录最小接线的注册表 resolve 调用（(realtime, openai, fallback=False)）
    resolve_calls = []
    original_resolve = rt_executor_module.vendor_adapter_registry.resolve

    def recording_resolve(protocol, vendor=None, *, fallback=True):
        resolve_calls.append((protocol, vendor, fallback))
        return original_resolve(protocol, vendor, fallback=fallback)

    monkeypatch.setattr(rt_executor_module.vendor_adapter_registry, 'resolve',
                        recording_resolve)

    executor_stub = ExecutorStub()
    rt_executor = RealtimeSessionExecutor(executor_stub)
    rt_executor._publisher = publisher
    from api_test_service.domain.services.api_rms_spl_service import ApiRmsSplService
    rt_executor._spl_repo = SplRepoStub()
    rt_executor._spl_service = ApiRmsSplService(rt_executor._spl_repo)
    rt_executor._render_service = RenderServiceStub(audio_pcm, chunk_ms=20)

    api_config = SimpleNamespace(
        id=7, api_endpoints=[{'endpoint': mock_rt.url}],
        default_max_process=2, meta={'vendor': 'openai'}, max_timeout=30,
        vendor='openai')
    data = {
        'task_id': 100, 'tc_rel_id': 1, 'test_case_id': 11,
        'case_name': 'rt-openai-adapter-e2e',
        'algorithm_type': 'voice_llm',
        'device_type': DeviceType.WEBSOCKET_API.value,
        'api_configs': [api_config],
        'audio': {}, 'api_specific_config': {},
        'total_audio_duration': 0.3, 'case_algorithm_params': {}}
    # 建用例：rounds（正常轮 + 打断轮）+ vendor_adapter 显式选择 OpenAI 品牌适配器
    case_config = {'vendor_adapter': 'openai_realtime', 'rounds': [
        {'round_number': 1, 'audio_id': 1, 'spl': 65, 'query': '你好'},
        {'round_number': 2, 'audio_id': 1, 'spl': 65, 'is_interruption': True,
         'interruption_delay_ms': 50, 'original_topic': '打断话题'},
    ]}
    yield {
        'executor': rt_executor, 'stub': executor_stub,
        'publisher': publisher, 'eval_acl': eval_acl,
        'resolve_calls': resolve_calls, 'mock_rt': mock_rt,
        'data': data, 'case_config': case_config,
    }
    # teardown 清理：主线程 scoped session 移除，防线程局部污染后续用例
    from shared.models.database import remove_db_session
    remove_db_session()


# ── 验收标准 4：端到端 ────────────────────────────────────

class TestOpenAIRealtimeE2E:
    def test_full_chain_via_registry_dispatch(self, harness):
        """mock → 注册表分发 → OpenAIRealtimeAdapter → 执行 → 评估 → 出结果"""
        rt_executor = harness['executor']
        ok = rt_executor.execute(task_id=100, tc_rel_id=1,
                                 data=harness['data'],
                                 case_config=harness['case_config'])
        assert ok is True

        # ① 最小接线：执行链经注册表严格分发 (realtime, openai, fallback=False)
        assert (AdapterProtocol.REALTIME, AdapterVendor.OPENAI, False) \
            in harness['resolve_calls'], 'Realtime 品牌适配器分发未触发'

        # ② WS 会话建立：厂商收到 session.update 并确认 session.updated
        received = harness['mock_rt'].service.state.received
        assert received[0] == 'session.update'
        assert harness['mock_rt'].service.state.responses_streamed >= 1

        # ③ 音频帧收发：chunk 逐帧推送 + commit（两轮各一次）
        appends = received.count('input_audio_buffer.append')
        assert appends >= 10  # 0.3s @ 20ms/chunk ≈ 15 chunks/轮
        assert received.count('input_audio_buffer.commit') == 2

        # ④ 事件流转：frame 通道逐帧推送（含打断轮 barge-in 事件）
        frame_types = [f['type'] for f in harness['publisher'].frames]
        assert 'ai_audio_delta' in frame_types
        assert 'ai_audio_done' in frame_types
        assert 'user_speech_started' in frame_types
        assert 'response_cancelled' in frame_types

        # ⑤ 出结果：multi_round result 落库 + summary 通道推送
        assert len(harness['stub'].result_calls) == 1
        call = harness['stub'].result_calls[0]
        assert call['success'] is True
        assert call['api_config_id'] == 7
        aggregated = call['aggregated']
        algo = aggregated['algorithm_result']
        assert algo['round_count'] == 2
        assert algo['barge_in_total'] == 1
        assert algo['barge_in_success'] == 1
        assert aggregated['ai_output_rms_dbfs'] is not None
        assert 'ai_wav' in algo
        assert len(harness['publisher'].summaries) == 1
        assert harness['publisher'].summaries[0]['channel'] == 'realtime_summary'

        # ⑥ 评估：evaluation ACL 收到 algorithm_result，device_type='websocket_api'
        assert len(harness['eval_acl'].calls) == 1
        eval_call = harness['eval_acl'].calls[0]
        assert eval_call['result_id'] == 555
        assert eval_call['algorithm_result']['round_count'] == 2
        assert eval_call['eval_params']['device_type'] == 'websocket_api'

    def test_disconnect_injection_converges(self, mock_rt):
        """超时/错误路径：断连注入收敛 connection_closed，wait_ai_complete 判失败"""
        from api_test_service.infrastructure.adapters.vendors.openai_realtime_adapter import (
            OpenAIRealtimeAdapter,
        )
        mock_rt.set_behavior({'disconnect_after_events': 2})
        adapter = OpenAIRealtimeAdapter(
            SimpleNamespace(id=7, api_endpoints=[{'endpoint': mock_rt.url}], meta={}),
            case_config={}, endpoint=mock_rt.url)
        assert adapter.initialize() is True
        try:
            assert adapter.pre_process() is True
            adapter.send_audio_chunk(
                base64.b64encode(b'\x00\x01' * 40).decode('ascii'))
            end = time.time() + 5
            closed = False
            while time.time() < end:
                event = adapter.recv(timeout=1)
                if event.get('type') == RealtimeFrameType.CONNECTION_CLOSED.value:
                    closed = True
                    break
            assert closed, '断连注入后适配器未收敛 connection_closed'
            assert adapter.wait_ai_complete(start_timeout=2, end_timeout=2) is False
        finally:
            adapter.teardown()

    def test_protocol_error_injection_fails_pre_process(self, mock_rt):
        """超时/错误路径：协议错误注入 → pre_process 收敛失败（session.updated 未确认）"""
        from api_test_service.infrastructure.adapters.vendors.openai_realtime_adapter import (
            OpenAIRealtimeAdapter,
        )
        mock_rt.set_behavior({'protocol_error_on_event': 'session.update'})
        adapter = OpenAIRealtimeAdapter(
            SimpleNamespace(id=7, api_endpoints=[{'endpoint': mock_rt.url}], meta={}),
            case_config={}, endpoint=mock_rt.url)
        assert adapter.initialize() is True
        try:
            assert adapter.pre_process() is False
        finally:
            adapter.teardown()


# ── 最小接线分发判定（仅替换构造对象一处） ────────────────────────────

class TestWiringDispatch:
    """_resolve_realtime_transport 配置口径（方案审计拍板第 5 项）：
    openai/openai_realtime → 适配器；api_driver/mock/未配置 → RealtimeWSClient 默认。"""

    @staticmethod
    def _executor():
        from api_test_service.core.realtime_session_executor import RealtimeSessionExecutor
        ex = RealtimeSessionExecutor.__new__(RealtimeSessionExecutor)
        ex._executor = SimpleNamespace(_log=lambda *a, **k: None)
        ex._on_frame = lambda *a, **k: None
        return ex

    @staticmethod
    def _cfg(endpoint='ws://mock', vendor_adapter=None, meta=None):
        cfg = SimpleNamespace(
            id=7, api_endpoints=[{'endpoint': endpoint}], meta=dict(meta or {}),
            max_timeout=30, vendor='openai')
        return cfg

    def test_case_level_vendor_adapter_selects_adapter(self):
        ex = self._executor()
        transport = ex._resolve_realtime_transport(
            self._cfg(), {'vendor_adapter': 'openai_realtime'}, {},
            'ws://mock', {}, 20, 1, 'c1', 'rt-1')
        from api_test_service.infrastructure.adapters.vendors.openai_realtime_adapter import (
            OpenAIRealtimeAdapter,
        )
        assert isinstance(transport, OpenAIRealtimeAdapter)

    def test_api_specific_config_selects_adapter(self):
        """per-API 配置（api_specific_config）与 HTTP 路径同口径"""
        ex = self._executor()
        transport = ex._resolve_realtime_transport(
            self._cfg(), {}, {'vendor_adapter': 'openai'},
            'ws://mock', {}, 20, 1, 'c1', 'rt-1')
        from api_test_service.infrastructure.adapters.vendors.openai_realtime_adapter import (
            OpenAIRealtimeAdapter,
        )
        assert isinstance(transport, OpenAIRealtimeAdapter)

    def test_api_meta_vendor_adapter_selects_adapter(self):
        ex = self._executor()
        transport = ex._resolve_realtime_transport(
            self._cfg(meta={'vendor_adapter': 'openai_realtime'}), {}, {},
            'ws://mock', {}, 20, 1, 'c1', 'rt-1')
        from api_test_service.infrastructure.adapters.vendors.openai_realtime_adapter import (
            OpenAIRealtimeAdapter,
        )
        assert isinstance(transport, OpenAIRealtimeAdapter)

    def test_unset_keeps_realtime_ws_client(self):
        """未配置 / api_driver / mock → RealtimeWSClient 默认（向后兼容）"""
        from api_test_service.infrastructure.adapters.transport import RealtimeWSClient
        ex = self._executor()
        for vendor_adapter in (None, 'api_driver', 'mock'):
            case_cfg = ({'vendor_adapter': vendor_adapter}
                        if vendor_adapter else {})
            transport = ex._resolve_realtime_transport(
                self._cfg(), case_cfg, {}, 'ws://mock', {}, 20, 1, 'c1', 'rt-1')
            assert isinstance(transport, RealtimeWSClient), vendor_adapter

    def test_strict_resolve_failure_propagates(self, monkeypatch):
        """显式配置 REALTIME 品牌适配器但未注册 → resolve 失败必须抛错、
        不静默回退 RealtimeWSClient（防双通道语义歧义）"""
        from api_test_service.infrastructure.adapters import (
            VendorAdapterNotFoundError,
            VendorAdapterRegistry,
        )
        import api_test_service.core.realtime_session_executor as rt_mod
        monkeypatch.setattr(rt_mod, 'vendor_adapter_registry',
                            VendorAdapterRegistry())
        ex = self._executor()
        with pytest.raises(VendorAdapterNotFoundError, match='未注册的厂商适配器'):
            ex._resolve_realtime_transport(
                self._cfg(), {'vendor_adapter': 'openai_realtime'}, {},
                'ws://mock', {}, 20, 1, 'c1', 'rt-1')
