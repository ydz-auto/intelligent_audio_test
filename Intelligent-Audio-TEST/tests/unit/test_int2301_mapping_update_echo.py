# -*- coding: utf-8 -*-
"""INT-2301：PUT /algorithm/mappings/{id} 响应体必须回显更新后的值。

历史缺陷：task_service `update_mapping()` 先 `get_mapping()` 取快照 → 调
`update_mapping_attrs()`（gRPC，写库）→ 仍用同一个未刷新的快照对象拼响应，
导致响应 data 是更新前值，与库/随后 GET 不一致。

修复口径：
- ACL `update_mapping_attrs()` 返回 gRPC UpdateMapping 响应里的更新后 DTO；
- 服务层只把该返回值的白名单字段合入响应视图（不合入请求体），缺失时回落到
  更新前快照，且不额外发 GetMapping。

覆盖：
1. 更新后值回显（含 source / target_param / transform_type / dimension_id）；
2. dimension_name 按更新后的 dimension_id 解析；
3. ACL 无回读数据（None）→ 回落旧快照，不误清零；
4. 空 body / 只带 id 的 PUT → 值不变；
5. 请求体里未生效的键不进入响应（白名单）；
6. ACL 层：解析 UpdateMapping 响应为 DTO；响应无 data 返回 None；失败抛错。
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from types import SimpleNamespace

from shared.proto import algorithm_service_pb2 as _pb

from task_service.application.algorithm.algorithm_param_crud_service import (
    AlgorithmParamCrudService,
    MAPPING_ECHO_FIELDS,
)
from task_service.domain.dto.task_acl_dto import ParamMappingDTO
from task_service.infrastructure.acl import (
    algorithm_acl_mapping_dimension_mixin as mapping_mixin,
)
from task_service.infrastructure.acl.algorithm_acl_mapping_dimension_mixin import (
    AlgorithmMappingDimensionMixin,
)

ALGO = 'voice_llm'
OLD = dict(
    id=77,
    algorithm_type=ALGO,
    source='case',
    source_param='text',
    source_direction='output',
    dimension_id=11,
    target_param='asr_text',
    transform_type='none',
)


def _old_dto(**overrides):
    fields = dict(OLD)
    fields.update(overrides)
    return ParamMappingDTO(**fields)


class FakeRepo:
    """最小仓储桩：get_mapping / update_mapping_attrs / 维度查询 / 事务占位。"""

    def __init__(self, row, updated=None):
        self.row = row
        self.updated = updated
        self.calls = []
        self.committed = False
        self.rolled_back = False
        self.dimensions = {11: SimpleNamespace(id=11, name='旧维度'),
                           22: SimpleNamespace(id=22, name='新维度')}

    def get_mapping(self, mapping_id):
        self.calls.append(('get_mapping', mapping_id))
        return self.row

    def update_mapping_attrs(self, mapping, data):
        self.calls.append(('update_mapping_attrs', dict(data)))
        return self.updated

    def get_dimension_by_id(self, dim_id):
        self.calls.append(('get_dimension_by_id', dim_id))
        return self.dimensions.get(int(dim_id))

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def _make_service(repo):
    svc = AlgorithmParamCrudService.__new__(AlgorithmParamCrudService)
    svc.repo = repo
    return svc


# ==================== 服务层：回显更新后的值 ====================

def test_update_mapping_echoes_updated_values():
    row = _old_dto()
    updated = _old_dto(
        source='api',
        target_param='content',
        transform_type='json_path',
    )
    repo = FakeRepo(row, updated)
    result = _make_service(repo).update_mapping(77, {'target_param': 'content'})

    assert result['success'] is True
    data = result['data']
    assert data['source'] == 'api'
    assert data['target_param'] == 'content'
    assert data['transform_type'] == 'json_path'
    # 未变更的字段保持原值
    assert data['algorithm_type'] == ALGO
    assert data['source_param'] == 'text'
    assert data['source_direction'] == 'output'
    assert data['dimension_id'] == 11
    assert data['dimension_name'] == '旧维度'
    assert repo.committed is True


def test_update_mapping_echoes_new_dimension_and_name():
    row = _old_dto()
    updated = _old_dto(dimension_id=22)
    repo = FakeRepo(row, updated)
    result = _make_service(repo).update_mapping(77, {'dimension_id': 22})

    data = result['data']
    assert data['dimension_id'] == 22
    # 维度名必须按更新后的 dimension_id 解析，而不是旧快照
    assert data['dimension_name'] == '新维度'
    assert ('get_dimension_by_id', 22) in repo.calls


def test_update_mapping_no_extra_get_back():
    """回读复用 UpdateMapping 响应，不再额外发一次 GetMapping。"""
    row = _old_dto()
    repo = FakeRepo(row, _old_dto(source='device'))
    _make_service(repo).update_mapping(77, {'source_type': 'device'})

    assert [c for c in repo.calls if c[0] == 'get_mapping'] == [('get_mapping', 77)]


def test_update_mapping_falls_back_to_snapshot_when_acl_has_no_data():
    row = _old_dto()
    repo = FakeRepo(row, updated=None)
    result = _make_service(repo).update_mapping(77, {'target_param': 'x'})

    data = result['data']
    assert data['source'] == 'case'
    assert data['target_param'] == 'asr_text'
    assert data['transform_type'] == 'none'
    assert data['dimension_id'] == 11


def test_update_mapping_empty_body_keeps_values():
    row = _old_dto()
    repo = FakeRepo(row, _old_dto())
    result = _make_service(repo).update_mapping(77, {})

    data = result['data']
    for field in MAPPING_ECHO_FIELDS:
        assert data[field] == getattr(row, field)


def test_update_mapping_response_keys_are_whitelisted():
    """请求体里的键不会原样进入响应（只认服务端回写值）。"""
    row = _old_dto()
    repo = FakeRepo(row, _old_dto())
    result = _make_service(repo).update_mapping(
        77, {'source_type': 'api', 'unknown_field': 'polluted'}
    )

    data = result['data']
    assert set(data) == set(MAPPING_ECHO_FIELDS) | {'dimension_name'}
    assert 'source_type' not in data
    assert 'unknown_field' not in data
    # ACL 未回写 → 保持旧值，不把请求体当作已生效
    assert data['source'] == 'case'


def test_update_mapping_dict_shaped_row():
    """仓储兼容 dict 形态行（历史实现两种返回形态都存在）。"""
    repo = FakeRepo(dict(OLD), dict(OLD, target_param='content'))
    result = _make_service(repo).update_mapping(77, {'target_param': 'content'})
    assert result['data']['target_param'] == 'content'
    assert result['data']['source'] == 'case'


def test_update_mapping_not_found():
    repo = FakeRepo(None)
    result = _make_service(repo).update_mapping(999, {})
    assert result == {'success': False, 'message': 'Mapping not found', 'code': 404}


# ==================== ACL 层：解析 UpdateMapping 响应 ====================

class _FakeStub:
    def __init__(self, resp):
        self.resp = resp
        self.requests = []

    def UpdateMapping(self, request):
        self.requests.append(request)
        return self.resp


def test_acl_update_mapping_attrs_returns_updated_dto(monkeypatch):
    payload = dict(OLD, source='api', target_param='content')
    stub = _FakeStub(_pb.AlgorithmResponse(
        success=True, message='ok',
        data=json.dumps(payload, ensure_ascii=False),
    ))
    monkeypatch.setattr(mapping_mixin, '_get_stub', lambda: stub)

    result = AlgorithmMappingDimensionMixin().update_mapping_attrs(
        _old_dto(), {'source_type': 'api'}
    )

    assert isinstance(result, ParamMappingDTO)
    assert result.id == 77
    assert result.source == 'api'
    assert result.target_param == 'content'
    # 写请求仍按原口径携带 id + JSON body
    assert stub.requests[0].mapping_id == 77
    assert json.loads(stub.requests[0].data) == {'source_type': 'api'}


def test_acl_update_mapping_attrs_returns_none_without_data(monkeypatch):
    stub = _FakeStub(_pb.AlgorithmResponse(success=True, message='ok', data=''))
    monkeypatch.setattr(mapping_mixin, '_get_stub', lambda: stub)

    result = AlgorithmMappingDimensionMixin().update_mapping_attrs(
        _old_dto(), {'target_param': 'x'}
    )
    assert result is None


def test_acl_update_mapping_attrs_raises_on_failure(monkeypatch):
    stub = _FakeStub(_pb.AlgorithmResponse(success=False, message='不存在'))
    monkeypatch.setattr(mapping_mixin, '_get_stub', lambda: stub)

    with pytest.raises(RuntimeError, match='不存在'):
        AlgorithmMappingDimensionMixin().update_mapping_attrs(_old_dto(), {})
