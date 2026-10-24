# -*- coding: utf-8 -*-
"""INT-1747 / C2 守卫：API 输出字段 field_path（响应嵌套取值）+ 评估字段键 device∪api。

C0（INT-1745）裁定 §9.2 / §9.3：
- 输出字段声明唯一来源 ``algorithm_api_params(direction=output)``；
  ``field_path`` 非空按路径从厂商原始响应取值，为空按 ``param_code`` 取顶层键；
- ``apis.meta`` 解析器只在「该算法类型零输出声明」时逐键兜底；
- 单轮 / 多轮 / Realtime 三条链共用 ``shared.utils.api_output_extractor``；
- 评估侧输出字段键集合 = device ∪ api（仅输出字段展示/提取）。

覆盖：
1. extract_by_path：点路径 / 点号数字下标 / [n] 下标 / 两者等价 / 缺失键 /
   空路径 / 非 dict 中间层 / 非法下标 / dict 数字键存量语义；
2. extract_api_output_fields：声明优先、零声明兜底、都没有则空；
3. 单轮链：嵌套 field_path 取到值；存量（field_path 空）逐字段与改前一致；
   零声明走兜底并打 WARNING；
4. 多轮链：适配器 execute 结果 / 直连响应两种口径都能提取；
5. Realtime 链：field_path 在 WS 聚合输出上提取；
6. 评估侧：输出字段键 = device ∪ api（endpoint_worker 采集处）；
7. 配置缓存序列化透传 field_path（算法配置回读 / GetFieldMappings 口径）。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.utils.field_mapper_wrapper import FieldMapperWrapper
from shared.utils.path_extractor import extract_by_path
from shared.utils.api_output_extractor import (
    SOURCE_DECLARED,
    SOURCE_META_FALLBACK,
    SOURCE_NONE,
    extract_api_output_fields,
    extract_declared_output_fields,
    get_api_output_field_defs,
)


NESTED_RESPONSE = {
    'code': 0,
    'data': {
        'translation': {'text': '你好', 'segments': [{'start': 0, 'end': 1}]},
        'events': [{'text': '第一段'}, {'text': '第二段'}],
    },
}


def _output_defs(*defs):
    return {
        'original': {
            'api': {
                'output': {
                    code: {'code': code, 'direction': 'output', **extra}
                    for code, extra in defs
                },
            },
        },
    }


class _LogExecutorStub:
    """执行器替身：仅提供 runner / session executor 依赖的 _log"""

    def __init__(self):
        self.logs = []

    def _log(self, level='INFO', content='', task_id=None, **kwargs):
        self.logs.append((level, content))

    def _handle_control(self, task_id):
        pass


# ==================== 1. 路径提取 ====================

def test_extract_by_path_dot_and_index_syntax():
    assert extract_by_path(NESTED_RESPONSE, 'data.translation.text') == '你好'
    # 点号数字下标与 [n] 等价
    assert extract_by_path(NESTED_RESPONSE, 'data.events.0.text') == '第一段'
    assert extract_by_path(NESTED_RESPONSE, 'data.events[0].text') == '第一段'
    assert extract_by_path(NESTED_RESPONSE, 'data.events[1].text') == '第二段'
    # 段内多下标
    assert extract_by_path({'m': [[1, 2], [3, 4]]}, 'm[1][0]') == 3
    # 下标后继续点分
    assert extract_by_path({'m': [{'v': 'x'}]}, 'm[0].v') == 'x'


def test_extract_by_path_missing_and_invalid():
    assert extract_by_path(NESTED_RESPONSE, 'data.missing.text') is None
    assert extract_by_path(NESTED_RESPONSE, 'data.events[9].text') is None
    assert extract_by_path(NESTED_RESPONSE, '') is None
    assert extract_by_path(NESTED_RESPONSE, None) is None
    # 非 dict/list 中间层
    assert extract_by_path(NESTED_RESPONSE, 'data.translation.text.more') is None
    # 非法下标写法（非数字 / 负数）按路径无效
    assert extract_by_path(NESTED_RESPONSE, 'data.events[x].text') is None
    assert extract_by_path(NESTED_RESPONSE, 'data.events[-1].text') is None
    # 段名与取值类型不匹配
    assert extract_by_path(NESTED_RESPONSE, 'data.events.text') is None
    assert extract_by_path(NESTED_RESPONSE, 'data.0.text') is None
    # default 透传
    assert extract_by_path(NESTED_RESPONSE, 'data.missing', 'dft') == 'dft'


def test_extract_by_path_preserves_legacy_dict_numeric_key():
    # 点号数字段在 dict 上仍按字符串键查（与扩展前一致）
    assert extract_by_path({'0': 'v'}, '0') == 'v'
    assert extract_by_path({'rounds': [{'output': {'q': 'a'}}]}, 'rounds.0.output.q') == 'a'


# ==================== 2. 声明驱动提取 / 兜底 ====================

def test_extract_api_output_fields_declared_prefers_field_path():
    mappings = _output_defs(
        ('text', {'field_path': 'data.translation.text'}),
        ('first_event', {'field_path': 'data.events[0].text'}),
    )
    values, source = extract_api_output_fields(mappings, NESTED_RESPONSE)
    assert source == SOURCE_DECLARED
    assert values == {'text': '你好', 'first_event': '第一段'}


def test_extract_api_output_fields_declared_pathless_uses_flat_source():
    mappings = _output_defs(('asr_result', {}))
    values, source = extract_api_output_fields(
        mappings, {'code': 0, 'data': {'asr_result': '顶层键值'}},
        flat_source={'asr_result': '顶层键值'})
    assert source == SOURCE_DECLARED
    assert values == {'asr_result': '顶层键值'}


def test_extract_api_output_fields_zero_declaration_falls_back():
    mappings = {'original': {'api': {'output': {}}}}
    values, source = extract_api_output_fields(
        mappings, {'whatever': 1},
        fallback_values={'asr': '问', 'trans': '答', 'output': '', 'other': 'x'})
    assert source == SOURCE_META_FALLBACK
    # 只认 meta 解析器产出的三个键，空值不写
    assert values == {'asr': '问', 'trans': '答'}


def test_extract_api_output_fields_no_declaration_no_fallback():
    values, source = extract_api_output_fields(
        {'original': {'api': {'output': {}}}}, {'a': 1}, fallback_values={'asr': ''})
    assert values == {}
    assert source == SOURCE_NONE


def test_get_api_output_field_defs_tolerates_missing_structure():
    assert get_api_output_field_defs(None) == {}
    assert get_api_output_field_defs({}) == {}
    assert get_api_output_field_defs({'original': None}) == {}
    defs = get_api_output_field_defs(
        _output_defs(('text', {'field_path': 'data.translation.text'})))
    assert list(defs) == ['text']


def test_extract_declared_output_fields_missing_key_is_none():
    values = extract_declared_output_fields(
        {'text': {'field_path': 'data.missing'}}, NESTED_RESPONSE)
    assert values == {'text': None}


# ==================== 3. 单轮链 ====================

def _patch_single_round_acl(monkeypatch, field_mappings):
    from api_test_service.core import api_task_runner as runner_mod
    monkeypatch.setattr(runner_mod._algo_acl, 'get_field_mappings',
                        lambda algorithm_type: field_mappings)
    monkeypatch.setattr(runner_mod._algo_acl, 'get_device_params',
                        lambda algorithm_type: [])
    monkeypatch.setattr(runner_mod._algo_acl, 'get_api_params',
                        lambda algorithm_type: [])
    monkeypatch.setattr(runner_mod._algo_acl, 'get_param_mapping',
                        lambda algorithm_type, comp_type: [])
    return runner_mod


def _make_runner(monkeypatch, field_mappings):
    runner_mod = _patch_single_round_acl(monkeypatch, field_mappings)
    executor = _LogExecutorStub()
    return runner_mod.APITaskRunner(executor), executor


def test_single_round_extracts_nested_field_path(monkeypatch):
    runner, executor = _make_runner(
        monkeypatch,
        _output_defs(('text', {'field_path': 'data.translation.text'})))
    final_result = {
        'json': {'code': 0, 'data': {'translation': {'text': '你好'}}},
        'latency': 12, 'asr': '', 'trans': '', 'output': '',
    }
    algo_results, latency = runner.extract_final_result(1, final_result, 'translation')
    assert algo_results == {'text': '你好'}
    assert latency == 12


def test_single_round_array_field_path_both_syntaxes(monkeypatch):
    for path in ('data.events[0].text', 'data.events.0.text'):
        runner, _ = _make_runner(
            monkeypatch, _output_defs(('event_text', {'field_path': path})))
        algo_results, _ = runner.extract_final_result(
            1, {'json': NESTED_RESPONSE, 'latency': 1,
                'asr': '', 'trans': '', 'output': ''}, 'translation')
        assert algo_results == {'event_text': '第一段'}


def test_single_round_legacy_top_level_behavior_unchanged(monkeypatch):
    """存量（field_path 为空）：仍按 param_code 取 json.data 顶层键，缺失补空串。"""
    runner, _ = _make_runner(
        monkeypatch, _output_defs(('asr_result', {}), ('translation', {})))
    final_result = {
        'json': {'code': 0, 'data': {'asr_result': '识别文本'}},
        'latency': 3, 'asr': '', 'trans': '', 'output': '',
    }
    algo_results, _ = runner.extract_final_result(1, final_result, 'translation')
    assert algo_results == {'asr_result': '识别文本', 'translation': ''}


def test_single_round_zero_declaration_warns_and_falls_back(monkeypatch):
    runner, executor = _make_runner(
        monkeypatch, {'original': {'api': {'output': {}}}})
    final_result = {
        'json': {'code': 0, 'data': {}},
        'latency': 3, 'asr': '问', 'trans': '答', 'output': '答',
    }
    algo_results, _ = runner.extract_final_result(1, final_result, 'translation')
    assert algo_results == {'asr': '问', 'trans': '答', 'output': '答'}
    assert any(level == 'WARNING' and '兜底' in content
               for level, content in executor.logs)


def test_single_round_field_path_wins_over_same_named_top_level_key(monkeypatch):
    """声明带 field_path 时按路径取值，不被同名的 json.data 顶层键覆盖。"""
    runner, _ = _make_runner(
        monkeypatch,
        _output_defs(('text', {'field_path': 'data.translation.text'})))
    final_result = {
        'json': {'code': 0, 'data': {'text': '顶层旧值',
                                     'translation': {'text': '你好'}}},
        'latency': 1, 'asr': '', 'trans': '', 'output': '',
    }
    algo_results, _ = runner.extract_final_result(1, final_result, 'translation')
    assert algo_results == {'text': '你好'}


def test_single_round_declared_suppresses_meta_fallback(monkeypatch):
    """有声明时 meta 解析器不生效：只出声明字段，asr/trans/output 不混入。"""
    runner, executor = _make_runner(
        monkeypatch, _output_defs(('text', {'field_path': 'data.missing'})))
    final_result = {
        'json': {'code': 0, 'data': {}},
        'latency': 1, 'asr': '问', 'trans': '答', 'output': '答',
    }
    algo_results, _ = runner.extract_final_result(1, final_result, 'translation')
    assert algo_results == {'text': ''}
    assert not any('兜底' in content for _, content in executor.logs)


# ==================== 4. 多轮链 ====================

def _make_session_executor():
    from api_test_service.core.api_session_executor import APISessionExecutor
    executor = APISessionExecutor.__new__(APISessionExecutor)
    executor._executor = _LogExecutorStub()
    return executor


def test_multi_round_adapter_path_extracts_field_path():
    executor = _make_session_executor()
    round_result = {
        'round_number': 1,
        'raw_response': {
            'success': True,
            'json': {'code': 0, 'data': {'translation': {'text': '你好'}}},
            'asr': '', 'trans': '', 'output': '',
        },
    }
    executor._attach_api_output_fields(
        round_result,
        _output_defs(('text', {'field_path': 'data.translation.text'})),
        'translation', task_id=1, unwrap_execute_result=True)
    assert round_result['output_fields'] == {'text': '你好'}


def test_multi_round_direct_path_extracts_field_path():
    executor = _make_session_executor()
    round_result = {
        'round_number': 1,
        'raw_response': {'data': {'events': [{'text': '第一段'}]}},
    }
    executor._attach_api_output_fields(
        round_result,
        _output_defs(('event_text', {'field_path': 'data.events[0].text'})),
        'translation', task_id=1)
    assert round_result['output_fields'] == {'event_text': '第一段'}


def test_multi_round_missing_value_writes_nothing():
    """声明存在但响应里取不到值：不写 output_fields，保持存量轮次结构。"""
    executor = _make_session_executor()
    round_result = {'round_number': 1,
                    'raw_response': {'success': True, 'json': {'data': {}}}}
    executor._attach_api_output_fields(
        round_result, _output_defs(('response_audio', {})),
        'voice_llm', task_id=1, unwrap_execute_result=True)
    assert 'output_fields' not in round_result


# ==================== 5. Realtime 链 ====================

def test_realtime_collect_eval_fields_uses_field_path(monkeypatch):
    from api_test_service.core import realtime_session_executor as rt_mod
    mappings = _output_defs(('text', {'field_path': 'nested.answer'}))
    monkeypatch.setattr(rt_mod._algo_acl, 'get_field_mappings',
                        lambda algorithm_type: mappings)
    executor = rt_mod.RealtimeSessionExecutor.__new__(
        rt_mod.RealtimeSessionExecutor)
    fields = executor._collect_eval_fields(
        {}, {'text': '平铺文本', 'nested': {'answer': '嵌套答案'}}, 'voice_llm')
    assert fields == {'text': '嵌套答案'}


def test_realtime_collect_eval_fields_zero_declaration_stays_empty(monkeypatch):
    """零声明时 Realtime 不兜底：本方法产出的是评估入参字段，入参侧只认
    param_mappings（卡面约束，与改前一致返回空）。"""
    from api_test_service.core import realtime_session_executor as rt_mod
    monkeypatch.setattr(rt_mod._algo_acl, 'get_field_mappings',
                        lambda algorithm_type: {'original': {'api': {'output': {}}}})
    executor = rt_mod.RealtimeSessionExecutor.__new__(
        rt_mod.RealtimeSessionExecutor)
    fields = executor._collect_eval_fields({}, {'text': '会话输出'}, 'voice_llm')
    assert fields == {}


# ==================== 6. 评估侧输出字段键 device ∪ api ====================

def test_field_mapper_wrapper_api_output_keys():
    wrapper = FieldMapperWrapper({'mapped': {'api': {'api_only': {}, 'shared': {}}}})
    assert wrapper.get_mapped_api_output_field_keys() == ['api_only', 'shared']
    assert FieldMapperWrapper({}).get_mapped_api_output_field_keys() == []


def test_endpoint_worker_output_field_keys_union(monkeypatch):
    from evaluation_service.infrastructure.evaluation_api import endpoint_worker as ew
    wrapper = FieldMapperWrapper({
        'original': {'evaluation': {'input': {}}},
        'mapped': {'device': {'answer': {'target_param': 'answer'}},
                   'api': {'api_only': {'target_param': 'api_only'}}},
    })
    monkeypatch.setattr(ew.algorithm_acl_repository, 'get_field_mappings',
                        lambda algorithm_type: wrapper)
    worker = ew.EndpointWorker.__new__(ew.EndpointWorker)
    worker._log = lambda **kwargs: None
    captured = {}

    def _capture_context(task_id, test_case_id, algorithm_result,
                         representative_dim_data, algorithm_type,
                         output_field_keys, dim_id, eval_input_fields, kwargs,
                         group_items=None):
        captured['output_field_keys'] = output_field_keys
        return {}

    worker._build_evaluation_context = _capture_context
    worker._prepare_api_config = lambda *a, **k: ({}, 'POST', {}, {}, [])
    worker._call_evaluation_api = lambda *a, **k: {}
    worker._process_evaluation_result = lambda *a, **k: None

    worker._execute_evaluation(
        task_id=1, result_id=2, test_case_id=3, algorithm_result={},
        representative_dim_data={'id': 7, 'name': 'd'},
        group_items=[({'id': 7, 'name': 'd'},)],
        algorithm_type='voice_llm')

    assert captured['output_field_keys'] == ['answer', 'api_only']


# ==================== 7. 配置缓存序列化透传 ====================

def test_serialize_params_passes_field_path_only_when_present():
    from algorithm_service.infrastructure.persistence.config_cache import (
        AlgorithmConfigCache,
    )
    rows = [
        {'id': 1, 'param_code': 'text', 'direction': 'output',
         'field_path': 'data.translation.text'},
        {'id': 2, 'param_code': 'response_audio', 'direction': 'output',
         'field_path': None},
        {'id': 3, 'param_code': 'device_code', 'direction': 'output'},
    ]
    serialized = AlgorithmConfigCache._serialize_params(rows)
    assert serialized[0]['field_path'] == 'data.translation.text'
    assert 'field_path' not in serialized[1]
    assert 'field_path' not in serialized[2]


# ==================== 8. 网关参数 CRUD 透传（打回 P1/P2） ====================

class _FakeParamRepo:
    """参数仓储替身：只记录下发给 UpdateParam RPC 的字段，不连库。

    ``get_device_param`` 对 API 参数返回 None —— 这是修复后的真实 ACL 语义
    （按 GetParam 响应里的 ``param_type_source`` 判类型，不再跨表回落）；
    来源判定的真实链路用例见 ``test_int1747_param_source_type_judgment.py``。
    """

    def __init__(self, *, device=None, api=None, api_list=None):
        self._device = device
        self._api = api
        self._api_list = api_list or []
        self.sent_fields = None
        self.commits = 0

    def get_device_param(self, param_id):
        return self._device

    def get_api_param(self, param_id):
        return self._api

    def list_api_params(self, algorithm_type=None):
        return list(self._api_list)

    def update_param_attrs(self, param, fields):
        self.sent_fields = fields

    def commit(self):
        self.commits += 1


def _crud_service(repo):
    from task_service.application.algorithm.algorithm_param_crud_service import (
        AlgorithmParamCrudService,
    )
    svc = AlgorithmParamCrudService.__new__(AlgorithmParamCrudService)
    svc.repo = repo
    return svc


def test_update_param_sends_field_path_for_api_param():
    """P1：PUT /algorithm/params/{id} 对 API 参数必须把 field_path 下发到 UpdateParam RPC。"""
    repo = _FakeParamRepo(api={'id': 1, 'algorithm_type': 'voice_llm',
                               'param_code': 'text', 'direction': 'output'})
    result = _crud_service(repo).update_param(
        1, {'field_path': 'data.translation.text', 'ui_order': 9})

    assert result['success'] is True
    assert repo.sent_fields == {'field_path': 'data.translation.text', 'ui_order': 9}
    assert repo.commits == 1


def test_update_param_sends_field_path_for_camel_case_key():
    repo = _FakeParamRepo(api={'id': 1, 'param_code': 'text', 'direction': 'output'})
    _crud_service(repo).update_param(1, {'fieldPath': 'data.events[0].text'})
    assert repo.sent_fields == {'field_path': 'data.events[0].text'}


def test_update_param_does_not_send_field_path_for_device_param():
    """设备参数表无 field_path 列：设备分支不得下发该键（避免双口径 / 无效写）。"""
    repo = _FakeParamRepo(device={'id': 2, 'param_code': 'device_code'})
    result = _crud_service(repo).update_param(
        2, {'field_path': 'data.translation.text', 'ui_order': 3})

    assert result['success'] is True
    assert repo.sent_fields == {'ui_order': 3}


def test_update_fields_apply_to_api_param_model():
    """下发字段确实落到 AlgorithmApiParam PO（_apply_update_fields 按 hasattr 写值）。"""
    from algorithm_service.infrastructure.persistence._param_converters import (
        _apply_update_fields,
    )
    from algorithm_service.infrastructure.persistence.models import (
        AlgorithmApiParam, AlgorithmDeviceParam,
    )
    api_po = AlgorithmApiParam()
    _apply_update_fields(api_po, {'field_path': 'data.translation.text'})
    assert api_po.field_path == 'data.translation.text'

    # 设备 PO 无该属性：不抛异常、不产生属性（共用函数的既有语义）
    device_po = AlgorithmDeviceParam()
    _apply_update_fields(device_po, {'field_path': 'x'})
    assert not hasattr(device_po, 'field_path')


def test_api_param_dto_keeps_field_path_device_dto_does_not():
    """P2：task_service ACL 的 dict→DTO 投影（列表/详情读路径）不得丢 field_path。"""
    from dataclasses import asdict
    from shared.utils.dto_utils import dict_to_dto
    from task_service.domain.dto.task_acl_dto import ApiParamDTO, DeviceParamDTO

    payload = {'id': 1, 'algorithm_type': 'voice_llm', 'param_code': 'text',
               'direction': 'output', 'field_path': 'data.translation.text'}

    api_dto = dict_to_dto(payload, ApiParamDTO)
    assert api_dto.field_path == 'data.translation.text'
    assert asdict(api_dto)['field_path'] == 'data.translation.text'

    # 设备参数不加该字段，避免双口径
    assert 'field_path' not in {f.name for f in DeviceParamDTO.__dataclass_fields__.values()}


def test_list_params_returns_field_path():
    """GET /algorithm/params?param_type=api 的序列化结果含 field_path。"""
    from task_service.application.algorithm.algorithm_param_query_service import (
        AlgorithmParamQueryService,
    )
    from task_service.domain.dto.task_acl_dto import ApiParamDTO

    repo = _FakeParamRepo(api_list=[
        ApiParamDTO(id=1, algorithm_type='voice_llm', param_code='text',
                    direction='output', field_path='data.translation.text'),
        ApiParamDTO(id=2, algorithm_type='voice_llm', param_code='response_audio',
                    direction='output'),
    ])
    svc = AlgorithmParamQueryService.__new__(AlgorithmParamQueryService)
    svc.repo = repo
    result = svc.list_params(algorithm_type='voice_llm', param_type='api')

    items = result['data']['items']
    assert items[0]['field_path'] == 'data.translation.text'
    assert items[1]['field_path'] is None


def test_grpc_update_param_boundary_keeps_field_path():
    """进程内全链：UpdateParamRequest(JSON) → task_service servicer → service 白名单 → 下发字段。

    复刻打回 P1 的复现路径（不连库、不写库），只是把入口从直调 service 换成真实 gRPC 边界。
    """
    import json
    from shared.proto import task_service_pb2 as task_pb
    from task_service.interfaces.grpc.algorithm_config import (
        AlgorithmConfigServiceServicer,
    )

    repo = _FakeParamRepo(api={'id': 1, 'algorithm_type': 'voice_llm',
                               'param_code': 'text', 'direction': 'output'})
    servicer = AlgorithmConfigServiceServicer()
    servicer._svc = _crud_service(repo)

    resp = servicer.UpdateParam(task_pb.UpdateParamRequest(
        param_id=1,
        data=json.dumps({'field_path': 'data.translation.text', 'uiOrder': 9}),
    ))

    assert resp.success is True
    assert repo.sent_fields == {'field_path': 'data.translation.text', 'ui_order': 9}
