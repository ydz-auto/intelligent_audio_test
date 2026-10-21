# -*- coding: utf-8 -*-
"""INT-1176 迁移验证 — 内嵌 voice_llm chat 执行路径（api_adapter_service 删除）。

覆盖（验收标准 2：HTTP 多轮用例执行与迁移前结果契约一致）：
1. ApiDriverAdapter.execute_voice_llm_chat 请求逐字段等价：
   URL={base}/chat、rendered_headers 合入 + X-Session-Id、text json payload、
   audio multipart、显式 session_timeout、result_parser + 通用 fallback 解析。
2. _send_via_adapter 结果字段映射：output = asr or trans or output、
   latency 秒（客户端墙钟）、response_metrics={'latency'}、
   output_audio_path=None（HTTP 路径）、success/raw_response 透传。
3. 音频轮次缺混音产物 → 定轮次失败（INT-71 语义保留）。
4. adapter_class=MockDialogAdapter → MockVendorAdapter；未知类名报错。
"""
import json
import os
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'ut-dummy-ak')
os.environ.setdefault('OSS_SECRET_KEY', 'ut-dummy-sk')

import pytest

from api_test_service.infrastructure.adapters import api_driver_adapter as ada
from api_test_service.infrastructure.adapters import mock_vendor_adapter as mva
from api_test_service.infrastructure.adapters import vendor_adapter_registry
from api_test_service.core import api_session_executor as exmod


class _FakeSession:
    session_id = 's-int1176'
    session_timeout = 10

    def get_context(self):
        return [{'round': 1, 'input': 'a', 'output': 'b'}]

    def get_context_for_request(self):
        return [{'role': 'user', 'content': 'a'}]


def _driver_cfg(meta=None, adapter_class=None, vendor=None):
    return SimpleNamespace(id=1, meta=meta or {}, api_endpoints=[],
                           api_url='http://dut:5008',
                           adapter_class=adapter_class, vendor=vendor,
                           proxy_type=None, proxy_url=None, max_timeout=30)


# ── 1. execute_voice_llm_chat 请求等价 ─────────────────────────────

class TestVoiceLlmChatRequestEquivalence:
    def _run(self, input_type='text', input_data='你好', headers=None, **kw):
        cfg = _driver_cfg()
        adapter = ada.ApiDriverAdapter(cfg, case_config={})
        captured = {}

        def _fake_call(**kwargs):
            captured.update(kwargs)
            return {'status_code': 200, 'latency': 88,
                    'raw_response': '',
                    'json': {'asr_text': '你好', 'trans_text': 'hello'},
                    'error': None}

        with mock.patch.object(ada.api_client, 'call', _fake_call):
            result = adapter.execute_voice_llm_chat(
                session_id='s-1', input_type=input_type, input_data=input_data,
                source_lang='zh', target_lang='en',
                round_number=1, total_rounds=3, task_type='voice_llm',
                headers=headers, timeout=10, **kw)
        return captured, result

    def test_url_chat_suffix(self):
        captured, _ = self._run()
        assert captured['endpoint'] == 'http://dut:5008/chat'

    def test_headers_merged_with_session_id(self):
        captured, _ = self._run(headers={'X-Custom': 'v'})
        assert captured['headers']['X-Session-Id'] == 's-1'
        assert captured['headers']['X-Custom'] == 'v'

    def test_text_payload_fields(self):
        captured, result = self._run(
            context=[{'role': 'user', 'content': 'a'}],
            algorithm_params=[{'field_code': 'x', 'field_value': '1'}],
            case_algorithm_params={'k': 'v'}, translation_direction='zh2en')
        payload = captured['data']
        assert payload['session_id'] == 's-1'
        assert payload['task_type'] == 'voice_llm'
        assert payload['round'] == 1
        assert payload['total_rounds'] == 3
        assert payload['input'] == {'type': 'text', 'text': '你好'}
        assert payload['source_lang'] == 'zh'
        assert payload['target_lang'] == 'en'
        assert payload['translation_direction'] == 'zh2en'
        assert payload['context'] != []
        assert payload['algorithm_params'] != []
        assert payload['case_algorithm_params'] == {'k': 'v'}

    def test_explicit_timeout(self):
        captured, _ = self._run()
        assert captured['timeout'] == 10

    def test_audio_multipart(self):
        captured, _ = self._run(input_type='audio', input_data=b'\x00\x01')
        assert list(captured['files'].keys()) == ['audio']
        assert captured['data']['input_type'] == 'audio'
        # multipart 移除 Content-Type
        assert all(k.lower() != 'content-type'
                   for k in captured['headers'].keys())

    def test_audio_missing_raises(self):
        cfg = _driver_cfg()
        adapter = ada.ApiDriverAdapter(cfg, case_config={})
        with pytest.raises((ValueError, OSError)):
            adapter.execute_voice_llm_chat(
                session_id='s-1', input_type='audio', input_data='',
                round_number=1, total_rounds=1, timeout=5)

    def test_parse_fallback_and_parser(self):
        captured, result = self._run()
        assert result['asr'] == '你好'
        assert result['trans'] == 'hello'
        assert result['output'] == '你好'
        assert result['success'] is True

    def test_parser_paths_used_when_configured(self):
        cfg = _driver_cfg()
        adapter = ada.ApiDriverAdapter(cfg, case_config={})
        captured = {}

        def _fake_call(**kwargs):
            captured['json'] = kwargs.get('data', {})
            return {'status_code': 200, 'latency': 10, 'raw_response': '',
                    'json': {'result': {'asr_text': 'path-asr',
                                        'trans_text': 'path-trans'}},
                    'error': None}

        adapter.meta = {'result_parser': {
            'asr_text_path': 'result.asr_text',
            'trans_text_path': 'result.trans_text',
            'session_id_path': 'session_id'}}
        with mock.patch.object(ada.api_client, 'call', _fake_call):
            result = adapter.execute_voice_llm_chat(
                session_id='s-1', input_type='text', input_data='x',
                round_number=1, total_rounds=1, timeout=5)
        assert result['asr'] == 'path-asr'
        assert result['trans'] == 'path-trans'


# ── 2. _send_via_adapter 结果字段映射 ───────────────────────────────

class TestSendViaAdapterResultMapping:
    def _executor(self):
        ex = exmod.APISessionExecutor.__new__(exmod.APISessionExecutor)
        ex._executor = SimpleNamespace(_log=lambda *a, **k: None)
        return ex

    def test_round_result_fields_preserved(self):
        ex = self._executor()
        api_config = _driver_cfg(meta={'vendor_adapter': 'mock'})
        result = ex._send_via_adapter(
            task_id=31, algorithm_type='voice_llm', session=_FakeSession(),
            round_number=1, total_rounds=1, rendered_headers={}, rendered_body={},
            api_specific_config={}, meta={'vendor_adapter': 'mock'},
            api_config=api_config, timeout=20, input_text='hi',
            input_type='text', start_time=0.0, input_audio_path='')
        assert set(result.keys()) == {
            'round_number', 'input', 'input_type', 'output',
            'output_audio_path', 'latency', 'response_metrics',
            'success', 'raw_response'}
        assert result['output'] == 'hi'
        assert result['output_audio_path'] is None
        assert 'latency' in result['response_metrics']
        assert result['success'] is True

    def test_audio_missing_fails_loud(self):
        ex = self._executor()
        api_config = _driver_cfg(meta={'vendor_adapter': 'mock'})
        with pytest.raises(ValueError, match='拒绝空音频发送'):
            ex._send_via_adapter(
                task_id=31, algorithm_type='voice_llm', session=_FakeSession(),
                round_number=1, total_rounds=1, rendered_headers={},
                rendered_body={}, api_specific_config={}, meta={},
                api_config=api_config, timeout=20, input_text='',
                input_type='audio', start_time=0.0, input_audio_path='')

    def test_round_number_sort_key(self):
        assert exmod.APISessionExecutor._round_sort_key('3') == 3


# ── 3. mock 行为 + adapter_class 通道 ───────────────────────────────

class TestMockAdapterAndAdapterClass:
    def test_mock_per_session_counter(self):
        cfg = _driver_cfg()
        adapter = mva.MockVendorAdapter(cfg, case_config={})
        r1 = adapter.execute_voice_llm_chat(
            session_id='sess', input_type='text', input_data='你好',
            round_number=1, total_rounds=2, timeout=10)
        assert r1['asr'] == '你好'  # echo
        r2 = adapter.execute_voice_llm_chat(
            session_id='sess', input_type='text', input_data='',
            round_number=2, total_rounds=2, timeout=10)
        assert r2['asr'] != '你好'  # preset idx=1
        # 新会话重置计数
        a2 = mva.MockVendorAdapter(cfg, case_config={})
        s1 = a2.execute_voice_llm_chat(
            session_id='other', input_type='text', input_data='',
            round_number=1, total_rounds=1, timeout=10)
        assert s1['asr'] == '你好，有什么可以帮助你的？'

    def test_adapter_class_maps_to_mock(self):
        cfg = _driver_cfg(adapter_class='MockDialogAdapter')
        # 构造真实对象（api_config 上的 adapter_class 经 registry 读取）
        from api_test_service.infrastructure.adapters import registry as reg
        a_type = reg._adapter_class_override(cfg, None)
        assert a_type == reg.VendorAdapterType.MOCK

    def test_unknown_adapter_class_raises(self):
        from api_test_service.infrastructure.adapters import registry as reg
        cfg = _driver_cfg(adapter_class='NopeAdapter')
        with pytest.raises(ValueError, match='未注册'):
            reg._adapter_class_override(cfg, None)
