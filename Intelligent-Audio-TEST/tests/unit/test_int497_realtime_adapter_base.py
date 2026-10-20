# -*- coding: utf-8 -*-
"""INT-497 Realtime 协议级 base / OpenAI 品牌适配器生命周期单测（验收标准 3）

对进程内 mock Realtime API（mock_services/mock_realtime_api.py，INT-137 契约）
验证 OpenAIRealtimeAdapter（继承 RealtimeAdapterBase）三级生命周期：
    initialize → pre_process → send → recv → post_process → teardown

覆盖：
- 生命周期六钩子对 mock 跑通：WS 建立、session.update 确认、音频帧收发、
  事件流转（ai_audio_delta/done/text_delta）、输出聚合
- 注入路径：first_delta_delay_ms（首帧延迟）、disconnect_after_events（中途断连
  收敛 connection_closed）、protocol_error_on_event（协议错误 → pre_process 失败）
- RealtimeWSClient 同形方法面：connect / close / send_audio_chunk / commit_input /
  mark_commit / wait_ai_speaking / wait_ai_complete / output / connected
- 三级体系：OpenAIRealtimeAdapter(RealtimeAdapterBase(ApiVendorAdapter))，注册键
  (REALTIME, OPENAI)；HTTP 执行契约（execute/render_request_parts）明确拒绝
"""
import base64
import os
import time

import pytest

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.models.common_enums import (
    AdapterProtocol,
    AdapterVendor,
    RealtimeFrameType,
    VendorAdapterType,
)
from api_test_service.domain.ports import ApiVendorAdapter
from api_test_service.infrastructure.adapters import vendor_adapter_registry
from api_test_service.infrastructure.adapters.protocol.realtime_adapter_base import (
    RealtimeAdapterBase,
)
from api_test_service.infrastructure.adapters.vendors.openai_realtime_adapter import (
    OpenAIRealtimeAdapter,
)
from mock_services.mock_realtime_api import MockRealtimeBehavior, MockRealtimeServer


@pytest.fixture()
def mock_rt():
    server = MockRealtimeServer(MockRealtimeBehavior())
    server.start()
    try:
        yield server
    finally:
        server.stop()
        server.service.state.reset()
        server.service.behavior = MockRealtimeBehavior()


def _make_api_config(url, meta=None, vendor='openai'):
    from types import SimpleNamespace
    return SimpleNamespace(
        id=7, endpoint=url, api_endpoints=[], meta=dict(meta or {}),
        max_timeout=30, vendor=vendor)


def _chunk_b64(n_bytes=80):
    return base64.b64encode(b'\x00\x01' * (n_bytes // 2)).decode('ascii')


# ──────────────────────────── 三级体系 ────────────────────────────

class TestThreeTierHierarchy:
    def test_openai_realtime_inherits_base_which_is_port_subclass(self):
        assert issubclass(RealtimeAdapterBase, ApiVendorAdapter)
        assert issubclass(OpenAIRealtimeAdapter, RealtimeAdapterBase)

    def test_protocol_vendor_class_attrs(self):
        assert RealtimeAdapterBase.protocol is AdapterProtocol.REALTIME
        assert RealtimeAdapterBase.vendor is AdapterVendor.ANY
        assert OpenAIRealtimeAdapter.protocol is AdapterProtocol.REALTIME
        assert OpenAIRealtimeAdapter.vendor is AdapterVendor.OPENAI
        assert OpenAIRealtimeAdapter.adapter_type is VendorAdapterType.OPENAI_REALTIME

    def test_registered_in_global_registry(self):
        assert vendor_adapter_registry.resolve(
            AdapterProtocol.REALTIME, AdapterVendor.OPENAI) is OpenAIRealtimeAdapter
        assert vendor_adapter_registry.resolve(
            AdapterProtocol.REALTIME, AdapterVendor.ANY) is RealtimeAdapterBase

    def test_http_execute_contract_rejected(self):
        """Realtime 适配器不经 HTTP execute/render_request_parts（执行面不同）"""
        adapter = OpenAIRealtimeAdapter(None, case_config={})
        with pytest.raises(NotImplementedError, match='Realtime'):
            adapter.render_request_parts({})
        with pytest.raises(NotImplementedError, match='Realtime'):
            adapter.execute({})


# ──────────────────────────── 生命周期 ────────────────────────────

class TestLifecycle:
    def test_initialize_pre_process_send_recv_post_process_teardown(self, mock_rt):
        adapter = OpenAIRealtimeAdapter(
            _make_api_config(mock_rt.url), case_config={}, endpoint=mock_rt.url)
        try:
            # initialize：WS 握手
            assert adapter.initialize() is True
            assert adapter.connected is True
            # pre_process：session.update → session.updated 确认
            assert adapter.pre_process({'voice': 'alloy'}) is True
            # send：逐帧推送音频 + commit（recv 流转事件）
            chunk = _chunk_b64()
            for _ in range(3):
                adapter.send_audio_chunk(chunk)
            adapter.commit_input()
            # recv：事件轮转（首帧 delta → done 收口）
            assert adapter.wait_ai_complete(start_timeout=5, end_timeout=5) is True
            # post_process：聚合轮次/会话输出
            output = adapter.post_process()
            assert output['ai_complete'] is True
            assert output['audio'] == b'\x01\x02' * 40 * 3
            assert output['text'] == 'mock 回复文本'
            assert output['latency_ms'] is not None
            types = {f['type'] for f in output['frame_results']}
            assert RealtimeFrameType.SESSION_CREATED.value in types
            assert RealtimeFrameType.SESSION_UPDATED.value in types
            assert RealtimeFrameType.AI_AUDIO_DELTA.value in types
            assert RealtimeFrameType.AI_AUDIO_DONE.value in types
            assert RealtimeFrameType.AI_TEXT_DELTA.value in types
            # 服务端观测：会话建立 + 音频帧收发 + commit
            assert mock_rt.service.state.received[0] == 'session.update'
            assert mock_rt.service.state.received.count(
                'input_audio_buffer.append') == 3
            assert 'input_audio_buffer.commit' in mock_rt.service.state.received
        finally:
            # teardown：关连接、释放会话绑定（幂等）
            adapter.teardown()
        assert adapter.connected is False
        adapter.teardown()  # 幂等

    def test_recv_timeout_semantics(self, mock_rt):
        adapter = OpenAIRealtimeAdapter(
            _make_api_config(mock_rt.url), case_config={}, endpoint=mock_rt.url)
        adapter.initialize()
        try:
            event = adapter.recv(timeout=0.2)
            assert event['type'] == 'recv_timeout'
        finally:
            adapter.close()

    def test_send_is_single_chunk_alias(self, mock_rt):
        """send（Port 生命周期钩子）= send_audio_chunk 单帧粒度"""
        adapter = OpenAIRealtimeAdapter(
            _make_api_config(mock_rt.url), case_config={}, endpoint=mock_rt.url)
        adapter.initialize()
        try:
            adapter.send(_chunk_b64())
            adapter.commit_input()
            assert adapter.wait_ai_complete(start_timeout=5, end_timeout=5) is True
            assert mock_rt.service.state.received.count(
                'input_audio_buffer.append') == 1
        finally:
            adapter.teardown()

    def test_connect_failure_returns_false(self):
        adapter = OpenAIRealtimeAdapter(
            _make_api_config('ws://127.0.0.1:1'), case_config={},
            endpoint='ws://127.0.0.1:1')
        assert adapter.connect() is False
        adapter.close()


# ──────────────────────────── 注入路径（超时/断连/协议错误） ────────────────────────────

class TestInjectionPaths:
    def test_first_delta_delay_injection(self, mock_rt):
        """首帧延迟注入：first_delta_delay_ms 生效于 commit → 首帧延迟口径"""
        mock_rt.set_behavior({'first_delta_delay_ms': 400})
        adapter = OpenAIRealtimeAdapter(
            _make_api_config(mock_rt.url), case_config={}, endpoint=mock_rt.url)
        adapter.initialize()
        try:
            assert adapter.pre_process() is True
            adapter.commit_input()
            assert adapter.wait_ai_complete(start_timeout=10, end_timeout=5) is True
            assert adapter.output['latency_ms'] >= 350
        finally:
            adapter.teardown()

    def test_disconnect_injection_converges_connection_closed(self, mock_rt):
        """中途断连注入：disconnect_after_events 后连接收敛 connection_closed，
        wait_ai_complete 判失败"""
        mock_rt.set_behavior({'disconnect_after_events': 2})
        adapter = OpenAIRealtimeAdapter(
            _make_api_config(mock_rt.url), case_config={}, endpoint=mock_rt.url)
        adapter.initialize()
        try:
            assert adapter.pre_process() is True
            adapter.send_audio_chunk(_chunk_b64())
            closed = False
            end = time.time() + 5
            while time.time() < end:
                event = adapter.recv(timeout=1)
                if event.get('type') == 'connection_closed':
                    closed = True
                    break
            assert closed, '服务端断连后适配器未收敛 connection_closed'
            assert adapter.wait_ai_complete(start_timeout=2, end_timeout=2) is False
        finally:
            adapter.teardown()

    def test_protocol_error_injection_fails_pre_process(self, mock_rt):
        """协议错误注入：session.update 回 error → pre_process 收敛失败"""
        mock_rt.set_behavior({'protocol_error_on_event': 'session.update'})
        adapter = OpenAIRealtimeAdapter(
            _make_api_config(mock_rt.url), case_config={}, endpoint=mock_rt.url)
        adapter.initialize()
        try:
            assert adapter.pre_process() is False
        finally:
            adapter.teardown()


# ──────────────────────────── RealtimeWSClient 同形方法面 ────────────────────────────

class TestSameShapeMethodSurface:
    def test_method_surface_delegates_to_transport(self, mock_rt):
        """executor 轮次编排消费的同形方法面齐全且可被 mock 应答"""
        adapter = OpenAIRealtimeAdapter(
            _make_api_config(mock_rt.url), case_config={}, endpoint=mock_rt.url)
        adapter.initialize()
        try:
            adapter.pre_process()
            adapter.reset_round_state()
            adapter.mark_commit()
            adapter.send_audio_chunk(_chunk_b64())
            adapter.commit_input()
            assert adapter.wait_ai_speaking(start_timeout=5) is True
            assert adapter.wait_ai_complete(start_timeout=5, end_timeout=5) is True
            output = adapter.output
            assert output['ai_complete'] is True
            assert len(adapter.frame_results) > 0
            assert adapter.connected is True
        finally:
            adapter.close()

    def test_output_defaults_before_connect(self):
        """未连接时 output 返回空聚合，不抛异常（executor finally 兜底安全）"""
        adapter = OpenAIRealtimeAdapter(
            _make_api_config('ws://127.0.0.1:1'), case_config={})
        out = adapter.output
        assert out['audio'] == b'' and out['ai_complete'] is False
        assert adapter.frame_results == []
