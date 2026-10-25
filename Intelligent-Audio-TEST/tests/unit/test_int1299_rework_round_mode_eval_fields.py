# -*- coding: utf-8 -*-
"""INT-1299 返工单测：resolve_round_mode 轮次语义归一化 + _collect_eval_fields field_mapper 配置透传

覆盖（验收补充，08:36 并入 / 08:43 修正后失败清单 P1-1 / P1-2 / P1-3）：
- P1-1 RealtimeAdapterBase.resolve_round_mode 默认语义（内部 _as_bool 兼容
  int/bool/str）：'0'/'false' 字符串不再误判打断轮；厂商方言覆写一例
- P1-1 RealtimeWSClient.resolve_round_mode（默认传输路径同形方法面）
- P1-1 executor _execute_round 改调 client.resolve_round_mode，不再自行 get 字段
- P1-2 _collect_eval_fields 无硬编码字段名：original.evaluation.output 的
  param_mapping（case/reference 源取 round_config，api 源取轮次输出）+
  original.api.output 字段定义（output_field_keys 模式）；无映射 → 空 dict
- P1-2 结构守卫：executor 源码无 get('is_interruption') / get('question') 等散落硬编码
"""
import inspect
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.models.common_enums import RealtimeRoundMode
from api_test_service.domain.dto import AlgoFieldMappingsDTO
from api_test_service.core.realtime_session_executor import RealtimeSessionExecutor
from api_test_service.infrastructure.adapters.protocol.realtime_adapter_base import (
    RealtimeAdapterBase,
)
from api_test_service.infrastructure.adapters.transport import RealtimeWSClient
import api_test_service.core.realtime_session_executor as rt_executor_module


def _make_api_config(endpoint='ws://mock', meta=None):
    return SimpleNamespace(
        id=7, endpoint=endpoint, api_endpoints=[], meta=dict(meta or {}),
        max_timeout=30, vendor='openai')


def _make_adapter(cls=RealtimeAdapterBase):
    return cls(_make_api_config())


def _executor():
    ex = RealtimeSessionExecutor.__new__(RealtimeSessionExecutor)
    ex._executor = SimpleNamespace(_log=lambda *a, **k: None)
    ex._on_frame = lambda *a, **k: None
    return ex


# ── P1-1：RealtimeAdapterBase.resolve_round_mode 默认语义 ──

class TestRealtimeAdapterBaseResolveRoundMode:
    def test_truthy_forms_map_to_interruption(self):
        adapter = _make_adapter()
        for v in (True, 1, 1.0, '1', 'true', 'True', 'yes', 'y', '是'):
            assert adapter.resolve_round_mode({'is_interruption': v}) \
                is RealtimeRoundMode.INTERRUPTION, v

    def test_falsy_forms_map_to_normal(self):
        """'0'/'false' 字符串不再被裸 truthy 误判为打断轮"""
        adapter = _make_adapter()
        for v in (False, 0, 0.0, '0', 'false', 'False', 'no', '', None):
            assert adapter.resolve_round_mode({'is_interruption': v}) \
                is RealtimeRoundMode.NORMAL, v

    def test_missing_or_none_round_config_is_normal(self):
        adapter = _make_adapter()
        assert adapter.resolve_round_mode({}) is RealtimeRoundMode.NORMAL
        assert adapter.resolve_round_mode(None) is RealtimeRoundMode.NORMAL

    def test_openai_adapter_inherits_default(self):
        from api_test_service.infrastructure.adapters.vendors.openai_realtime_adapter import (
            OpenAIRealtimeAdapter,
        )
        adapter = _make_adapter(OpenAIRealtimeAdapter)
        assert adapter.resolve_round_mode({'is_interruption': '1'}) \
            is RealtimeRoundMode.INTERRUPTION
        assert adapter.resolve_round_mode({'is_interruption': '0'}) \
            is RealtimeRoundMode.NORMAL


# ── P1-1：厂商方言覆写语义一例 ──

class _BargeInDialectAdapter(RealtimeAdapterBase):
    """厂商方言覆写示例：打断字段名 barge_in（非默认 is_interruption）"""

    def resolve_round_mode(self, round_config):
        if self._as_bool((round_config or {}).get('barge_in')):
            return RealtimeRoundMode.INTERRUPTION
        return RealtimeRoundMode.NORMAL


class TestVendorDialectOverride:
    def test_override_field_name_wins(self):
        adapter = _make_adapter(_BargeInDialectAdapter)
        assert adapter.resolve_round_mode({'barge_in': '1'}) \
            is RealtimeRoundMode.INTERRUPTION
        # 覆写后不再看 is_interruption（厂商字段名方言由覆写方法决定）
        assert adapter.resolve_round_mode({'barge_in': '0', 'is_interruption': True}) \
            is RealtimeRoundMode.NORMAL


# ── P1-1：RealtimeWSClient 默认传输路径同形方法面 ──

class TestRealtimeWSClientResolveRoundMode:
    def test_default_transport_semantics(self):
        client = RealtimeWSClient('ws://mock')
        assert client.resolve_round_mode({'is_interruption': '0'}) \
            is RealtimeRoundMode.NORMAL
        assert client.resolve_round_mode({'is_interruption': 'false'}) \
            is RealtimeRoundMode.NORMAL
        assert client.resolve_round_mode({'is_interruption': '1'}) \
            is RealtimeRoundMode.INTERRUPTION
        assert client.resolve_round_mode({'is_interruption': True}) \
            is RealtimeRoundMode.INTERRUPTION


# ── P1-1：executor 改调 resolve_round_mode，不再自行 get 字段 ──

class TestExecutorRoundModeDelegation:
    @staticmethod
    def _dispatch_executor():
        ex = _executor()
        calls = []
        ex._execute_interruption_round = \
            lambda *a, **k: calls.append('interruption') or {'mode': 'interruption'}
        ex._execute_normal_round = \
            lambda *a, **k: calls.append('normal') or {'mode': 'normal'}
        return ex, calls

    def test_dispatches_by_client_mode(self):
        ex, calls = self._dispatch_executor()
        client = RealtimeWSClient('ws://mock')
        ex._execute_round(client, None, {'is_interruption': True}, 1, 1, 1, {})
        assert calls == ['interruption']
        calls.clear()
        ex._execute_round(client, None, {'is_interruption': False}, 1, 1, 1, {})
        assert calls == ['normal']

    def test_falsy_strings_do_not_misjudge_interruption(self):
        ex, calls = self._dispatch_executor()
        client = RealtimeWSClient('ws://mock')
        for falsy in ('0', 'false', 'False', 0, False, None, ''):
            calls.clear()
            ex._execute_round(client, None, {'is_interruption': falsy}, 1, 1, 1, {})
            assert calls == ['normal'], falsy
        for truthy in ('1', 'true', 1, True, '是'):
            calls.clear()
            ex._execute_round(client, None, {'is_interruption': truthy}, 1, 1, 1, {})
            assert calls == ['interruption'], truthy


# ── P1-2：_collect_eval_fields field_mapper 配置透传 ──

_FIELD_MAPPINGS = {
    'original': {
        'case': {'input': {}, 'output': {}},
        'reference': {'input': {}, 'output': {}},
        'api': {'output': {
            'text': {'code': 'text'},
            'audio_text': {'code': 'audio_text'},
        }},
        'evaluation': {'output': {
            'question': {'source_param': 'query', 'source': 'case',
                         'target_param': 'question'},
            'correct_answer': {'source_param': 'correct_answer', 'source': 'case',
                               'target_param': 'correct_answer'},
            'reference_text': {'source_param': 'ref_text', 'source': 'reference',
                               'target_param': 'reference_text'},
            'answer': {'source_param': 'text', 'source': 'api',
                       'target_param': 'answer'},
        }},
    },
    'mapped': {},
}


class _ACLStub:
    def __init__(self, data):
        self._data = data

    def get_field_mappings(self, algorithm_type):
        return self._data


class TestCollectEvalFieldsFieldMapper:
    def test_case_reference_api_sources_mapped_to_targets(self, monkeypatch):
        """api 源按 param_mappings 映射到 target_param（INT-1746 收口）

        case/reference 来源改由评估侧按轮自行加载（C0 裁定 1），执行侧 output
        只保留 api/device 侧的键：被映射的 ``text`` 只以 target_param ``answer``
        出现；没配映射的 ``audio_text`` 按自身参数名保留（评估侧 mapped 键与
        报告展开都按它读）。
        """
        monkeypatch.setattr(rt_executor_module, '_algo_acl', _ACLStub(_FIELD_MAPPINGS))
        ex = _executor()
        fields = ex._collect_eval_fields(
            {'query': '你好', 'correct_answer': '对的', 'ref_text': '参考文本'},
            {'text': 'AI回复', 'audio_text': '副文本'},
            'voice_llm')
        assert fields == {'answer': 'AI回复', 'audio_text': '副文本'}
        assert 'text' not in fields  # source_param 不残留

    def test_missing_source_value_skipped(self, monkeypatch):
        """round_config 缺 source_param → 该 target 不出现（无兜底链）"""
        monkeypatch.setattr(rt_executor_module, '_algo_acl', _ACLStub(_FIELD_MAPPINGS))
        ex = _executor()
        fields = ex._collect_eval_fields(
            {'query': '你好'}, {'text': 'AI回复', 'audio_text': '副文本'}, 'voice_llm')
        assert fields == {'answer': 'AI回复', 'audio_text': '副文本'}

    def test_no_field_mappings_returns_empty(self, monkeypatch):
        monkeypatch.setattr(rt_executor_module, '_algo_acl', _ACLStub({}))
        ex = _executor()
        assert ex._collect_eval_fields({'query': 'x'}, {'text': 'y'}, 'voice_llm') == {}

    def test_algo_service_unreachable_empty_dto_returns_empty(self, monkeypatch):
        """ACL 回退 AlgoFieldMappingsDTO()（算法服务不可达）→ 空 dict"""
        monkeypatch.setattr(rt_executor_module, '_algo_acl', _ACLStub(AlgoFieldMappingsDTO()))
        ex = _executor()
        assert ex._collect_eval_fields({'query': 'x'}, {'text': 'y'}, 'voice_llm') == {}

    def test_default_algorithm_type_fallback(self, monkeypatch):
        """algorithm_type 缺省 → voice_llm（对齐既有默认）"""
        captured = {}
        class _RecordingACL:
            def get_field_mappings(self, algorithm_type):
                captured['algorithm_type'] = algorithm_type
                return _FIELD_MAPPINGS
        monkeypatch.setattr(rt_executor_module, '_algo_acl', _RecordingACL())
        ex = _executor()
        ex._collect_eval_fields({'query': '你好'}, {'text': 'AI回复', 'audio_text': '副文本'})
        assert captured['algorithm_type'] == 'voice_llm'


# ── P1-2 结构守卫：executor 无散落硬编码字段名 ──

class TestNoScatteredHardcodedFieldGetters:
    def test_executor_source_has_no_hardcoded_eval_field_getters(self):
        src = inspect.getsource(rt_executor_module)
        for needle in (
            "get('is_interruption')",
            "get('question'",
            "get('query'",
            "get('correct_answer'",
            "get('original_topic'",
        ):
            assert needle not in src, f'executor 源码仍含散落硬编码: {needle}'
