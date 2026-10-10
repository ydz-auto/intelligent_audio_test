# -*- coding: utf-8 -*-
"""INT-72 单测 — APIAdapterFactory 注册表化与 adapter_class 通道（UC-1003）。

覆盖：
- api_test_service 侧通道：apis.adapter_class 经 SendRound vendor_config
  透传至 adapter 服务；未配置时不携带该键（走 protocol+vendor 自动匹配）。
- api_adapter_service 注册表默认注册快照：五个内置适配器按 (protocol,
  vendor) 键注册即生效。
"""
import json
from types import SimpleNamespace

import pytest

import api_test_service.core.api_session_executor as executor_mod


def _run_send_via_adapter(monkeypatch, api_config):
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

    ex._send_via_adapter(
        task_id=31, algorithm_type='voice_llm', session=session,
        round_number=1, total_rounds=1,
        rendered_headers={}, rendered_body={},
        api_specific_config={}, meta={},
        api_config=api_config, timeout=20,
        input_text='hi', input_type='text', start_time=0.0,
        input_audio_path='')

    return json.loads(captured['req'].vendor_config)


class TestAdapterClassChannel:
    """apis.adapter_class → SendRound vendor_config 透传（UC-0901/UC-1003）。"""

    def test_adapter_class_forwarded(self, monkeypatch):
        api_config = SimpleNamespace(id=1, meta={}, api_endpoints=[],
                                     api_url='http://api',
                                     adapter_class='DoubaoRealtimeAdapter')
        vendor_config = _run_send_via_adapter(monkeypatch, api_config)
        assert vendor_config['adapter_class'] == 'DoubaoRealtimeAdapter'
        assert vendor_config['api_url'] == 'http://api'

    def test_no_adapter_class_key_when_unset(self, monkeypatch):
        """未配置 adapter_class → 不携带该键，自动匹配不受影响。"""
        api_config = SimpleNamespace(id=1, meta={}, api_endpoints=[],
                                     api_url='http://api', adapter_class=None)
        vendor_config = _run_send_via_adapter(monkeypatch, api_config)
        assert 'adapter_class' not in vendor_config


class TestAdapterRegistryDefaults:
    """api_adapter_service 注册表默认注册快照（UC-1003 注册即生效）。"""

    def test_default_registry_snapshot(self):
        from api_adapter_service.adapters.factory import api_adapter_factory
        assert api_adapter_factory.list_adapters() == {
            '(http, default)': 'HttpAdapter',
            '(mock, mock)': 'MockDialogAdapter',
            '(sse, default)': 'SseAdapter',
            '(websocket, qwen)': 'QwenAdapter',
            '(websocket, volc_ast)': 'VolcAstAdapter',
        }

    def test_adapter_class_priority_over_auto_match(self):
        """adapter_class 显式类名优先于 (protocol, vendor) 自动匹配。"""
        from api_adapter_service.adapters.factory import api_adapter_factory
        from api_adapter_service.adapters.qwen_adapter import QwenAdapter
        adapter = api_adapter_factory.get_adapter('openai', {
            'protocol': 'sse', 'adapter_class': 'QwenAdapter'})
        assert isinstance(adapter, QwenAdapter)

    def test_duplicate_key_conflict_raises(self):
        """同 (protocol, vendor) 注册不同实现 → 注册期抛错（UC-1003 5a）。"""
        from api_adapter_service.adapters.base import BaseAdapter
        from api_adapter_service.adapters.factory import APIAdapterFactory
        from api_adapter_service.domain.enums import AdapterProtocol, Vendor

        factory = APIAdapterFactory()

        class FakeA(BaseAdapter):
            def send_request(self, **kwargs):
                return {}

        class FakeB(BaseAdapter):
            def send_request(self, **kwargs):
                return {}

        factory.register(AdapterProtocol.WEBSOCKET, Vendor.QWEN, FakeA)
        with pytest.raises(ValueError, match='适配器注册冲突'):
            factory.register(AdapterProtocol.WEBSOCKET, Vendor.QWEN, FakeB)

    def test_websocket_unregistered_raises(self):
        """websocket 协议未注册 vendor → 拒绝静默降级，抛 ValueError。"""
        from api_adapter_service.adapters.factory import APIAdapterFactory
        factory = APIAdapterFactory()
        with pytest.raises(ValueError, match='websocket'):
            factory.get_adapter('doubao', {'protocol': 'websocket'})
