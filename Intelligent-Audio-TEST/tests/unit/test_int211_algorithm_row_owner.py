# -*- coding: utf-8 -*-
"""INT-211 后端加固测试：_update_params/_update_case_params/_update_mappings id 分支行归属校验。

历史缺陷：算法复制链路（前端 handleClone）原样透传源算法各行真实 id，后端 id 对账分支
按全局 id 取行且不校验 algorithm_type 归属，副本保存静默改写源算法参数行。前端已修复为
剔除行级 id（副本走纯新建路径），本卡同时对后端 id 分支加归属校验（防御性收口）：
跨算法 id 直接抛 ValueError，使 create/update 整体失败回滚，而非静默改写他算法的行。

覆盖：
1. 跨算法行 id：device/api 参数、用例参数、映射三处 id 分支均拒绝，且不产生任何更新；
2. 属于目标算法的行 id：照常对账更新（正常保存路径不受影响）；
3. dict 形态行（仓储兼容两种返回形态）同样被校验；
4. 旧复制载荷（携带源算法行 id）走 create_algorithm → 整体失败、源行零改写、不提交；
5. 修复后复制载荷（不含行级 id）走 create_algorithm → 副本纯新建自己的行（含维度关联）。
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

SOURCE_TYPE = 'voice_llm'
CLONE_TYPE = 'voice_llm_copy'


class FakeAlgorithmRepo:
    """最小内存仓储桩：仅实现本测试路径所需方法。"""

    def __init__(self):
        self.updated = []   # (row_id, fields)
        self.created = []   # (kind, data)
        self.deleted = []   # (kind, row_id)
        self.committed = False
        self.device_rows = {}
        self.case_rows = {}
        self.mapping_rows = {}
        self._created_def = None

    # ---- 算法定义 ----
    def find_algorithm_by_type(self, algo_type):
        if self._created_def is not None and self._created_def.type == algo_type:
            return self._created_def
        return None

    def create_algorithm_definition(self, data):
        self._created_def = SimpleNamespace(
            id=999, type=data.get('type'), name=data.get('name'),
            group_id=data.get('group_id'), group_name=None,
            description=data.get('description'), status=data.get('status', 'online'),
            icon=None, display_order=data.get('display_order', 0),
            created_at='2026-10-12', updated_at='2026-10-12',
        )
        return self._created_def

    # ---- 列表查询（副本面向空行集）----
    def list_device_params(self, algorithm_type=None):
        return []
    def list_api_params(self, algorithm_type=None):
        return []
    def list_case_params(self, algorithm_type=None):
        return []
    def list_mappings(self, algorithm_type=None, source_type=None, dimension_id=None):
        return []
    def list_dimension_relations(self, algo_type):
        return []
    def list_reference_params(self, algo_type):
        return []

    # ---- 单行查询 ----
    def get_device_param(self, param_id):
        return self.device_rows.get(int(param_id))
    def get_api_param(self, param_id):
        return self.device_rows.get(int(param_id))
    def get_case_param(self, param_id):
        return self.case_rows.get(int(param_id))
    def get_mapping(self, mapping_id):
        return self.mapping_rows.get(int(mapping_id))

    # ---- 按码查找（新建算法无既有行）----
    def find_device_param_by_code(self, algorithm_type, param_code, direction):
        return None
    def find_api_param_by_code(self, algorithm_type, param_code, direction):
        return None
    def find_case_param_by_code(self, algorithm_type, param_code, deleted=False):
        return None

    # ---- 写操作 ----
    def create_device_param(self, data):
        self.created.append(('device', data))
        return data
    def create_api_param(self, data):
        self.created.append(('api', data))
        return data
    def create_case_param(self, data):
        self.created.append(('case', data))
        return data
    def create_mapping(self, data):
        self.created.append(('mapping', data))
        return data
    def create_dimension_relation(self, data):
        self.created.append(('relation', data))
        return data

    def update_param_attrs(self, param, fields):
        row_id = param.get('id') if isinstance(param, dict) else getattr(param, 'id', None)
        self.updated.append((row_id, fields))
    def update_mapping_attrs(self, mapping, data):
        self.updated.append((getattr(mapping, 'id', None), data))

    def soft_delete_param(self, param):
        row_id = param.get('id') if isinstance(param, dict) else getattr(param, 'id', None)
        self.deleted.append(('param', row_id))
    def soft_delete_mapping(self, mapping):
        self.deleted.append(('mapping', getattr(mapping, 'id', None)))

    def commit(self):
        self.committed = True
    def rollback(self):
        pass


def _make_service(repo):
    svc = AlgorithmCrudService.__new__(AlgorithmCrudService)
    svc.repo = repo
    return svc


# ==================== _update_params（device/api） ====================

def test_update_params_rejects_cross_algorithm_device_row_id():
    repo = FakeAlgorithmRepo()
    repo.device_rows[12] = DeviceParamDTO(id=12, algorithm_type=SOURCE_TYPE, param_code='audio_channel')
    svc = _make_service(repo)

    with pytest.raises(ValueError) as exc_info:
        svc._update_params(CLONE_TYPE, [{'id': 12, 'param_code': 'audio_channel'}], 'device')

    assert SOURCE_TYPE in str(exc_info.value)
    assert CLONE_TYPE in str(exc_info.value)
    assert repo.updated == []  # 未发生任何静默改写


def test_update_params_allows_own_algorithm_row_id():
    repo = FakeAlgorithmRepo()
    repo.device_rows[12] = DeviceParamDTO(id=12, algorithm_type=CLONE_TYPE, param_code='audio_channel')
    svc = _make_service(repo)

    svc._update_params(CLONE_TYPE, [{'id': 12, 'param_name': '声道(改)'}], 'device')

    assert repo.updated == [(12, {'param_name': '声道(改)'})]


def test_update_params_validates_dict_shaped_row():
    repo = FakeAlgorithmRepo()
    # 仓储层兼容 dict 形态返回（update_param_attrs 等辅助均做 isinstance 双分支）
    repo.device_rows[7] = {'id': 7, 'algorithm_type': SOURCE_TYPE, 'param_code': 'p'}
    svc = _make_service(repo)

    with pytest.raises(ValueError):
        svc._update_params(CLONE_TYPE, [{'id': 7}], 'device')
    assert repo.updated == []


def test_update_case_params_rejects_cross_algorithm_row_id():
    repo = FakeAlgorithmRepo()
    repo.case_rows[21] = CaseParamDTO(id=21, algorithm_type=SOURCE_TYPE, param_code='lang')
    svc = _make_service(repo)

    with pytest.raises(ValueError):
        svc._update_case_params(CLONE_TYPE, [{'id': 21, 'param_name': '语言(改)'}])
    assert repo.updated == []


def test_update_case_params_allows_own_algorithm_row_id():
    repo = FakeAlgorithmRepo()
    repo.case_rows[21] = CaseParamDTO(id=21, algorithm_type=CLONE_TYPE, param_code='lang')
    svc = _make_service(repo)

    svc._update_case_params(CLONE_TYPE, [{'id': 21, 'param_name': '语言(改)'}])

    assert repo.updated == [(21, {'param_name': '语言(改)'})]


def test_update_mappings_rejects_cross_algorithm_row_id():
    repo = FakeAlgorithmRepo()
    repo.mapping_rows[31] = ParamMappingDTO(id=31, algorithm_type=SOURCE_TYPE, source_param='asr_text', target_param='text')
    svc = _make_service(repo)

    with pytest.raises(ValueError):
        svc._update_mappings(CLONE_TYPE, {'device': [{'id': 31, 'source_param': 'asr_text', 'target_param': 'text'}]})
    assert repo.updated == []


# ==================== create_algorithm 整体行为 ====================

def test_create_algorithm_with_legacy_clone_payload_fails_and_never_touches_source_rows():
    """旧复制载荷（携带源算法行 id）→ 整体失败回滚，源算法行零改写、不提交。"""
    repo = FakeAlgorithmRepo()
    repo.device_rows[12] = DeviceParamDTO(id=12, algorithm_type=SOURCE_TYPE, param_code='audio_channel')
    repo.case_rows[21] = CaseParamDTO(id=21, algorithm_type=SOURCE_TYPE, param_code='lang')
    svc = _make_service(repo)

    result = svc.create_algorithm({
        'type': CLONE_TYPE,
        'name': '语音大模型 (副本)',
        'device_params': [{'id': 12, 'param_code': 'audio_channel'}],
        'case_params': [{'id': 21, 'param_code': 'lang'}],
    })

    assert result['success'] is False
    assert 'voice_llm_copy' in result['message']
    assert repo.updated == []
    assert repo.committed is False


def test_create_algorithm_with_idless_clone_payload_creates_own_rows():
    """修复后复制载荷（不含行级 id）→ 副本纯新建自己的参数行与维度关联。"""
    repo = FakeAlgorithmRepo()
    svc = _make_service(repo)

    result = svc.create_algorithm({
        'type': CLONE_TYPE,
        'name': '语音大模型 (副本)',
        'device_params': [{'param_code': 'audio_channel', 'param_name': '声道'}],
        'api_params': [{'param_code': 'api_lang', 'param_name': '语言'}],
        'case_params': [{'param_code': 'lang', 'param_name': '语言', 'scope': 'common'}],
        'mappings': {'device': [{'source_param': 'asr_text', 'target_param': 'text'}]},
        'associated_dimensions': [{'dimension_id': 8, 'weight': 1.0, 'is_default': False}],
    })

    assert result['success'] is True
    created_kinds = [kind for kind, _ in repo.created]
    assert created_kinds.count('device') == 1
    assert created_kinds.count('api') == 1
    assert created_kinds.count('case') == 1
    assert created_kinds.count('mapping') == 1
    assert created_kinds.count('relation') == 1
    # 新建行归属副本算法
    assert repo.created[0][1]['algorithm_type'] == CLONE_TYPE
    assert repo.created[2][1]['algorithm_type'] == CLONE_TYPE
    assert repo.updated == []
    assert repo.committed is True
