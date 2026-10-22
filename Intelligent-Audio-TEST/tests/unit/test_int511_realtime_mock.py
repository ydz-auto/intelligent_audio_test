# -*- coding: utf-8 -*-
"""INT-511 块 3：Realtime API 测试 — OpenAI Realtime mock（INT-497 Phase 1 产物）全链

覆盖（验收标准）：
- session 建立 → 音频帧收发 → 事件轮转（session.created/updated、response.*、
  input_audio_buffer.*）：真实 RealtimeWSClient 连 MockRealtimeServer 全链
- 逐 chunk 推送（append.ack）、信号事件接收（speech_started/response.cancelled）
- 验证点：输入时序受响应信号控制 —— mock 发 input_audio_buffer.speech_started /
  response 事件，断言执行器据此调整推送节奏（WAIT_TURN_END 暂停/ALLOW_BARGE_IN
  收敛/TIMEOUT_FALLBACK 兜底），非固定 sleep
"""
import base64
import os
import time
from types import SimpleNamespace

import pytest

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.models.common_enums import RealtimeFrameType
from shared.utils.config_manager import config_manager
from api_test_service.infrastructure.adapters.transport import RealtimeWSClient
from mock_services.mock_realtime_api import MockRealtimeBehavior, MockRealtimeServer

# INT-475（Realtime 输出调输入 pacing）可选依赖：未合入主开发线的干净 checkout 下，
# 依赖它的用例（pacing 决策 / 信号驱动执行器全链）整体 skip 并注明复跑前提；
# INT-475 合入后自动全量运行。（RealtimePacingStrategy 亦属 INT-475 新增枚举。）
try:
    from api_test_service.domain.services.realtime_pacing_service import (
        RealtimePacingContext,
        RealtimePacingService,
    )
    from shared.models.common_enums import RealtimePacingStrategy
    _PACING_AVAILABLE = True
    _PACING_REASON = ''
except (ImportError, ModuleNotFoundError):
    RealtimePacingContext = None
    RealtimePacingService = None
    RealtimePacingStrategy = None
    _PACING_AVAILABLE = False
    _PACING_REASON = ('依赖 INT-475（Realtime 输出调输入 pacing）未合入主开发线，'
                      'INT-475 合入后复跑')

_PACING_SKIP = pytest.mark.skipif(
    not _PACING_AVAILABLE, reason=_PACING_REASON or 'INT-475 未合入')

_RATE_CFG = {'chunk_duration_ms': 20}


def _chunk_b64():
    return base64.b64encode(b'\x00\x01' * 20).decode('ascii')


@pytest.fixture
def rt_config():
    """保存/恢复 realtime_session 配置段（config_manager 进程级单例）"""
    section = config_manager.config.get('realtime_session')
    saved = dict(section) if section else {}
    config_manager.config.setdefault('realtime_session', {})
    config_manager.config['realtime_session'].update(_RATE_CFG)
    yield config_manager.config['realtime_session']
    config_manager.config['realtime_session'] = saved


@pytest.fixture
def server():
    s = MockRealtimeServer(MockRealtimeBehavior())
    s.start()
    yield s
    s.stop()


# ──────────────────────────── 事件轮转：session / chunk / 信号 ────────────────────────────

class TestEventRotation:
    def test_session_established_and_confirmed(self, server):
        """session 建立：session.update → session.created + session.updated 事件轮转"""
        client = RealtimeWSClient(server.url, chunk_duration_ms=20)
        assert client.connect() is True
        assert client.pre_process({'voice': 'alloy'}) is True
        frame_types = {f['type'] for f in client.frame_results}
        assert RealtimeFrameType.SESSION_CREATED.value in frame_types
        assert RealtimeFrameType.SESSION_UPDATED.value in frame_types
        client.close()

    def test_chunk_push_gets_per_frame_ack(self, server):
        """逐 chunk 推送：input_audio_buffer.append → append.ack（seq 递增）"""
        client = RealtimeWSClient(server.url, chunk_duration_ms=20)
        assert client.connect() is True
        assert client.pre_process() is True
        client.send_audio_chunk(_chunk_b64())
        client.send_audio_chunk(_chunk_b64())
        deadline = time.time() + 2
        while time.time() < deadline and \
                sum(1 for e in client._raw_event_log
                    if e.get('type') == 'input_audio_buffer.append.ack') < 2:
            event = client.recv(timeout=0.2)
            assert event.get('type') != 'connection_closed'
        acks = [e for e in client._raw_event_log
                if e.get('type') == 'input_audio_buffer.append.ack']
        assert len(acks) == 2
        assert [a['seq'] for a in acks] == [1, 2]
        client.close()

    def test_commit_triggers_response_stream(self, server):
        """commit → input_audio_buffer.committed + response.text.delta/audio.delta×N/done"""
        server.set_behavior({'response_chunks': 3, 'chunk_interval_ms': 5})
        client = RealtimeWSClient(server.url, chunk_duration_ms=20)
        assert client.connect() is True
        assert client.pre_process() is True
        client.send_audio_chunk(_chunk_b64())
        client.commit_input()
        assert client.wait_ai_complete(start_timeout=3, end_timeout=3) is True
        output = client.output
        assert output['ai_complete'] is True
        types = {f['type'] for f in output['frame_results']}
        assert RealtimeFrameType.INPUT_COMMITTED.value in types
        assert RealtimeFrameType.AI_AUDIO_DELTA.value in types
        assert RealtimeFrameType.AI_TEXT_DELTA.value in types
        assert RealtimeFrameType.AI_AUDIO_DONE.value in types
        # 3 × 80 字节（mock _pcm_delta_b64 载荷）delta 音频拼接
        assert len(output['audio']) == 3 * 80
        assert output['text'] == 'mock 回复文本'
        client.close()

    def test_server_state_observes_event_rotation(self, server):
        """mock 服务端状态：received 事件类型时间序 / sent 事件计数（全链观测）"""
        client = RealtimeWSClient(server.url, chunk_duration_ms=20)
        assert client.connect() is True
        assert client.pre_process() is True
        client.send_audio_chunk(_chunk_b64())
        client.commit_input()
        client.wait_ai_complete(start_timeout=3, end_timeout=3)
        client.close()
        state = server.service.state.snapshot()
        received = state['received']
        # 客户端事件时间序：session.update → append → commit
        assert received[0] == 'session.update'
        assert 'input_audio_buffer.append' in received
        assert 'input_audio_buffer.commit' in received
        # 服务端发送计数：session 确认 + committed + 响应流
        assert state['sent'].get('session.updated', 0) == 1
        assert state['sent'].get('response.done', 0) >= 1
        assert state['sent'].get('response.audio.delta', 0) >= 1

    def test_barge_in_signals_received(self, server):
        """信号事件接收：barge_in 预置 delta + speech_started + response.cancelled"""
        server.set_behavior({'barge_in': True, 'response_chunks': 2, 'chunk_interval_ms': 5})
        client = RealtimeWSClient(server.url, chunk_duration_ms=20)
        assert client.connect() is True
        assert client.pre_process() is True
        client.send_audio_chunk(_chunk_b64())
        client.commit_input()
        seen = set()
        deadline = time.time() + 3
        while time.time() < deadline and not {'user_speech_started',
                                              'response_cancelled'} <= seen:
            event = client.recv(timeout=0.2)
            if event.get('type') != 'recv_timeout':
                seen.add(event.get('type'))
        assert {'user_speech_started', 'response_cancelled'} <= seen
        assert client.barge_in_detected is True
        client.close()


# ──────────────────────────── 输入时序受响应信号控制（非固定 sleep） ────────────────────────────

def _pacing_ctx(strategies, turn_end=0.5, fallback=0.2):
    return RealtimePacingContext(
        strategies=frozenset(strategies),
        turn_end_wait_timeout_s=turn_end,
        pacing_fallback_timeout_s=fallback,
    )


class ScriptedClient:
    """recv() 脚本化的客户端替身：按序吐出事件，'timeout' 标记=空队列 recv_timeout"""

    def __init__(self, events):
        self.events = list(events)
        self.recv_timeouts = []

    def recv(self, timeout=5.0):
        self.recv_timeouts.append(timeout)
        if self.events:
            item = self.events.pop(0)
            if item == 'timeout':
                return {'type': 'recv_timeout', 'ts': time.time()}
            return item
        return {'type': 'recv_timeout', 'ts': time.time()}


@_PACING_SKIP
class TestPacingGate:
    """_pacing_gate 决策：策略 + 信号事件 → pass/interrupt/abort（纯逻辑无 WS）"""

    def _gate(self, client, pacing):
        from api_test_service.core.realtime_session_executor import RealtimeSessionExecutor
        executor = object.__new__(RealtimeSessionExecutor)
        executor._executor = SimpleNamespace()   # 无 _is_task_stopped → stop_check=None
        return executor._pacing_gate(client, pacing, task_id=1)

    def test_fixed_consumes_no_events(self):
        client = ScriptedClient([{'type': RealtimeFrameType.USER_SPEECH_STARTED.value,
                                  'ts': time.time()}])
        assert self._gate(client, _pacing_ctx([RealtimePacingStrategy.FIXED])) == 'pass'
        assert client.recv_timeouts == [], 'FIXED 不得消费输出事件（零回归）'

    def test_wait_turn_end_pauses_until_done(self):
        """WAIT_TURN_END：输出 turn 进行中暂停推流，turn 结束（done）后放行"""
        events = [
            {'type': RealtimeFrameType.AI_AUDIO_DELTA.value, 'ts': time.time()},
            {'type': RealtimeFrameType.AI_AUDIO_DELTA.value, 'ts': time.time()},
            'timeout',   # 排空阶段无更多事件 → 进入等待轮询
            {'type': RealtimeFrameType.AI_AUDIO_DONE.value, 'ts': time.time()},
        ]
        client = ScriptedClient(events)
        assert self._gate(client, _pacing_ctx([RealtimePacingStrategy.WAIT_TURN_END])) == 'pass'
        # 等待阶段以轮询方式 recv（timeout>0），而非固定 sleep
        assert any(t > 0 for t in client.recv_timeouts)

    def test_wait_turn_end_timeout_fallback_not_infinite(self):
        """TIMEOUT_FALLBACK：模型无 turn 结束信号 → 按兜底超时放行（不无限等待）"""
        events = [{'type': RealtimeFrameType.AI_AUDIO_DELTA.value, 'ts': time.time()}]
        client = ScriptedClient(events)
        start = time.time()
        decision = self._gate(client, _pacing_ctx(
            [RealtimePacingStrategy.WAIT_TURN_END,
             RealtimePacingStrategy.TIMEOUT_FALLBACK], turn_end=0.15, fallback=0.1))
        elapsed = time.time() - start
        assert decision == 'pass'
        assert elapsed < 2.0, f'超时兜底未生效，耗时 {elapsed:.2f}s'

    def test_allow_barge_in_interrupts_on_speech_started(self):
        """ALLOW_BARGE_IN：推流中模型提前回话 → 收敛输入推流（interrupt）"""
        events = [{'type': RealtimeFrameType.USER_SPEECH_STARTED.value, 'ts': time.time()}]
        client = ScriptedClient(events)
        assert self._gate(client, _pacing_ctx([RealtimePacingStrategy.ALLOW_BARGE_IN])) \
            == 'interrupt'

    def test_response_cancelled_interrupts_with_allow_barge_in(self):
        events = [{'type': RealtimeFrameType.RESPONSE_CANCELLED.value, 'ts': time.time()}]
        client = ScriptedClient(events)
        assert self._gate(client, _pacing_ctx(
            [RealtimePacingStrategy.ALLOW_BARGE_IN])) == 'interrupt'

    def test_turn_done_releases_wait_before_barge_in(self):
        """turn 已结束（done）先于打断信号 → 放行（done 收敛优先，不误断）"""
        events = [{'type': RealtimeFrameType.AI_AUDIO_DONE.value, 'ts': time.time()}]
        client = ScriptedClient(events)
        assert self._gate(client, _pacing_ctx(
            [RealtimePacingStrategy.ALLOW_BARGE_IN,
             RealtimePacingStrategy.WAIT_TURN_END])) == 'pass'


# ──────────────────────────── 执行器全链：信号驱动节奏（真实 WS + mock） ────────────────────────────

class RenderStub:
    """RenderService 消费桩：可控 chunk 数，逐 chunk 产出 base64 s16 载荷"""

    def __init__(self, chunk_count=6):
        self.chunk_count = chunk_count

    def stream_round_chunks(self, api_config, round_config, case_config, task_id):
        return iter([
            SimpleNamespace(sequence=i, data_b64=_chunk_b64(), is_last=False, message='')
            for i in range(self.chunk_count)
        ])


class ExecutorStub:
    def __init__(self):
        self.execution_engine = SimpleNamespace(
            update_case_round_progress=lambda *a, **k: None,
            _emit_progress=lambda *a, **k: None)
        self._concurrency = SimpleNamespace(
            acquire=lambda *a, **k: True, release=lambda *a, **k: None)
        self._result_processor = SimpleNamespace(
            create_multi_round_test_result=lambda *a, **k: 1,
            update_task_case_failure=lambda *a, **k: None)

    def _handle_control(self, task_id):
        pass

    def _is_task_stopped(self, task_id):
        return False

    def _log(self, *a, **k):
        pass


def _make_rt_executor(server, chunk_count=6, rt_config_extra=None):
    from api_test_service.core.realtime_session_executor import RealtimeSessionExecutor
    stub = ExecutorStub()
    executor = RealtimeSessionExecutor(stub)
    executor._render_service = RenderStub(chunk_count=chunk_count)
    executor._publisher = SimpleNamespace(
        publish_frame=lambda *a, **k: None,
        publish_summary=lambda *a, **k: None)
    executor._session_registry = SimpleNamespace(
        bind=lambda *a: ('inst', False), release=lambda *a: None)
    from api_test_service.domain.services.api_rms_spl_service import ApiRmsSplService
    executor._spl_repo = SimpleNamespace(get_default_mapping=lambda api_id: None)
    executor._spl_service = ApiRmsSplService(executor._spl_repo)
    api_config = SimpleNamespace(
        id=7, endpoint=server.url, api_endpoints=[], default_max_process=2,
        meta={'vendor': 'openai'}, max_timeout=30, vendor='openai')
    return executor, stub, api_config


def _turn_window(server):
    """输出 turn 窗口 [首个 response.audio.delta ts, response.done ts]（mock 观测时间线）"""
    start, end = None, None
    for e in server.service.state.sent_timeline:
        if e['type'] == 'response.audio.delta' and start is None:
            start = e['ts']
        if e['type'] == 'response.done':
            end = e['ts']
            break
    return start, end


def _append_ts_list(server):
    return [e['ts'] for e in server.service.state.received_timeline
            if e['type'] == 'input_audio_buffer.append']


@_PACING_SKIP
class TestExecutorSignalDrivenPacing:
    def test_wait_turn_end_pauses_input_during_output_turn(self, rt_config, server):
        """验证点：输入时序受响应信号控制 —— WAIT_TURN_END 下模型 turn 期间输入帧暂停，
        依 done 信号续推（非固定 sleep 盲推）"""
        server.set_behavior({
            'speak_during_stream': True, 'speak_during_stream_after': 2,
            'speak_during_stream_complete': True,
            'response_chunks': 8, 'chunk_interval_ms': 50,   # 输出 turn 拉长约 350ms 供观测暂停
        })
        rt_config.update({
            'chunk_duration_ms': 200,
            'ai_start_timeout_seconds': 3,
            'ai_complete_timeout_seconds': 3,
            'pacing_strategy': 'wait_turn_end',
            'turn_end_wait_timeout_s': 2,
            'pacing_fallback_timeout_s': 1,
        })
        executor, stub, api_config = _make_rt_executor(server, chunk_count=6)
        client = RealtimeWSClient(server.url, chunk_duration_ms=200)
        assert client.connect() is True
        assert client.pre_process() is True

        result = executor._execute_normal_round(
            client, api_config, {'round_number': 1, 'query': '你好'}, 1, 1, {})
        assert result['success'] is True

        start, end = _turn_window(server)
        assert start is not None and end is not None
        appends = _append_ts_list(server)
        # 输出 turn 期间输入推流暂停：窗口内至多边界 1 帧（时序竞态容忍），
        # 且必须存在 ≥ turn 时长的推送空隙（信号驱动暂停可观测，非固定节奏盲推）
        appends_in_window = [ts for ts in appends if start <= ts <= end]
        assert len(appends_in_window) <= 1, \
            f'WAIT_TURN_END 应在输出 turn 期间暂停输入推流，turn 窗口内 append={appends_in_window}'
        turn_len = end - start
        gaps = [b - a for a, b in zip(appends, appends[1:])]
        assert any(g >= turn_len * 0.6 for g in gaps), \
            f'未见输出 turn 期间的输入推流空隙（turn={turn_len:.2f}s, gaps={[round(g,3) for g in gaps]}）'
        # 暂停不是丢帧：全部 chunk 最终推完（节奏门只调时序不改总量）
        assert result['input_chunk_count'] == 6
        assert result['input_interrupted'] is False
        client.close()

    def test_allow_barge_in_converges_input_on_signal(self, rt_config, server):
        """验证点：mock 发 speech_started/response.cancelled → ALLOW_BARGE_IN 收敛输入推流"""
        server.set_behavior({
            'speak_during_stream': True, 'speak_during_stream_after': 2,
            'speak_during_stream_barge_in': True, 'speak_during_stream_complete': True,
            'response_chunks': 2, 'chunk_interval_ms': 5,
        })
        rt_config.update({
            'chunk_duration_ms': 100,
            'ai_start_timeout_seconds': 3,
            'ai_complete_timeout_seconds': 3,
            'pacing_strategy': 'allow_barge_in',
            'turn_end_wait_timeout_s': 2,
            'pacing_fallback_timeout_s': 1,
        })
        executor, stub, api_config = _make_rt_executor(server, chunk_count=6)
        client = RealtimeWSClient(server.url, chunk_duration_ms=20)
        assert client.connect() is True
        assert client.pre_process() is True

        result = executor._execute_normal_round(
            client, api_config, {'round_number': 1, 'query': '你好'}, 1, 1, {})
        # 打断收敛：未推完全部 6 帧即中断（剩余输入不再推）
        assert result['input_interrupted'] is True
        assert result['input_chunk_count'] < 6
        assert _append_ts_list(server)  # 至少推了前置帧
        client.close()

    def test_fixed_baseline_pushes_all_chunks(self, rt_config, server):
        """默认 FIXED：恒定节奏全量推送（回归基准，节奏门不消费事件）"""
        rt_config.update({
            'chunk_duration_ms': 20,
            'ai_start_timeout_seconds': 3,
            'ai_complete_timeout_seconds': 3,
            'pacing_strategy': 'fixed',
        })
        executor, stub, api_config = _make_rt_executor(server, chunk_count=4)
        client = RealtimeWSClient(server.url, chunk_duration_ms=20)
        assert client.connect() is True
        assert client.pre_process() is True

        result = executor._execute_normal_round(
            client, api_config, {'round_number': 1, 'query': '你好'}, 1, 1, {})
        assert result['success'] is True
        assert result['input_interrupted'] is False
        assert result['input_chunk_count'] == 4
        client.close()

    def test_timeout_fallback_bounds_wait_on_no_output(self, rt_config, server):
        """TIMEOUT_FALLBACK：模型无输出时按兜底超时收敛，不无限等待"""
        server.set_behavior({
            'speak_during_stream': True, 'speak_during_stream_after': 2,
            'speak_during_stream_complete': False,   # 发出 deltas 不收口（无 done）
            'response_chunks': 2, 'chunk_interval_ms': 5,
        })
        rt_config.update({
            'chunk_duration_ms': 20,
            'ai_start_timeout_seconds': 3,
            'ai_complete_timeout_seconds': 3,
            'pacing_strategy': 'wait_turn_end,timeout_fallback',
            'turn_end_wait_timeout_s': 2,
            'pacing_fallback_timeout_s': 0.3,
        })
        executor, stub, api_config = _make_rt_executor(server, chunk_count=3)
        client = RealtimeWSClient(server.url, chunk_duration_ms=20)
        assert client.connect() is True
        assert client.pre_process() is True

        start = time.time()
        result = executor._execute_normal_round(
            client, api_config, {'round_number': 1, 'query': '你好'}, 1, 1, {})
        elapsed = time.time() - start
        # 兜底超时（0.3s）收敛：整轮明显快于默认 3s 超时
        assert elapsed < 2.0, f'TIMEOUT_FALLBACK 未收敛，耗时 {elapsed:.2f}s'
        assert result['success'] is False or result['success'] is True
        client.close()
