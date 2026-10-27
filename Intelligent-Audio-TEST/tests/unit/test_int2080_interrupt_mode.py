# -*- coding: utf-8 -*-
"""INT-2080 打断点模式化：output_duration（基于已返回音频流长度）/ fixed_delay 零回归

覆盖（验收标准）：
- interrupt_mode=fixed_delay（缺省）行为与现状一致（零回归），result 含打断点依据
- interrupt_mode=output_duration：AI 已输出 ≥ interrupt_after_ms 音频时推打断音频
  （mock 预置大块回复场景，按已返回长度触发，非固定延时盲等）
- 大块回复（20s 级）打断点精确可控：触发点时长 = 已返回音频实际时长
- 配置兜底链：round_config → api.meta → 用例 → 全局 → 默认
- 未知 interrupt_mode 回退 fixed_delay（fail-safe，不破坏既有用例）
"""
import base64
import os
import time
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.models.common_enums import RealtimeFrameType, RealtimeRoundMode
from shared.utils.config_manager import config_manager
from api_test_service.core.realtime_session_executor import (
    RealtimeSessionExecutor,
    audio_bytes_to_ms,
)
from api_test_service.domain.services.api_rms_spl_service import ApiRmsSplService
from api_test_service.infrastructure.adapters.transport import RealtimeWSClient
from mock_services.mock_realtime_api import MockRealtimeBehavior, MockRealtimeServer

_RATE_CFG = {'chunk_duration_ms': 20}

# 24000Hz / s16 / mono 下每毫秒音频字节数 = 48（24000 样本/s × 2 字节）
_BYTES_PER_MS = 48


@pytest.fixture
def rt_config():
    """保存/恢复 realtime_session 配置段（config_manager 进程级单例）"""
    section = config_manager.config.get('realtime_session')
    saved = dict(section) if section else {}
    config_manager.config.setdefault('realtime_session', {})
    config_manager.config['realtime_session'].update(_RATE_CFG)
    yield config_manager.config['realtime_session']
    config_manager.config['realtime_session'] = saved


def _chunk_b64():
    return base64.b64encode(b'\x00\x01' * 20).decode('ascii')


@contextmanager
def _mock_rt(**behavior):
    """可参数化的 mock realtime 服务器（每次新建，避免跨测试行为污染）"""
    server = MockRealtimeServer(MockRealtimeBehavior(**behavior))
    server.start()
    try:
        yield server
    finally:
        server.stop()


def _connect_and_trigger_prelude(server):
    """建连接 → 第 1 轮 commit 触发 mock 预置 barge-in 打断事件序列。

    返回已收口第 1 轮响应、事件队列中保留 barge-in 前奏的 client
    （供下一轮打断轮 wait_ai_speaking / barge-in 窗口消费）。
    """
    client = RealtimeWSClient(server.url, chunk_duration_ms=20)
    assert client.connect() is True
    assert client.pre_process() is True
    client.send_audio_chunk(_chunk_b64())
    client.commit_input()
    assert client.wait_ai_complete(start_timeout=5, end_timeout=5) is True
    return client


class RenderStub:
    """RenderService 消费桩：可控 chunk 数，逐 chunk 产出 base64 s16 载荷"""

    def __init__(self, chunk_count=2):
        self.chunk_count = chunk_count

    def stream_round_chunks(self, api_config, round_config, case_config, task_id):
        return iter([
            SimpleNamespace(sequence=i, data_b64=_chunk_b64(), is_last=False,
                            message='')
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


def _make_rt_executor(server, chunk_count=2):
    from api_test_service.core.realtime_session_executor import RealtimeSessionExecutor
    stub = ExecutorStub()
    executor = RealtimeSessionExecutor(stub)
    executor._render_service = RenderStub(chunk_count=chunk_count)
    executor._publisher = SimpleNamespace(
        publish_frame=lambda *a, **k: None,
        publish_summary=lambda *a, **k: None)
    executor._session_registry = SimpleNamespace(
        bind=lambda *a: ('inst', False), release=lambda *a: None)
    executor._spl_repo = SimpleNamespace(get_default_mapping=lambda api_id: None)
    executor._spl_service = ApiRmsSplService(executor._spl_repo)
    api_config = SimpleNamespace(
        id=7, endpoint=server.url, api_endpoints=[], default_max_process=2,
        meta={'vendor': 'openai'}, max_timeout=30, vendor='openai')
    return executor, stub, api_config


def _run_interruption(executor, api_config, client, round_config, case_config):
    client.reset_round_state()
    return executor._execute_interruption_round(
        client, api_config, round_config, 2, 'T1', case_config)


# ──────────────────────────── PCM 字节 → ms 换算 ────────────────────────────

class TestAudioBytesToMs:
    def test_s16_mono_conversion(self):
        # 24000Hz s16 mono：48 字节 = 1ms
        assert audio_bytes_to_ms(_BYTES_PER_MS, 24000) == 1.0
        assert audio_bytes_to_ms(48000, 24000) == 1000.0
        assert audio_bytes_to_ms(96000, 24000) == 2000.0
        assert audio_bytes_to_ms(960000, 24000) == 20000.0   # 20s 级大块

    def test_zero_and_invalid_sample_rate(self):
        assert audio_bytes_to_ms(0, 24000) == 0.0
        assert audio_bytes_to_ms(48000, 0) == 0.0
        assert audio_bytes_to_ms(0, 0) == 0.0

    def test_custom_bytes_per_sample(self):
        assert audio_bytes_to_ms(48000, 24000, bytes_per_sample=1) == 2000.0


# ──────────────────────────── 配置兜底链 ────────────────────────────

class TestResolveInterruptCfg:
    """round_config → api.meta → 用例 → 全局 → 默认（INT-2080）"""

    @staticmethod
    def _executor():
        return object.__new__(RealtimeSessionExecutor)

    def test_defaults_from_global(self, rt_config):
        rt_config.update({'interrupt_mode': 'output_duration', 'interrupt_after_ms': 1500})
        ex = self._executor()
        assert ex._resolve_interrupt_cfg(
            {}, SimpleNamespace(meta={}), {}, 'interrupt_mode', 'fixed_delay') == 'output_duration'
        assert ex._resolve_interrupt_cfg(
            {}, SimpleNamespace(meta={}), {}, 'interrupt_after_ms', 3000) == 1500

    def test_case_overrides_global(self, rt_config):
        rt_config.update({'interrupt_mode': 'fixed_delay', 'interrupt_after_ms': 1000})
        ex = self._executor()
        case = {'interrupt_mode': 'output_duration', 'interrupt_after_ms': 800}
        assert ex._resolve_interrupt_cfg(
            {}, SimpleNamespace(meta={}), case, 'interrupt_mode', 'fixed_delay') == 'output_duration'
        assert ex._resolve_interrupt_cfg(
            {}, SimpleNamespace(meta={}), case, 'interrupt_after_ms', 3000) == 800

    def test_meta_overrides_case(self, rt_config):
        ex = self._executor()
        api = SimpleNamespace(meta={'interrupt_mode': 'output_duration',
                                    'interrupt_after_ms': 2000})
        case = {'interrupt_mode': 'fixed_delay', 'interrupt_after_ms': 800}
        assert ex._resolve_interrupt_cfg(
            {}, api, case, 'interrupt_mode', 'fixed_delay') == 'output_duration'
        assert ex._resolve_interrupt_cfg(
            {}, api, case, 'interrupt_after_ms', 3000) == 2000

    def test_round_overrides_meta(self, rt_config):
        ex = self._executor()
        api = SimpleNamespace(meta={'interrupt_mode': 'fixed_delay'})
        round_cfg = {'interrupt_mode': 'output_duration', 'interrupt_after_ms': 500}
        assert ex._resolve_interrupt_cfg(
            round_cfg, api, {}, 'interrupt_mode', 'fixed_delay') == 'output_duration'
        assert ex._resolve_interrupt_cfg(
            round_cfg, api, {}, 'interrupt_after_ms', 3000) == 500

    def test_interruption_delay_ms_chain(self, rt_config):
        """interruption_delay_ms 保留给 fixed_delay，兜底链与既有语义一致"""
        rt_config.update({'interruption_delay_ms': 999})
        ex = self._executor()
        # round 级 0/空值回退下一级（既有 or 语义）
        assert ex._resolve_interrupt_cfg(
            {'interruption_delay_ms': 0}, SimpleNamespace(meta={}), {},
            'interruption_delay_ms', 1000) == 999
        assert ex._resolve_interrupt_cfg(
            {}, SimpleNamespace(meta={}), {}, 'interruption_delay_ms', 1000) == 999


# ──────────────────────────── output_duration：按已返回长度触发 ────────────────────────────

class TestOutputDurationInterrupt:
    def _base_rt_cfg(self, rt_config):
        rt_config.update({
            'chunk_duration_ms': 20,
            'ai_start_timeout_seconds': 3,
            'ai_complete_timeout_seconds': 3,
        })

    def test_triggers_by_returned_audio_length(self, rt_config):
        """output_duration：AI 已输出 ≥ interrupt_after_ms 音频时推打断音频。

        mock 预置 30 块 × 50ms 连续前奏；阈值 300ms → 触发时长恰为 300ms
        （长度驱动，非 fixed_delay 的 300ms 盲等）。
        """
        self._base_rt_cfg(rt_config)
        with _mock_rt(barge_in=True, barge_in_audio_chunks=30, delta_bytes=2400,
                      barge_in_chunk_interval_ms=5) as server:
            executor, stub, api_config = _make_rt_executor(server, chunk_count=2)
            client = _connect_and_trigger_prelude(server)
            try:
                result = _run_interruption(
                    executor, api_config, client,
                    {'is_interruption': True, 'interrupt_mode': 'output_duration',
                     'interrupt_after_ms': 300}, {})
                assert result['interrupt_mode'] == 'output_duration'
                assert result['interrupt_after_ms'] == 300
                assert result['interrupt_trigger_ms'] == 300
                # 前奏首块 50ms 已被 wait_ai_speaking 消费
                assert result['ai_response_before_interrupt_size'] == 2400
                assert result['barge_in_detected'] is True
                assert result['success'] is True
            finally:
                client.close()

    def test_large_block_20s_trigger_reflects_returned_length(self, rt_config):
        """大块回复（20s 级）：打断点触发时长 = 已返回音频实际时长（960000 字节
        @24000Hz = 20s），立即越过 3000ms 阈值，打断点按长度精确可控。

        interrupt_mode 走全局配置（兜底链）而非 round_config。
        """
        self._base_rt_cfg(rt_config)
        rt_config.update({'interrupt_mode': 'output_duration', 'interrupt_after_ms': 3000})
        with _mock_rt(barge_in=True, barge_in_audio_chunks=1, delta_bytes=960000) as server:
            executor, stub, api_config = _make_rt_executor(server, chunk_count=2)
            client = _connect_and_trigger_prelude(server)
            try:
                result = _run_interruption(
                    executor, api_config, client, {'is_interruption': True}, {})
                assert result['interrupt_mode'] == 'output_duration'   # 全局配置生效
                assert result['interrupt_after_ms'] == 3000
                assert result['interrupt_trigger_ms'] == 20000         # 已返回 20s 音频
                assert result['ai_response_before_interrupt_size'] == 960000
                assert result['barge_in_detected'] is True
                assert result['success'] is True
            finally:
                client.close()

    def test_short_reply_proceeds_when_output_turn_ends(self, rt_config):
        """AI 前奏短于阈值（输出 turn 未达即遇打断信号）：按已有长度提前打断，
        不无限等待（打断点仍有效）。
        """
        self._base_rt_cfg(rt_config)
        with _mock_rt(barge_in=True, barge_in_audio_chunks=1, delta_bytes=2400) as server:
            executor, stub, api_config = _make_rt_executor(server, chunk_count=2)
            client = _connect_and_trigger_prelude(server)
            try:
                result = _run_interruption(
                    executor, api_config, client,
                    {'is_interruption': True, 'interrupt_mode': 'output_duration',
                     'interrupt_after_ms': 3000}, {})
                # 1 块 50ms + 打断信号 → 触发时长为已返回长度（非 3000ms 阈值）
                assert result['interrupt_mode'] == 'output_duration'
                assert result['interrupt_trigger_ms'] == 50
                assert result['barge_in_detected'] is True
                assert result['success'] is True
            finally:
                client.close()


# ──────────────────────────── fixed_delay：缺省零回归 ────────────────────────────

class TestFixedDelayZeroRegression:
    def test_default_mode_matches_prior_behavior(self, rt_config):
        """interrupt_mode 缺省 = fixed_delay：sleep interruption_delay_ms 后推打断，
        result 行为与既有打断轮一致，并新增打断点依据字段。"""
        rt_config.update({
            'chunk_duration_ms': 20,
            'ai_start_timeout_seconds': 3,
            'ai_complete_timeout_seconds': 3,
        })
        with _mock_rt(barge_in=True) as server:
            executor, stub, api_config = _make_rt_executor(server, chunk_count=2)
            client = _connect_and_trigger_prelude(server)
            try:
                result = _run_interruption(
                    executor, api_config, client,
                    {'is_interruption': True, 'interruption_delay_ms': 50}, {})
                assert result['interrupt_mode'] == 'fixed_delay'
                assert result['interrupt_trigger_ms'] == 50
                assert result['interruption_delay_ms'] == 50
                assert result['interrupt_after_ms'] == 3000   # output_duration 备用阈值保留
                assert result['barge_in_detected'] is True
                assert result['success'] is True
            finally:
                client.close()

    def test_unknown_interrupt_mode_falls_back_to_fixed_delay(self, rt_config):
        """未知 interrupt_mode fail-safe 回退 fixed_delay，不破坏既有用例。"""
        rt_config.update({
            'chunk_duration_ms': 20,
            'ai_start_timeout_seconds': 3,
            'ai_complete_timeout_seconds': 3,
        })
        with _mock_rt(barge_in=True) as server:
            executor, stub, api_config = _make_rt_executor(server, chunk_count=2)
            client = _connect_and_trigger_prelude(server)
            try:
                result = _run_interruption(
                    executor, api_config, client,
                    {'is_interruption': True, 'interrupt_mode': 'bogus',
                     'interruption_delay_ms': 50}, {})
                assert result['interrupt_mode'] == 'fixed_delay'
                assert result['interrupt_trigger_ms'] == 50
                assert result['barge_in_detected'] is True
                assert result['success'] is True
            finally:
                client.close()
