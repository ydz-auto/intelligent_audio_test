# -*- coding: utf-8 -*-
"""INT-1749 执行侧 transform_type 接线（真实映射处理器 + 真实变换实现）

覆盖 C4 卡面验收 1 / 2 / 3 / 4 / 5 的可离线部分：

- 映射侧用**真实** ``FieldMappingQueryHandler.get_field_definitions``（假
  config_cache 喂 ``param_mappings`` 行口径，含 ``transform_type`` 列），
  证明「库里配了 json_parse / base64」一路带到执行侧；
- 变换侧用**真实** ``FieldMappingQueryHandler.convert_field_values``
  （= ``FieldTransformService``），不复制实现；
- 执行链用**真实** ``_attach_api_output_fields``（HTTP 多轮）、
  ``_collect_eval_fields``（Realtime）、``extract_final_result`` 的映射入口；
- 评估侧用**真实** ``RoundDataBuilderMixin._build_single_round`` 复算，
  证明执行侧落库值即评估侧取值（不二次变换）。
"""
import os

import pytest

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')


class _FakeConfigCache:
    """假 config_cache：只喂本用例关心的参数与映射行（口径同 DB 列）。"""

    def __init__(self, api_params, evaluation_mappings):
        self._api_params = api_params
        self._evaluation_mappings = evaluation_mappings

    def get_device_params(self, algorithm_type):
        return []

    def get_api_params(self, algorithm_type, api_id=None):
        return self._api_params

    def get_reference_params(self, algorithm_type):
        return []

    def get_case_params(self, algorithm_type):
        return []

    def get_param_mapping(self, algorithm_type, source, api_id=None):
        return self._evaluation_mappings if source == 'evaluation' else []


def _api_params(nested=True):
    # algorithm_api_params 行（direction=output）
    # nested=True：厂商响应包在 data 里，按 field_path 取嵌套值
    # nested=False：WS 聚合输出是扁平的，无 field_path 按 param_code 取顶层键
    if not nested:
        return [
            {'code': 'reply_text', 'param_type': 'text', 'direction': 'output'},
            {'code': 'reply_audio', 'param_type': 'audio', 'direction': 'output'},
            {'code': 'plain', 'param_type': 'text', 'direction': 'output'},
        ]
    return [
        {'code': 'reply_text', 'param_type': 'text', 'direction': 'output',
         'field_path': 'data.text'},
        {'code': 'reply_audio', 'param_type': 'audio', 'direction': 'output',
         'field_path': 'data.audio'},
        {'code': 'plain', 'param_type': 'text', 'direction': 'output'},
    ]


def _maps(answer_transform='json_parse', audio_transform='base64'):
    # param_mappings 行（transform_type 列由查询处理器原样带出）
    rows = [
        {'source': 'api', 'source_param': 'reply_text',
         'target_param': 'answer', 'transform_type': answer_transform,
         'dimension_id': 1, 'dimension_name': '识别准确率'},
        {'source': 'api', 'source_param': 'reply_audio',
         'target_param': 'audio_out', 'transform_type': audio_transform},
        {'source': 'case', 'source_param': 'query',
         'target_param': 'query', 'transform_type': 'none'},
    ]
    return rows


def _field_mappings(monkeypatch, nested=True, **kwargs):
    """真实查询处理器产出的 field_mappings（GetFieldMappings 返回口径）。"""
    import algorithm_service.application.queries.field_mapping_queries as q
    cache = _FakeConfigCache(_api_params(nested), _maps(**kwargs))
    monkeypatch.setattr(q, 'get_config_cache', lambda: cache)
    return q.FieldMappingQueryHandler.get_field_definitions('voice_llm')


class _RealTransformAcl:
    """ACL 替身：convert_field_values 直接调真实处理器（= 真实变换实现）。

    只替换跨进程这一跳，变换语义与批量编排走生产代码。
    """

    def __init__(self, field_mappings):
        self._field_mappings = field_mappings
        self.calls = []

    def get_field_mappings(self, algorithm_type, api_id=None):
        # INT-1757（C6b）：执行链调用带 api_id 形参，替身按算法级默认返回
        return self._field_mappings

    def convert_field_values(self, items):
        from algorithm_service.application.queries.field_mapping_queries import (
            FieldMappingQueryHandler,
        )
        self.calls.append(list(items))
        data = FieldMappingQueryHandler.convert_field_values(items)
        # 与真实 ACL 同口径：非空 errors 时保留原值
        if data.get('errors'):
            return None
        return data.get('values')


def _realtime_executor():
    from api_test_service.core.realtime_session_executor import RealtimeSessionExecutor
    return object.__new__(RealtimeSessionExecutor)


class _SessionExecutor:
    """HTTP 多轮 _attach_api_output_fields 的最小执行器替身（只需 _log）。"""


class _SilentLog:
    def __call__(self, *args, **kwargs):
        pass


def _session_executor():
    from api_test_service.core.api_session_executor import APISessionExecutor
    executor = object.__new__(APISessionExecutor)
    # _log 是只读 property（转发到 _executor._log），替身只提供日志能力
    executor._executor = type('_Exec', (), {'_log': _SilentLog()})()
    return executor


# ---------------------------------------------------------------- 验收 5 / 4

def test_mapping_handler_carries_transform_type_and_none_is_skipped(monkeypatch):
    from shared.utils.api_output_extractor import get_output_transform_types

    mappings = _field_mappings(monkeypatch, answer_transform='none')
    entry = mappings['original']['evaluation']['output']['answer']
    assert entry['transform_type'] == 'none'
    # none / 空值不进待变换集合（原值直传，改前行为）
    assert 'answer' not in get_output_transform_types(mappings)
    # case 来源由评估侧按轮加载，执行侧不变换
    assert 'query' not in get_output_transform_types(mappings)


def test_all_non_none_transforms_go_in_one_batch(monkeypatch):
    from shared.utils.api_output_extractor import get_output_transform_types

    mappings = _field_mappings(monkeypatch)
    assert get_output_transform_types(mappings) == {
        'answer': 'json_parse', 'audio_out': 'base64'}


# ---------------------------------------------------------------- 验收 1 / 2

def test_http_session_round_output_transformed(monkeypatch):
    """HTTP 多轮：rounds[i].output 在写入前已按 transform_type 变换。"""
    mappings = _field_mappings(monkeypatch)
    acl = _RealTransformAcl(mappings)
    import api_test_service.core.api_session_executor as sess_mod
    monkeypatch.setattr(sess_mod, '_algo_acl', acl)

    executor = _session_executor()
    round_result = {
        'round_number': 1,
        'answer_text': '{"a": 1}',
        'raw_response': {'data': {'text': '{"a": 1}', 'audio': 'abc'},
                         'plain': 'p'},
    }
    executor._attach_api_output_fields(round_result, mappings, 'voice_llm', 't1')

    # 验收 1：json_parse → 对象
    assert round_result['output']['answer'] == {'a': 1}
    # 验收 2：base64 按编码语义
    assert round_result['output']['audio_out'] == 'YWJj'
    # 未配映射的输出字段按自身参数名保留，源键不残留
    assert round_result['output']['plain'] == 'p'
    assert 'reply_text' not in round_result['output']
    assert 'reply_audio' not in round_result['output']
    # 验收 5：2 个字段只发 1 次批量请求
    assert len(acl.calls) == 1
    assert len(acl.calls[0]) == 2
    # 映射前的原始值留作排障证据
    assert round_result['output_fields']['reply_text'] == '{"a": 1}'


def test_realtime_collect_eval_fields_transformed(monkeypatch):
    """Realtime：同一个变换入口，WS 轮次 output 同构。"""
    mappings = _field_mappings(monkeypatch, nested=False)
    acl = _RealTransformAcl(mappings)
    import api_test_service.core.realtime_session_executor as rt_mod
    monkeypatch.setattr(rt_mod, '_algo_acl', acl)

    fields = _realtime_executor()._collect_eval_fields(
        {}, {'reply_text': '{"a": 1}', 'reply_audio': 'abc'}, 'voice_llm',
        text_output=None)

    assert fields == {'answer': {'a': 1}, 'audio_out': 'YWJj'}
    assert len(acl.calls) == 1


def test_invalid_json_keeps_original_value(monkeypatch):
    """非法输入：保留原值（不吞成空串），并记录 errors。"""
    from algorithm_service.application.queries.field_mapping_queries import (
        FieldMappingQueryHandler,
    )

    data = FieldMappingQueryHandler.convert_field_values(
        [{'transform_type': 'json_parse', 'value': '{bad'},
         {'transform_type': 'base64', 'value': 123}])
    assert data['values'][0] == '{bad'
    assert [e['index'] for e in data['errors']] == [0, 1]
    # 非字符串进 base64 同样按「保留原值 + errors 回传」，不吞成空串
    assert data['values'][1] == 123


def test_acl_errors_degrade_to_original(monkeypatch):
    """批量 RPC 带 errors 时整体按原值保留（执行链不中断）。"""
    mappings = _field_mappings(monkeypatch)

    class _ErrorAcl(_RealTransformAcl):
        def convert_field_values(self, items):
            self.calls.append(list(items))
            return None

    acl = _ErrorAcl(mappings)
    import api_test_service.core.api_session_executor as sess_mod
    monkeypatch.setattr(sess_mod, '_algo_acl', acl)

    round_result = {'round_number': 1, 'answer_text': '{bad',
                    'raw_response': {'data': {'text': '{bad', 'audio': 'abc'}}}
    _session_executor()._attach_api_output_fields(
        round_result, mappings, 'voice_llm', 't1')
    assert round_result['output']['answer'] == '{bad'
    assert round_result['output']['audio_out'] == 'abc'


# ---------------------------------------------------------------- 验收 4

@pytest.mark.parametrize('transform_type', ['none', None, ''])
def test_none_transform_regression(monkeypatch, transform_type):
    """none / 空 transform_type：不改变量的原值直传。"""
    mappings = _field_mappings(monkeypatch)
    entry = mappings['original']['evaluation']['output']['answer']
    entry['transform_type'] = transform_type
    acl = _RealTransformAcl(mappings)
    import api_test_service.core.api_session_executor as sess_mod
    monkeypatch.setattr(sess_mod, '_algo_acl', acl)

    round_result = {'round_number': 1, 'answer_text': 'raw',
                    'raw_response': {'data': {'text': 'raw', 'audio': 'abc'}}}
    _session_executor()._attach_api_output_fields(
        round_result, mappings, 'voice_llm', 't1')

    assert round_result['output']['answer'] == 'raw'
    # 只有 audio_out 需要变换，answer 不进批量请求
    assert [item['transform_type'] for item in acl.calls[0]] == ['base64']


# ---------------------------------------------------------------- 验收 3

def test_eval_side_reads_same_value_without_second_transform(monkeypatch):
    """评估侧按 target_param 原样取值：与执行侧落库值逐字段一致。"""
    from evaluation_service.domain.services.evaluation_service.round_data_builder import (
        RoundDataBuilderMixin,
    )

    mappings = _field_mappings(monkeypatch)
    acl = _RealTransformAcl(mappings)
    import api_test_service.core.api_session_executor as sess_mod
    monkeypatch.setattr(sess_mod, '_algo_acl', acl)

    round_result = {'round_number': 1, 'answer_text': '{"a": 1}',
                    'raw_response': {'data': {'text': '{"a": 1}', 'audio': 'abc'}}}
    _session_executor()._attach_api_output_fields(
        round_result, mappings, 'voice_llm', 't1')

    builder = object.__new__(RoundDataBuilderMixin)
    eval_item = builder._build_single_round(
        {'round': 0, 'output': round_result['output']},
        None,
        _maps(),
        'llm_judge', 'voice_llm', 't1', 'c1',
        get_reference_params_fn=lambda algorithm_type: [],
        load_round_ref_file_fn=lambda *args, **kwargs: {},
        case_config=None)

    # 逐字段一致（JSON diff 为空）：评估侧拿到的就是执行侧变换后的值
    for target in ('answer', 'audio_out'):
        assert eval_item[target] == round_result['output'][target]
    assert eval_item['answer'] == {'a': 1}
    assert eval_item['audio_out'] == 'YWJj'


# ---------------------------------------------------------------- 单轮链

class _LogExecutorStub:
    def _log(self, *args, **kwargs):
        pass


def test_single_round_extract_final_result_applies_transform(monkeypatch):
    """HTTP 单轮：extract_final_result 的映射入口同样在落轮次 output 前变换。"""
    from algorithm_service.application.queries.field_mapping_queries import (
        FieldMappingQueryHandler,
    )
    from api_test_service.core import api_task_runner as runner_mod

    mappings = _field_mappings(monkeypatch)
    calls = []

    def _convert(items):
        calls.append(list(items))
        data = FieldMappingQueryHandler.convert_field_values(items)
        return None if data.get('errors') else data.get('values')

    monkeypatch.setattr(runner_mod._algo_acl, 'get_field_mappings',
                        lambda algorithm_type, api_id=None: mappings)
    monkeypatch.setattr(runner_mod._algo_acl, 'get_device_params',
                        lambda algorithm_type: [])
    monkeypatch.setattr(runner_mod._algo_acl, 'get_api_params',
                        lambda algorithm_type, api_id=None: [])
    monkeypatch.setattr(runner_mod._algo_acl, 'get_param_mapping',
                        lambda algorithm_type, comp_type, api_id=None: [])
    monkeypatch.setattr(runner_mod._algo_acl, 'convert_field_values', _convert)

    runner = runner_mod.APITaskRunner(_LogExecutorStub())
    algo_results, _ = runner.extract_final_result(
        1, {'json': {'code': 0, 'data': {'text': '{"a": 1}', 'audio': 'abc'}},
            'latency': 5}, 'voice_llm')

    assert algo_results['answer'] == {'a': 1}
    assert algo_results['audio_out'] == 'YWJj'
    assert len(calls) == 1
