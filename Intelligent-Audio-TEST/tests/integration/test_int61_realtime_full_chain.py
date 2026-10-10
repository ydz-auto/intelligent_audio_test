# -*- coding: utf-8 -*-
"""INT-61 Realtime 执行链路端到端集成测试（验收标准 1）

真实链路（服务边界内全部真实组件）：
RealtimeSessionExecutor（真实执行器 + 真实路由）
  → RealtimeWSClient（真实 WS 客户端）→ 进程内伪厂商 Realtime 服务器
  → RealtimeAudioRenderer（真实渲染：格式适配 + SPL 增益 + 100ms 切片）
  → frame 双通道推送（桩发布器捕获）→ summary 落库（桩结果处理器捕获）
  → 评估队列提交（桩评估 ACL 捕获）

外部系统以替身仿真（生产中为真实外部系统，测试只替换系统边界）：
- 厂商 Realtime API：伪 WS 服务器（session.update 确认 / delta 流 / done /
  barge-in 事件）
- 轮次音频：内存生成的 s16 PCM（真实 WAV 解析见渲染器/音频源单测）
- 跨服务 gRPC（task/algorithm/evaluation）：ACL 桩

覆盖（对照验收标准 1）：
1. WS 建立（session.update → session.updated）
2. 流式执行（append chunk × N + commit，SPL 校准增益生效）
3. frame 通道逐帧推送（ai_audio_delta / ai_audio_done / user_speech_started）
4. summary 落库（algorithm_result.rounds + barge-in 统计 + SPL 口径字段）
5. 评估完成（evaluation ACL 收到 algorithm_result，test_type='api' 入队）
"""
import base64
import json
import os
import threading

import pytest

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.utils.config_manager import config_manager
from shared.models.common_enums import DeviceType
import api_test_service.core.realtime_session_executor as rt_executor_module
from api_test_service.core.realtime_session_executor import RealtimeSessionExecutor
from api_test_service.domain.services.realtime_audio_renderer import AudioFormat
from api_test_service.infrastructure.acl import AlgorithmQueryAclRepositoryImpl
from tests.unit.test_int61_realtime_ws_client import FakeVendorRealtimeServer

# 测试提速：20ms 切片推送
config_manager.config.setdefault('realtime_session', {})['chunk_duration_ms'] = 20


# ── 替身 ──────────────────────────────────────────────────

class BargeInVendorServer(FakeVendorRealtimeServer):
    """带打断场景的伪厂商：第 1 轮 commit 后预置 AI 说话 + 打断事件入队，
    模拟上一轮回复未结束、打断轮开始时 AI 正在说话的真实时序"""

    def __init__(self):
        super().__init__(mode='executor_barge_in')
        self._round_commits = 0

    def start(self):
        import websockets

        async def handler(ws):
            async for raw in ws:
                event = json.loads(raw)
                etype = event.get('type')
                self.received.append(etype)
                if etype == 'session.update':
                    await ws.send(json.dumps({'type': 'session.updated'}))
                elif etype == 'input_audio_buffer.commit':
                    self._round_commits += 1
                    await ws.send(json.dumps({'type': 'input_audio_buffer.committed'}))
                    for _ in range(3):
                        await ws.send(json.dumps(
                            {'type': 'response.audio.delta',
                             'delta': base64.b64encode(b'\x01\x02').decode('ascii')}))
                    await ws.send(json.dumps({'type': 'response.done'}))
                    if self._round_commits == 1:
                        # 预置下一轮（打断轮）的 AI 说话与打断事件
                        await ws.send(json.dumps(
                            {'type': 'response.audio.delta',
                             'delta': base64.b64encode(b'\x03\x04').decode('ascii')}))
                        await ws.send(json.dumps(
                            {'type': 'input_audio_buffer.speech_started'}))
                        await ws.send(json.dumps({'type': 'response.cancelled'}))

        import asyncio

        async def serve():
            self._server = await websockets.serve(handler, '127.0.0.1', 0)
            self.port = self._server.sockets[0].getsockname()[1]
            self._started.set()
            await self._server.serve_forever()

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_until_complete, args=(serve(),), daemon=True)
        self._thread.start()
        assert self._started.wait(timeout=5), '伪厂商服务器启动超时'


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

    def _log(self, level='INFO', content='', **kwargs):
        pass

    class _ResultProcessor:
        def __init__(self, outer):
            self._outer = outer

        def create_multi_round_test_result(self, task_id, test_case_id, api_config_id,
                                           algorithm_type, aggregated, success):
            self._outer.result_calls.append({
                'task_id': task_id, 'test_case_id': test_case_id,
                'api_config_id': api_config_id, 'aggregated': aggregated,
                'success': success})
            return 555

        def update_task_case_failure(self, task_id, tc_rel_id, error_msg,
                                     utc_plus_8=None):
            self._outer.failure_calls.append(error_msg)

    @property
    def _result_processor(self):
        return self._ResultProcessor(self)


class PublisherStub:
    """双通道发布桩：捕获 frame / summary（载荷结构与真实发布器一致）"""

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
                             algorithm_result, eval_params):
        self.calls.append({
            'task_id': task_id, 'result_id': result_id,
            'test_case_id': test_case_id,
            'algorithm_result': algorithm_result, 'eval_params': eval_params})
        return True


class SplRepoStub:
    """SPL 映射仓储桩：本链路测口径计算，不触 DB（避免污染全局线程局部会话）"""

    def get_default_mapping(self, api_id):
        return None

    def get_mapping(self, mapping_id):
        return None


# ── 夹具 ──────────────────────────────────────────────────

@pytest.fixture
def vendor_server():
    server = BargeInVendorServer()
    server.start()
    yield server
    server.stop()


@pytest.fixture
def audio_pcm():
    """0.3s @24kHz s16 正弦替代（方波便于 RMS 断言）"""
    return (b'\x10\x27' * 3600) * 2  # 幅值 0x2710=10000，7200 样本


@pytest.fixture
def harness(vendor_server, audio_pcm, monkeypatch):
    publisher = PublisherStub()
    eval_acl = EvaluationAclStub()
    rt_executor_module._evaluation_acl = eval_acl

    monkeypatch.setattr(
        AlgorithmQueryAclRepositoryImpl, 'extract_case_all_params',
        lambda self, params: {'evaluation': {}})
    # AI 音频归档走 OSS，测试环境替换为内存桩
    import shared.infrastructure.storage as storage_mod
    monkeypatch.setattr(
        storage_mod.storage, 'save_bytes',
        lambda data, category, key, content_type=None: f'local://{category}/{key}')

    executor_stub = ExecutorStub()
    rt_executor = RealtimeSessionExecutor(executor_stub)
    rt_executor._publisher = publisher
    # SPL 域服务为纯计算：仅把查表仓储替换为桩（口径走线性近似），
    # 本链路全程不触全局 DB 会话，避免线程局部 Session 污染后续测试
    from api_test_service.domain.services.api_rms_spl_service import ApiRmsSplService
    from api_test_service.domain.services.realtime_audio_renderer import (
        RealtimeAudioRenderer,
    )
    rt_executor._spl_repo = SplRepoStub()
    rt_executor._spl_service = ApiRmsSplService(rt_executor._spl_repo)
    rt_executor._renderer = RealtimeAudioRenderer(rt_executor._spl_service)
    # 轮次音频：内存 PCM 替身（音频字节加载链路另有单测/桩覆盖）
    rt_executor._audio_source = type('SrcStub', (), {
        'get_pcm': staticmethod(lambda audio_id: (audio_pcm, AudioFormat(24000, 's16', 1)))})()

    from types import SimpleNamespace
    api_config = SimpleNamespace(
        id=7, endpoint=vendor_server.url, api_endpoints=[],
        default_max_process=2, meta={'vendor': 'openai'}, max_timeout=30,
        vendor='openai')
    data = {
        'task_id': 100, 'tc_rel_id': 1, 'test_case_id': 11,
        'case_name': 'rt-integration',
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
        'data': data, 'case_config': case_config,
        'server': vendor_server,
    }
    # 防护：清理主线程线程局部 scoped session，避免任何意外 DB 触碰
    # 留下 bind=None 的会话对象污染同线程后续测试（flush 时 UnboundExecutionError）
    from shared.models.database import remove_db_session
    remove_db_session()


# ── 验收标准 1：端到端 ────────────────────────────────────

class TestRealtimeEndToEnd:
    def test_full_chain(self, harness):
        rt_executor = harness['executor']
        ok = rt_executor.execute(task_id=100, tc_rel_id=1,
                                 data=harness['data'],
                                 case_config=harness['case_config'])
        assert ok is True

        # ① WS 建立：厂商收到 session.update
        assert 'session.update' in harness['server'].received

        # ② 流式执行：chunk 逐帧推送 + commit（两轮各一次）
        appends = harness['server'].received.count('input_audio_buffer.append')
        assert appends >= 10  # 0.3s @ 20ms/chunk ≈ 15 chunks/轮
        assert harness['server'].received.count('input_audio_buffer.commit') == 2

        # ③ frame 通道逐帧推送
        frame_types = [f['type'] for f in harness['publisher'].frames]
        assert 'ai_audio_delta' in frame_types
        assert 'ai_audio_done' in frame_types
        assert 'user_speech_started' in frame_types  # 打断轮
        assert 'response_cancelled' in frame_types

        # ④ summary 落库：算法结果含轮次明细 + barge-in 统计 + SPL 口径
        assert len(harness['stub'].result_calls) == 1
        call = harness['stub'].result_calls[0]
        assert call['success'] is True
        assert call['api_config_id'] == 7
        aggregated = call['aggregated']
        algo = aggregated['algorithm_result']
        assert algo['round_count'] == 2
        assert len(algo['rounds']) == 2
        assert algo['barge_in_total'] == 1
        assert algo['barge_in_success'] == 1
        assert 0 < algo['barge_in_success_rate'] <= 1
        # SPL 口径字段（对照测试断言其存在且数值合理）
        assert aggregated['ai_output_rms_dbfs'] is not None
        assert -60 < aggregated['ai_output_rms_dbfs'] < 0
        assert aggregated['ai_output_spl_db'] is not None

        # 打断轮轮次明细
        interrupt_round = algo['rounds'][1]
        assert interrupt_round['barge_in_detected'] is True
        assert interrupt_round['ai_renewed'] is True
        assert interrupt_round['success'] is True

        # ⑤ summary 通道推送
        assert len(harness['publisher'].summaries) == 1
        summary = harness['publisher'].summaries[0]
        assert summary['channel'] == 'realtime_summary'
        assert summary['round_count'] == 2
        assert summary['barge_in_total'] == 1

        # ⑥ 评估完成：入评估队列（异步，不阻塞会话）
        assert len(harness['eval_acl'].calls) == 1
        eval_call = harness['eval_acl'].calls[0]
        assert eval_call['result_id'] == 555
        assert eval_call['algorithm_result']['round_count'] == 2
        assert eval_call['eval_params']['test_type'] == 'api'

    def test_frame_channel_payloads_are_lightweight(self, harness):
        """frame 载荷轻量（不含原始音频字节）"""
        rt_executor = harness['executor']
        rt_executor.execute(task_id=100, tc_rel_id=1,
                            data=harness['data'],
                            case_config=harness['case_config'])
        for frame in harness['publisher'].frames:
            assert frame['channel'] == 'realtime_frame'
            payload = frame.get('payload')
            assert payload is None or 'size' in payload or 'delta' in payload
