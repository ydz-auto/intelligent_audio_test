# -*- coding: utf-8 -*-
"""INT-218 后端测试：case_params 写链路 RPC 路由 + 整体保存失败语义。

历史缺陷（INT-210 验收发现）：`_update_case_params` 既有行误走 UpdateParam RPC
（设备/API 参数表），case_algorithm_params 行查不到 → 整体保存必 400
「Parameter id=43 不存在，无法更新」。更新分支已由 INT-198（03615545）修复，
本卡补齐同族残留并锁定路由契约：

1. RPC 路由：case_params 的 id 行 / 按码 dup 行 / 陈旧行软删，全部只允许走
   CaseParam 系列 RPC（update_case_param_attrs / soft_delete_case_param），
   绝不落设备/API 参数表（update_param_attrs / soft_delete_param）；
2. 整体保存（update_algorithm）含 case_params 既有行 id → 成功，不再 400；
3. 失败语义：gRPC 写逐条自动提交、rollback 为 no-op——
   - 写前预检（_preflight_row_refs）把 id 行归属校验失败提前到首条写之前，
     该类失败全成或全败、零部分写；
   - 残余中段失败时，失败信息必须明确列出已落库生效的步骤（不再静默）。

桩仓储按方法名记录调用，专用于断言「走了哪个 RPC」。
"""
import os
import sys

import pytest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from task_service.application.algorithm.algorithm_crud_service import AlgorithmCrudService
from task_service.domain.dto.task_acl_dto import CaseParamDTO, DeviceParamDTO, ParamMappingDTO

ALGO_TYPE = 'voice_llm'
OTHER_TYPE = 'asr_engine'


class RoutingRepoStub:
    """最小内存仓储桩：按方法名记录全部写调用，供 RPC 路由断言。"""

    def __init__(self):
        self.calls = []            # (method_name, *args)
        self.device_rows = {}
        self.case_rows = {}
        self.mapping_rows = {}
        self.existing_device = []
        self.existing_case = []
        self.existing_mappings = []
        self.definition = self._make_definition()
        self.raise_on = {}         # method_name -> exception

    @staticmethod
    def _make_definition():
        return SimpleNamespace(
            id=9, type=ALGO_TYPE, name='语音大模型', group_id=None, group_name=None,
            description=None, status='online', icon=None, display_order=0,
            created_at='2026-10-12', updated_at='2026-10-12',
        )

    # ---- 读 ----
    def find_algorithm_by_type(self, algo_type):
        if self.definition.type == algo_type:
            return self.definition
        return None

    def list_device_params(self, algorithm_type=None):
        return list(self.existing_device)

    def list_api_params(self, algorithm_type=None):
        return []

    def list_case_params(self, algorithm_type=None, scope=None):
        return list(self.existing_case)

    def list_mappings(self, algorithm_type=None, source_type=None, dimension_id=None):
        return list(self.existing_mappings)

    def list_dimension_relations(self, algo_type):
        return []

    def list_reference_params(self, algo_type):
        return []

    def get_device_param(self, param_id):
        return self.device_rows.get(int(param_id))

    def get_api_param(self, param_id):
        return None

    def get_case_param(self, param_id):
        return self.case_rows.get(int(param_id))

    def get_mapping(self, mapping_id):
        return self.mapping_rows.get(int(mapping_id))

    def find_device_param_by_code(self, algorithm_type, param_code, direction):
        return None

    def find_api_param_by_code(self, algorithm_type, param_code, direction):
        return None

    def find_case_param_by_code(self, algorithm_type, param_code, deleted=False):
        for row in self.case_rows.values():
            if row.algorithm_type == algorithm_type and row.param_code == param_code:
                return row
        return None

    # ---- 写（全部只记录不落库）----
    def create_device_param(self, data):
        self._write('create_device_param', data)
        return data

    def create_api_param(self, data):
        self._write('create_api_param', data)
        return data

    def create_case_param(self, data):
        self._write('create_case_param', data)
        return data

    def create_mapping(self, data):
        self._write('create_mapping', data)
        return data

    def create_dimension_relation(self, data):
        self._write('create_dimension_relation', data)
        return data

    def update_algorithm_definition_attrs(self, algo_def, data):
        self._write('update_algorithm_definition_attrs', algo_def.id)

    def create_algorithm_definition(self, data):
        self._write('create_algorithm_definition', data.get('type'))
        return self.definition

    def update_param_attrs(self, param, fields):
        self._write('update_param_attrs', self._rid(param), dict(fields))

    def update_case_param_attrs(self, param, fields):
        self._write('update_case_param_attrs', self._rid(param), dict(fields))

    def update_mapping_attrs(self, mapping, data):
        self._write('update_mapping_attrs', self._rid(mapping), dict(data))

    def soft_delete_param(self, param):
        self._write('soft_delete_param', self._rid(param))

    def soft_delete_case_param(self, param):
        self._write('soft_delete_case_param', self._rid(param))

    def soft_delete_mapping(self, mapping):
        self._write('soft_delete_mapping', self._rid(mapping))

    def soft_delete_dimension_relation(self, relation):
        self._write('soft_delete_dimension_relation', self._rid(relation))

    def commit(self):
        self.calls.append(('commit',))

    def rollback(self):
        self.calls.append(('rollback',))

    # ---- 辅助 ----
    def _write(self, method, *args):
        exc = self.raise_on.get(method)
        if exc is not None:
            raise exc
        self.calls.append((method, *args))

    @staticmethod
    def _rid(row):
        return row.get('id') if isinstance(row, dict) else getattr(row, 'id', None)

    def write_methods(self):
        return [c[0] for c in self.calls]


def _make_service(repo):
    svc = AlgorithmCrudService.__new__(AlgorithmCrudService)
    svc.repo = repo
    return svc


# ==================== 1. RPC 路由：case_params 只走 CaseParam 系列 RPC ====================

def test_case_param_id_row_updates_via_case_rpc():
    """id 对账分支必须走 update_case_param_attrs（INT-198 修复，本卡锁定路由契约）。"""
    repo = RoutingRepoStub()
    repo.case_rows[43] = CaseParamDTO(id=43, algorithm_type=ALGO_TYPE, param_code='lang')
    svc = _make_service(repo)

    svc._update_case_params(ALGO_TYPE, [{'id': 43, 'param_name': '语言(改)'}])

    assert ('update_case_param_attrs', 43, {'param_name': '语言(改)'}) in repo.calls
    assert 'update_param_attrs' not in repo.write_methods()


def test_case_param_by_code_row_updates_via_case_rpc():
    """无 id 按码对账 dup 行同样只走 update_case_param_attrs。"""
    repo = RoutingRepoStub()
    repo.case_rows[43] = CaseParamDTO(id=43, algorithm_type=ALGO_TYPE, param_code='lang')
    svc = _make_service(repo)

    svc._update_case_params(ALGO_TYPE, [{'param_code': 'lang', 'param_name': '语言(改)'}])

    assert ('update_case_param_attrs', 43, {'param_name': '语言(改)'}) in repo.calls
    assert 'update_param_attrs' not in repo.write_methods()


def test_case_param_stale_rows_deleted_via_case_rpc():
    """整体保存剔除的陈旧 case 行必须走 soft_delete_case_param（DeleteCaseParam RPC），
    绝不走 soft_delete_param（DeleteParam RPC——设备/API 表，id 撞车会误删他表行）。"""
    repo = RoutingRepoStub()
    repo.case_rows[1] = CaseParamDTO(id=1, algorithm_type=ALGO_TYPE, param_code='lang')
    repo.case_rows[2] = CaseParamDTO(id=2, algorithm_type=ALGO_TYPE, param_code='style')
    repo.existing_case = [repo.case_rows[1], repo.case_rows[2]]
    svc = _make_service(repo)

    svc._update_case_params(ALGO_TYPE, [{'id': 1, 'param_name': '语言(改)'}])

    assert ('soft_delete_case_param', 2) in repo.calls
    assert 'soft_delete_param' not in repo.write_methods()
    assert ('update_case_param_attrs', 1, {'param_name': '语言(改)'}) in repo.calls


# ==================== 2. 整体保存含 case 既有行 id → 成功，不再 400 ====================

def test_update_algorithm_with_case_param_id_row_succeeds():
    """INT-210 复测口径回归：update_algorithm 带 case_params 既有行 id（原必 400
    「Parameter id=43 不存在」）→ 成功且走 CaseParam RPC。"""
    repo = RoutingRepoStub()
    repo.case_rows[43] = CaseParamDTO(id=43, algorithm_type=ALGO_TYPE, param_code='lang')
    svc = _make_service(repo)

    result = svc.update_algorithm(ALGO_TYPE, {
        'name': '语音大模型(改)',
        'case_params': [{'id': 43, 'param_name': '语言(改)'}],
    })

    assert result['success'] is True
    assert ('update_case_param_attrs', 43, {'param_name': '语言(改)'}) in repo.calls
    assert 'update_param_attrs' not in repo.write_methods()


# ==================== 3. 失败语义：全成或全败 + 已生效项披露 ====================

def test_preflight_rejects_foreign_row_before_any_write():
    """预检把跨算法 id 拒绝在首条写之前：有效 device 行在前、跨算法 case 行在后
    → 整体失败且零写（连定义头都不改），该类失败全成或全败。"""
    repo = RoutingRepoStub()
    repo.device_rows[12] = DeviceParamDTO(id=12, algorithm_type=ALGO_TYPE, param_code='ch')
    repo.case_rows[21] = CaseParamDTO(id=21, algorithm_type=OTHER_TYPE, param_code='lang')
    svc = _make_service(repo)

    result = svc.update_algorithm(ALGO_TYPE, {
        'name': '语音大模型(改)',
        'device_params': [{'id': 12, 'param_name': '声道(改)'}],
        'case_params': [{'id': 21, 'param_name': '语言(改)'}],
    })

    assert result['success'] is False
    assert 'update_algorithm_definition_attrs' not in repo.write_methods()
    assert not any(m.startswith(('update_case', 'update_param', 'soft_delete', 'create_'))
                   for m in repo.write_methods())
    # 零已生效项 → 不附加部分写披露
    assert '已落库生效' not in result['message']


def test_midchain_failure_discloses_applied_steps():
    """残余中段失败（预检无法覆盖的写时错误）：失败信息必须明确列出已落库生效的
    步骤，杜绝「看到失败但部分改动已静默生效」。"""
    repo = RoutingRepoStub()
    repo.device_rows[12] = DeviceParamDTO(id=12, algorithm_type=ALGO_TYPE, param_code='ch')
    repo.case_rows[43] = CaseParamDTO(id=43, algorithm_type=ALGO_TYPE, param_code='lang')
    repo.raise_on['create_mapping'] = ValueError('mapping 写入失败')
    svc = _make_service(repo)

    result = svc.update_algorithm(ALGO_TYPE, {
        'device_params': [{'id': 12, 'param_name': '声道(改)'}],
        'case_params': [{'id': 43, 'param_name': '语言(改)'}],
        'mappings': {'device': [{'source_param': 'asr_text', 'target_param': 'text'}]},
    })

    assert result['success'] is False
    assert '已落库生效' in result['message']
    assert 'device_params(设备参数)' in result['message']
    assert 'case_params(用例参数)' in result['message']
    # 失败步骤本身（mappings）不在已生效清单
    assert 'mappings(参数映射)' not in result['message']
    # 已生效写入确实发生了
    assert ('update_case_param_attrs', 43, {'param_name': '语言(改)'}) in repo.calls


def test_failure_without_applied_steps_keeps_plain_message():
    """全败（无任何步骤生效）→ 保持原报错文案，不附加空披露。"""
    repo = RoutingRepoStub()
    repo.case_rows[21] = CaseParamDTO(id=21, algorithm_type=OTHER_TYPE, param_code='lang')
    svc = _make_service(repo)

    result = svc.update_algorithm(ALGO_TYPE, {
        'case_params': [{'id': 21, 'param_name': '语言(改)'}],
    })

    assert result['success'] is False
    assert result['message'].startswith('更新失败:')
    assert '已落库生效' not in result['message']


def test_create_algorithm_discloses_applied_steps_on_midchain_failure():
    """create_algorithm 同链路同语义：定义已建 + device 行已建后失败 → 披露已生效项。"""
    repo = RoutingRepoStub()
    repo.definition = SimpleNamespace(
        id=9, type='new_algo', name='x', group_id=None, group_name=None,
        description=None, status='online', icon=None, display_order=0,
        created_at='2026-10-12', updated_at='2026-10-12',
    )
    # 新建路径：算法尚未存在
    repo.find_algorithm_by_type = lambda algo_type: None
    repo.raise_on['create_case_param'] = ValueError('case 行写入失败')
    svc = _make_service(repo)

    result = svc.create_algorithm({
        'type': 'new_algo',
        'name': '新算法',
        'device_params': [{'param_code': 'ch', 'param_name': '声道'}],
        'case_params': [{'param_code': 'lang', 'param_name': '语言'}],
    })

    assert result['success'] is False
    assert '已落库生效' in result['message']
    assert 'device_params(设备参数)' in result['message']
    assert 'case_params(用例参数)' not in result['message']


# ==================== 4. 预检不改变正常保存路径 ====================

def test_preflight_allows_own_rows_and_save_succeeds():
    """全部 id 行归属本算法 → 预检放行，正常保存成功（INT-210 四列表口径不回退）。"""
    repo = RoutingRepoStub()
    repo.device_rows[12] = DeviceParamDTO(id=12, algorithm_type=ALGO_TYPE, param_code='ch')
    repo.case_rows[43] = CaseParamDTO(id=43, algorithm_type=ALGO_TYPE, param_code='lang')
    repo.mapping_rows[31] = ParamMappingDTO(id=31, algorithm_type=ALGO_TYPE, source_param='a', target_param='t')
    svc = _make_service(repo)

    result = svc.update_algorithm(ALGO_TYPE, {
        'device_params': [{'id': 12, 'param_name': '声道(改)'}],
        'case_params': [{'id': 43, 'param_name': '语言(改)'}],
        'mappings': {'device': [{'id': 31, 'target_param': 'text(改)'}]},
    })

    assert result['success'] is True
    assert ('update_param_attrs', 12, {'param_name': '声道(改)'}) in repo.calls
    assert ('update_case_param_attrs', 43, {'param_name': '语言(改)'}) in repo.calls
    assert ('update_mapping_attrs', 31, {'target_param': 'text(改)'}) in repo.calls
