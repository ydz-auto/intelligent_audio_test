# -*- coding: utf-8 -*-
"""INT-1896：algorithm_results 快照路径取真实算法类型（C6b api_id 输出声明接线）。

缺陷：``_result_group_mixin._build_and_store_algorithm_results`` 里
``algorithm_type = ''`` 从未赋值，``_load_output_fields`` / ``_load_device_output_fields``
在空串处短路 → 预提取快照恒为零声明，报告侧命中非空快照就不再走带 api_id 的
回退分支，INT-1757（C6b）在评估/报告快照路径上取不到声明。

覆盖：
1. 同一 algorithm_type 下两个 api_id（各一套 API 级输出声明）分别走快照路径，
   快照声明字段各自正确、互不覆盖；断言 ``_load_output_fields`` 以真实
   algorithm_type + 结果自身 api_id 调用。
2. api_id 为 None（设备/E2E 结果）：回落算法级声明，api_id=None 原样透传。
3. algorithm_type 取不到：保持改动前的空声明行为，但必须留 WARNING（不得静默）。
4. ``_resolve_result_algorithm_type`` 的口径：结果行值优先（用例软删也能取），
   行值缺失回落用例详情，都取不到返回空。
"""
import importlib
import os
import tempfile
from types import SimpleNamespace

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int1896_t_') + '/guard.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from evaluation_service.domain.dto.evaluation_acl_dto import (
    TestCaseDetailDTO,
    TestResultDTO,
)
from evaluation_service.infrastructure.persistence import _result_group_mixin as group_mod
from evaluation_service.infrastructure.persistence._result_group_mixin import GroupResultMixin

# 注意：包级 ``evaluation_service.infrastructure.acl.algorithm_acl_repository``
# 是仓储单例（被同名子模块遮蔽），要打桩的是子模块里的 AlgorithmAclRepository 类
_ALGO_ACL_MODULE = importlib.import_module(
    'evaluation_service.infrastructure.acl.algorithm_acl_repository')

ALGORITHM_TYPE = 'voice_llm'

# API 级声明：两个 API 实例各一套（同一 algorithm_type）
API_OUTPUT_DECLS = {
    11: [{'target_param': 'translation_text', 'param_type': 'text', 'label': '译文'}],
    12: [{'target_param': 'asr_text', 'param_type': 'text', 'label': '识别文本'}],
}
# 算法级声明（api_id 缺失时的回落口径）
ALGO_OUTPUT_DECLS = [
    {'target_param': 'translation_text', 'param_type': 'text', 'label': '算法级译文'},
]


class _Host(GroupResultMixin):
    """最小宿主：绕开 DB / 文件 IO，只留快照构建链路。"""

    def __init__(self):
        self.logs = []
        self.stored = []

    def _log(self, level='INFO', content='', **kwargs):
        self.logs.append({'level': level, 'content': content, **kwargs})

    # 本地 DB / gRPC 资源名查询走桩
    # INT-1809（C2）：签名随生产路径带上内存 payload 缓存，桩一并跟随
    def _load_dim_result_rows(self, result_id, payload_context=None):
        return []

    def _resolve_resource_name(self, result_id, device_id, api_id):
        return f'api_{api_id}' if api_id else f'result_{result_id}'

    @property
    def warnings(self):
        return [log for log in self.logs if log.get('level') == 'WARNING']


def _patch_env(monkeypatch, result, test_case, *, output_calls, device_calls):
    """打桩：task 侧 gRPC 读取 + 算法 ACL 声明 + result_data_store。"""
    monkeypatch.setattr(group_mod.task_acl_repository, 'get_test_result_by_id',
                        lambda result_id: result)
    monkeypatch.setattr(group_mod.task_acl_repository, 'get_test_case_detail',
                        lambda tc_id: test_case)
    monkeypatch.setattr(group_mod.task_acl_repository, 'get_task_by_id',
                        lambda task_id: None)

    def _fake_get_output_fields(self, algorithm_type, test_type=None, api_id=None):
        output_calls.append({'algorithm_type': algorithm_type, 'api_id': api_id})
        if api_id is None:
            return list(ALGO_OUTPUT_DECLS)
        return list(API_OUTPUT_DECLS.get(int(api_id), []))

    monkeypatch.setattr(_ALGO_ACL_MODULE.AlgorithmAclRepository,
                        'get_output_fields', _fake_get_output_fields)

    def _fake_get_device_output_fields(algorithm_type):
        device_calls.append(algorithm_type)
        return []

    import shared.clients.grpc_clients as grpc_clients
    monkeypatch.setattr(grpc_clients, 'algo_get_device_output_fields',
                        _fake_get_device_output_fields)

    import shared.utils.result_data_store as store
    monkeypatch.setattr(store, 'load_full_result_data',
                        lambda raw, path: raw if isinstance(raw, dict) else {})
    monkeypatch.setattr(store, 'split_result_data',
                        lambda data: (dict(data), False))
    monkeypatch.setattr(store, 'write_result_data_file',
                        lambda *a, **k: pytest.fail('轻量快照不应写文件'))


def _run_snapshot(host, monkeypatch, result, test_case, *, task_id=9, test_case_id='TC-9'):
    output_calls, device_calls = [], []
    _patch_env(monkeypatch, result, test_case,
               output_calls=output_calls, device_calls=device_calls)

    def _fake_update(result_id, lightweight, path):
        host.stored.append({'result_id': result_id,
                            'data': lightweight, 'path': path})
        return True

    monkeypatch.setattr(group_mod.task_acl_repository, 'update_test_result_data',
                        _fake_update)
    host._build_and_store_algorithm_results(result['id'] if isinstance(result, dict)
                                            else result.id, task_id, test_case_id)
    return output_calls, device_calls


def _result(api_id, **kwargs):
    defaults = dict(
        id=501, task_id=9, test_case_id='TC-9', api_id=api_id,
        algorithm_result={'translation_text': 'A', 'asr_text': 'B'},
        result_data={'kept': True}, result_data_path=None,
    )
    defaults.update(kwargs)
    return TestResultDTO(**defaults)


@pytest.mark.parametrize(
    'api_id, expected_code, other_code',
    [(11, 'translation_text', 'asr_text'), (12, 'asr_text', 'translation_text')])
def test_snapshot_declarations_scoped_by_api_id(monkeypatch, api_id,
                                                expected_code, other_code):
    """两个 api_id 各一套声明：快照只含本 API 声明，互不覆盖。"""
    host = _Host()
    tc = TestCaseDetailDTO(id='TC-9', algorithm_type=ALGORITHM_TYPE)
    output_calls, device_calls = _run_snapshot(host, monkeypatch, _result(api_id), tc)

    assert len(host.stored) == 1, host.logs
    algorithm_results = host.stored[0]['data']['algorithm_results']
    codes = [item['param_code'] for item in algorithm_results]
    assert expected_code in codes
    assert other_code not in codes
    # 声明 label 来自本 API 的声明（不是算法级、也不是另一家的）
    matched = next(i for i in algorithm_results if i['param_code'] == expected_code)
    assert matched['label'] == API_OUTPUT_DECLS[api_id][0]['label']
    assert matched['value'] == ('A' if expected_code == 'translation_text' else 'B')
    # 真实 algorithm_type + 结果自身 api_id 透传到算法 ACL
    assert output_calls == [{'algorithm_type': ALGORITHM_TYPE, 'api_id': api_id}]
    assert device_calls == [ALGORITHM_TYPE]


def test_snapshot_without_api_id_uses_algorithm_level_declaration(monkeypatch):
    """api_id 为 None（设备/E2E 结果）：回落算法级声明，api_id 原样传 None。"""
    host = _Host()
    tc = TestCaseDetailDTO(id='TC-9', algorithm_type=ALGORITHM_TYPE)
    output_calls, _ = _run_snapshot(host, monkeypatch, _result(None), tc)

    assert output_calls == [{'algorithm_type': ALGORITHM_TYPE, 'api_id': None}]
    algorithm_results = host.stored[0]['data']['algorithm_results']
    matched = next(i for i in algorithm_results if i['param_code'] == 'translation_text')
    assert matched['label'] == '算法级译文'


def test_missing_algorithm_type_keeps_empty_and_warns(monkeypatch):
    """算法类型推不出来：空声明（改动前行为）+ WARNING，不得静默。"""
    host = _Host()
    output_calls, device_calls = _run_snapshot(
        host, monkeypatch, _result(11, algorithm_result={}), None)

    assert host.stored[0]['data']['algorithm_results'] is None
    # 空算法类型：两个声明查询都在空串处短路，与改动前完全一致（不发起 ACL 调用）
    assert output_calls == []
    assert device_calls == []
    assert any('缺算法类型' in log['content'] for log in host.warnings), host.logs
    warn = next(log for log in host.warnings if '缺算法类型' in log['content'])
    assert 'result_id=501' in warn['content'] and 'test_case_id=TC-9' in warn['content']


def test_resolve_algorithm_type_falls_back_to_test_result_case_id(monkeypatch):
    """调用方没传 test_case_id 时用 test_result.test_case_id 取用例。"""
    seen = []

    def _fake_detail(tc_id):
        seen.append(tc_id)
        return TestCaseDetailDTO(id=tc_id, algorithm_type='  voice_llm  ')

    monkeypatch.setattr(group_mod.task_acl_repository, 'get_test_case_detail', _fake_detail)

    result = _result(11)
    assert GroupResultMixin._resolve_result_algorithm_type(result) == ALGORITHM_TYPE
    assert seen == ['TC-9']


def test_resolve_algorithm_type_empty_without_case_id(monkeypatch):
    """无用例 ID / 用例不存在 / 声明为空 → 空串（由调用方记 WARNING）。"""
    monkeypatch.setattr(group_mod.task_acl_repository, 'get_test_case_detail',
                        lambda tc_id: None)

    assert GroupResultMixin._resolve_result_algorithm_type(
        _result(11, test_case_id=None)) == ''
    assert GroupResultMixin._resolve_result_algorithm_type(
        _result(11), 'TC-9') == ''


def test_snapshot_uses_result_row_algorithm_type_when_case_gone(monkeypatch):
    """结果行自带 algorithm_type 优先：用例已软删（GetTestCaseDetail 取不到）也能出声明。

    主库现存的 13 条 api 结果即此形态（所引用用例均已软删），若只按用例推断
    会全部退化为零声明。
    """
    host = _Host()
    output_calls, _ = _run_snapshot(
        host, monkeypatch, _result(11, algorithm_type=ALGORITHM_TYPE), None)

    assert output_calls == [{'algorithm_type': ALGORITHM_TYPE, 'api_id': 11}]
    codes = [i['param_code'] for i in host.stored[0]['data']['algorithm_results']]
    assert codes == ['translation_text']
    assert host.warnings == []


def test_resolve_prefers_result_row_value_over_case(monkeypatch):
    """结果行有值时不查用例（零额外跨服务调用），行值去除首尾空白。"""
    def _fake_detail(tc_id):
        raise AssertionError('行值存在时不应查用例详情')

    monkeypatch.setattr(group_mod.task_acl_repository, 'get_test_case_detail', _fake_detail)

    assert GroupResultMixin._resolve_result_algorithm_type(
        _result(11, algorithm_type='  voice_llm ')) == ALGORITHM_TYPE


def test_resolve_falls_back_to_case_when_row_blank(monkeypatch):
    """结果行 algorithm_type 为空（历史数据）→ 回落用例详情口径。"""
    monkeypatch.setattr(group_mod.task_acl_repository, 'get_test_case_detail',
                        lambda tc_id: TestCaseDetailDTO(id=tc_id, algorithm_type='translation'))

    assert GroupResultMixin._resolve_result_algorithm_type(
        _result(11, algorithm_type='   ')) == 'translation'
