# -*- coding: utf-8 -*-
"""INT-475 Realtime 输出调输入节奏集成测试（M1 核心 + M3 验证）

真实链路：
RealtimeSessionExecutor（真实执行器）→ RealtimeWSClient（真实 WS 客户端）
  → MockRealtimeServer（mock_services 独立替身，新增 speak_during_stream 行为注入）
  → RenderService 消费桩 → frame 双通道桩 → 评估 ACL 桩

覆盖（对照 INT-475 验收标准）：
1. 默认 FIXED 恒定节奏：全量 chunk 推送，与既有 int61/int137 路径一致（零回归）
2. WAIT_TURN_END：模型长回复时输入帧推送暂停至输出 turn 结束，时序断言通过
   （输出信号经 RealtimeWSClient 内部事件队列 + recv() 轮询实例内回流）
3. ALLOW_BARGE_IN：输入推流中模型提前回话/打断 → 收敛输入推流
4. TIMEOUT_FALLBACK：模型无输出/无 turn 结束时按配置超时兜底，不无限等待
5. case_config['pacing'] 覆盖全局配置生效
"""
import base64
import os
import time
from types import SimpleNamespace

import pytest

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.utils.config_manager import config_manager
from shared.models.common_enums import DeviceType
from mock_services.mock_realtime_api import MockRealtimeBehavior, MockRealtimeServer
import api_test_service.core.realtime_session_executor as rt_executor_module
from api_test_service.core.realtime_session_executor import RealtimeSessionExecutor
from api_test_service.infrastructure.acl import AlgorithmQueryAclRepositoryImpl


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
    def __init__(self):
        self.frames = []
        self.summaries = []

    def publish_frame(self, task_id, test_case_id, session_id, round_number,
                      seq, frame):
        self.frames.append({'session_id': session_id, 'seq': seq, **frame})

    def publish_summary(self, task_id, test_case_id, session_id, summary):
        self.summaries.append(summary)


class EvaluationAclStub:
    def __init__(self):
        self.calls = []

    def submit_evaluate_case(self, task_id, result_id, test_case_id,
                             algorithm_result, eval_params):
        self.calls.append({'result_id': result_id, 'algorithm_result': algorithm_result})
        return True


class SplRepoStub:
    def get_default_mapping(self, api_id):
        return None

    def get_mapping(self, mapping_id):
        return None


class RenderStub:
    """RenderService 消费桩：可控 chunk 数，逐 chunk 产出 s16 载荷"""

    def __init__(self, chunk_count=8):
        self.chunk_count = chunk_count
        self.stream_calls = []

    def stream_round_chunks(self, api_config, round_config, case_config, task_id):
        self.stream_calls.append(task_id)
        chunk_b64 = base64.b64encode(b'\x00\x01' * 20).decode('ascii')
        return iter([
            SimpleNamespace(sequence=i, data_b64=chunk_b64,
                            is_last=i == self.chunk_count - 1, message='')
            for i in range(self.chunk_count)
        ])


# ── 夹具 ──────────────────────────────────────────────────

@pytest.fixture
def rt_config():
    """保存/恢复 realtime_session 配置段（config_manager 进程级单例，互不污染）"""
    section = config_manager.config.get('realtime_session')
    saved = dict(section) if section else {}
    config_manager.config.setdefault('realtime_session', {})
    yield config_manager.config['realtime_session']
    config_manager.config['realtime_session'] = saved


@pytest.fixture
def harness(rt_config, monkeypatch):
    server = MockRealtimeServer(MockRealtimeBehavior())
    server.start()
    # 默认测试配置：快节奏 + 短超时（配置化，无魔法数字硬编码进断言之外的执行路径）
    rt_config.update({
        'chunk_duration_ms': 30,
        'ai_start_timeout_seconds': 2,
        'ai_complete_timeout_seconds': 2,
        'pacing_strategy': 'fixed',
        'turn_end_wait_timeout_s': 1,
        'pacing_fallback_timeout_s': 0.3,
    })

    publisher = PublisherStub()
    eval_acl = EvaluationAclStub()
    rt_executor_module._evaluation_acl = eval_acl
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
    from api_test_service.domain.services.api_rms_spl_service import ApiRmsSplService
    rt_executor._spl_repo = SplRepoStub()
    rt_executor._spl_service = ApiRmsSplService(rt_executor._spl_repo)
    rt_executor._render_service = RenderStub(chunk_count=8)

    api_config = SimpleNamespace(
        id=7, endpoint=server.url, api_endpoints=[],
        default_max_process=2, meta={'vendor': 'openai'}, max_timeout=30,
        vendor='openai')
    data = {
        'task_id': 4750, 'tc_rel_id': 1, 'test_case_id': 47501,
        'case_name': 'rt-pacing',
        'algorithm_type': 'voice_llm',
        'device_type': DeviceType.WEBSOCKET_API.value,
        'api_configs': [api_config],
        'audio': {}, 'api_specific_config': {},
        'total_audio_duration': 0.24, 'case_algorithm_params': {}}
    case_config = {'rounds': [
        {'round_number': 1, 'audio_id': 1, 'spl': 65, 'query': '你好'},
    ]}
    yield {
        'executor': rt_executor, 'stub': executor_stub,
        'publisher': publisher, 'eval_acl': eval_acl,
        'server': server, 'api_config': api_config,
        'data': data, 'case_config': case_config,
        'rt_config': rt_config,
    }
    server.stop()
    from shared.models.database import remove_db_session
    remove_db_session()


def _last_round(h):
    """最近一次落库的轮次明细（aggregated.algorithm_result.rounds[0]）"""
    call = h['stub'].result_calls[-1]
    return call['aggregated']['algorithm_result']['rounds'][0]


def _turn_window(server):
    """输出 turn 窗口 [首个 audio.delta 发出 ts, response.done 发出 ts]（mock 观测时间线）"""
    start, end = None, None
    for e in server.service.state.sent_timeline:
        if e['type'] == 'response.audio.delta' and start is None:
            start = e['ts']
        if e['type'] == 'response.done':
            end = e['ts']
            break
    return start, end


def _appends_in_window(server, start, end):
    return [e for e in server.service.state.received_timeline
            if e['type'] == 'input_audio_buffer.append' and start <= e['ts'] <= end]


def _append_count(server):
    return server.service.state.received.count('input_audio_buffer.append')


# ── 验收标准 ──────────────────────────────────────────────

class TestMockSpeakDuringStream:
    """M3 mock 行为注入扩展契约（mock_realtime_api.speak_during_stream，经真实 WS 客户端）"""

    def _connect(self, harness):
        from api_test_service.infrastructure.adapters.transport import RealtimeWSClient
        client = RealtimeWSClient(harness['server'].url, chunk_duration_ms=20)
        assert client.connect() is True
        assert client.pre_process() is True
        return client

    def test_fires_during_stream_before_commit(self, harness):
        """提前回话在 commit 前（输入推流中）即触发，并正常收口 done"""
        harness['server'].set_behavior({
            'speak_during_stream': True, 'speak_during_stream_after': 1,
            'speak_during_stream_complete': True,
            'response_chunks': 2, 'chunk_interval_ms': 5,
        })
        client = self._connect(harness)
        chunk_b64 = base64.b64encode(b'\x00\x01' * 20).decode('ascii')
        client.send_audio_chunk(chunk_b64)   # 第 1 帧即触发提前回话
        deadline = time.time() + 3
        seen_delta = seen_done = False
        while time.time() < deadline:
            event = client.recv(timeout=0.2)
            if event.get('type') == 'ai_audio_delta':
                seen_delta = True
            if event.get('type') == 'ai_audio_done':
                seen_done = True
                break
        assert seen_delta and seen_done
        # 提交后不重复响应（同一输入周期已回复），ai_complete 仍为真
        client.commit_input()
        assert client.output['ai_complete'] is True
        client.close()

    def test_complete_false_omits_done(self, harness):
        """speak_during_stream_complete=False：提前回话发出 deltas 但不收口（超时兜底验收用）"""
        harness['server'].set_behavior({
            'speak_during_stream': True, 'speak_during_stream_after': 1,
            'speak_during_stream_complete': False,
            'response_chunks': 2, 'chunk_interval_ms': 5,
        })
        client = self._connect(harness)
        client.send_audio_chunk(base64.b64encode(b'\x00\x01' * 20).decode('ascii'))
        deadline = time.time() + 3
        seen_delta = False
        while time.time() < deadline:
            event = client.recv(timeout=0.2)
            if event.get('type') == 'ai_audio_delta':
                seen_delta = True
                break
        assert seen_delta
        # 无 done：等待不收敛完成
        assert client.wait_ai_complete(start_timeout=0.5, end_timeout=0.5) is False
        client.close()

    def test_barge_in_signals_during_stream(self, harness):
        """speak_during_stream_barge_in：提前回话携带打断信号（ALLOW_BARGE_IN 验收用）"""
        harness['server'].set_behavior({
            'speak_during_stream': True, 'speak_during_stream_after': 1,
            'speak_during_stream_barge_in': True, 'speak_during_stream_complete': True,
            'response_chunks': 1, 'chunk_interval_ms': 5,
        })
        client = self._connect(harness)
        client.send_audio_chunk(base64.b64encode(b'\x00\x01' * 20).decode('ascii'))
        deadline = time.time() + 3
        seen = set()
        while time.time() < deadline and not {'user_speech_started',
                                              'response_cancelled'} <= seen:
            event = client.recv(timeout=0.2)
            seen.add(event.get('type'))
        assert {'user_speech_started', 'response_cancelled'} <= seen
        assert client.barge_in_detected is True
        client.close()


class TestFixedBaseline:
    def test_default_fixed_pushes_all_chunks(self, harness):
        """默认 FIXED 恒定节奏：全量 chunk 推送 + commit，轮次成功（零回归基准）"""
        ok = harness['executor'].execute(task_id=4750, tc_rel_id=1,
                                         data=harness['data'],
                                         case_config=harness['case_config'])
        assert ok is True
        assert _append_count(harness['server']) == 8
        assert harness['server'].service.state.received.count('input_audio_buffer.commit') == 1
        r = _last_round(harness)
        assert r['success'] is True
        assert r['input_interrupted'] is False
        assert r['input_chunk_count'] == 8

    def test_case_config_pacing_override_global(self, harness):
        """case_config['pacing'] 覆盖全局 fixed → allow_barge_in 生效（打断收敛）"""
        harness['server'].set_behavior({
            'speak_during_stream': True, 'speak_during_stream_after': 2,
            'speak_during_stream_barge_in': True, 'speak_during_stream_complete': True,
            'response_chunks': 3, 'chunk_interval_ms': 5,
        })
        harness['case_config']['pacing'] = {'pacing_strategy': 'allow_barge_in'}
        ok = harness['executor'].execute(task_id=4750, tc_rel_id=1,
                                         data=harness['data'],
                                         case_config=harness['case_config'])
        assert ok is True
        r = _last_round(harness)
        assert r['input_interrupted'] is True          # 打断收敛输入推流
        assert r['input_chunk_count'] < 8              # 剩余输入不再推
        assert r['success'] is True                    # 模型提前回话且收口


class TestWaitTurnEnd:
    def test_pauses_during_output_turn_then_resumes(self, harness):
        """WAIT_TURN_END：模型长回复期间输入帧暂停推送，turn 结束后续推（时序断言）"""
        harness['rt_config']['pacing_strategy'] = 'wait_turn_end'
        harness['server'].set_behavior({
            'speak_during_stream': True, 'speak_during_stream_after': 1,
            'speak_during_stream_complete': True,
            'response_chunks': 5, 'chunk_interval_ms': 40,
        })
        ok = harness['executor'].execute(task_id=4750, tc_rel_id=1,
                                         data=harness['data'],
                                         case_config=harness['case_config'])
        assert ok is True
        r = _last_round(harness)
        assert r['success'] is True
        # 全量输入最终都推完（暂停只是延后，不丢弃）
        assert _append_count(harness['server']) == 8

        start, end = _turn_window(harness['server'])
        assert start is not None and end is not None and end > start
        # 时序断言：输出 turn 窗口 [首个 delta, done] 内输入帧推送明显少于恒定节奏。
        # 允许节奏门在首帧检测前滑入的 1~2 帧瞬时（chunk 粒度暂停），恒定节奏下
        # 同一窗口（~160ms @30ms/chunk）会推约 5 帧 —— ≤2 证明暂停生效。
        in_window = _appends_in_window(harness['server'], start, end)
        assert len(in_window) <= 2
        # 暂停是延后而非丢弃：turn 结束后续推，全量输入最终到达
        assert _append_count(harness['server']) == 8


class TestAllowBargeIn:
    def test_interrupts_input_on_early_response(self, harness):
        """ALLOW_BARGE_IN：输入推流中模型提前回话/打断 → 收敛输入推流"""
        harness['rt_config']['pacing_strategy'] = 'allow_barge_in'
        harness['server'].set_behavior({
            'speak_during_stream': True, 'speak_during_stream_after': 2,
            'speak_during_stream_barge_in': True, 'speak_during_stream_complete': True,
            'response_chunks': 3, 'chunk_interval_ms': 5,
        })
        ok = harness['executor'].execute(task_id=4750, tc_rel_id=1,
                                         data=harness['data'],
                                         case_config=harness['case_config'])
        assert ok is True
        r = _last_round(harness)
        assert r['input_interrupted'] is True
        assert r['input_chunk_count'] < 8              # 打断信号到达后剩余输入不再推
        # 打断信号经内部事件队列回流：frame 通道可见（产出链路不受节奏影响）
        frame_types = [f['type'] for f in harness['publisher'].frames]
        assert 'user_speech_started' in frame_types
        assert 'response_cancelled' in frame_types


class TestTimeoutFallback:
    def test_converges_when_turn_never_ends(self, harness):
        """TIMEOUT_FALLBACK：模型长回复未收口（无 done）→ 按配置超时兜底，不无限等待"""
        harness['rt_config']['pacing_strategy'] = ['wait_turn_end', 'timeout_fallback']
        harness['rt_config']['pacing_fallback_timeout_s'] = 0.3
        harness['server'].set_behavior({
            'speak_during_stream': True, 'speak_during_stream_after': 1,
            'speak_during_stream_complete': False,   # 长回复未收口
            'response_chunks': 3, 'chunk_interval_ms': 10,
        })
        started = time.monotonic()
        ok = harness['executor'].execute(task_id=4750, tc_rel_id=1,
                                         data=harness['data'],
                                         case_config=harness['case_config'])
        elapsed = time.monotonic() - started
        # 兜底超时 0.3s 生效：整轮收敛远小于默认 60s（不无限等待）
        assert elapsed < 5
        assert ok is True   # execute 恒 True（多轮会话维度），轮次成败看 round
        r = _last_round(harness)
        assert r['success'] is False
        assert 'AI 回复未在超时内完成' in (r['error'] or '')

    def test_silent_model_no_infinite_wait(self, harness):
        """TIMEOUT_FALLBACK：模型全程无输出 → wait_ai_complete 按兜底超时收敛"""
        harness['rt_config']['pacing_strategy'] = ['wait_turn_end', 'timeout_fallback']
        harness['rt_config']['pacing_fallback_timeout_s'] = 0.3
        harness['server'].set_behavior({'auto_response': False})   # 模型沉默
        started = time.monotonic()
        ok = harness['executor'].execute(task_id=4750, tc_rel_id=1,
                                         data=harness['data'],
                                         case_config=harness['case_config'])
        elapsed = time.monotonic() - started
        assert elapsed < 5
        assert ok is True
        r = _last_round(harness)
        assert r['success'] is False
