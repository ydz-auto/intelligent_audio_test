# -*- coding: utf-8 -*-
"""INT-2355 单测：无关联算法的维度不得写任何 ParamMapping。

缺陷：``get_default_algorithm_type([])`` 回落 ``'voice_llm'``，导致
``associated_algorithms: []`` 的评估维度在建/改时把 input/output 参数映射
写进真实在用算法（INT-2336 复现：维度 558 → voice_llm 新增 248 行）。

修复口径：
1. 无关联算法（含条目缺 algorithm_type）→ 默认算法为 None；
2. 命令层 algorithm_type 为空 → 跳过 input/output 两个方向的映射同步，
   维度参数本身照常保存；
3. update 未携带关联算法时按库内现有关系取默认算法，显式空列表 = 清空关联；
4. algorithm_service 的 SyncParamMappings / sync_for_dimension 缺
   algorithm_type 时拒绝，而不是回落真实算法名。
"""
import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from evaluation_service.application.commands._command_utils import (  # noqa: E402
    get_default_algorithm_type,
)
from evaluation_service.application.commands.evaluation_command_service import (  # noqa: E402
    EvaluationCommandService,
)


# ==================== 1. 默认算法解析 ====================

class TestGetDefaultAlgorithmType:
    def test_empty_returns_none(self):
        assert get_default_algorithm_type(None) is None
        assert get_default_algorithm_type([]) is None

    def test_entry_without_type_returns_none(self):
        assert get_default_algorithm_type([{}, {'weight': 1.0}]) is None

    def test_dto_relations_supported(self):
        """GetRelationsByDimension 返回 DTO，也要能取到默认算法。"""
        from evaluation_service.domain.dto import DimensionRelationDTO
        got = get_default_algorithm_type([
            DimensionRelationDTO(algorithm_type='asr', is_default=False),
            DimensionRelationDTO(algorithm_type='voice_llm', is_default=True),
        ])
        assert got == 'voice_llm'


# ==================== 2. 命令层：create ====================

def _fake_service(dimension=None, relations=None):
    repo = MagicMock()
    repo.max_main_sort_order.return_value = 0
    repo.max_sub_sort_order.return_value = 0
    dim = dimension or SimpleNamespace(id=101, api_settings=None)
    repo.create_dimension.return_value = dim
    repo.get_dimension.return_value = dim
    repo.list_relations_by_dimension.return_value = relations or []
    return EvaluationCommandService(repo=repo), repo


_PAYLOAD = {
    'name': '矩阵测试_INT2355_无关联维度',
    'type': 'auto',
    'result_type': 1,
    'required_inputs': [
        {'key': 'q2355_in', 'param_name': '输入', 'field_type': 'text'},
    ],
    'output_fields': [
        {'param_code': 'o2355_out', 'param_name': '输出',
         'field_path': 'data.o2355_out', 'field_type': 'number'},
    ],
}


class TestCreateDimensionWithoutAlgorithm:
    def test_no_relations_writes_no_param_mappings(self):
        svc, repo = _fake_service()
        resp = svc.create_dimension(dict(_PAYLOAD, associated_algorithms=[]))

        assert resp['success'] is True
        # input / output 两个方向都不写映射
        assert repo.sync_param_mappings.call_count == 0
        # 维度参数本身照常保存（input + output 各一条）
        assert repo.add_dimension_param.call_count == 2
        repo.sync_relations.assert_called_once_with(101, [])

    def test_missing_relations_key_also_writes_no_mappings(self):
        svc, repo = _fake_service()
        resp = svc.create_dimension(dict(_PAYLOAD))

        assert resp['success'] is True
        assert repo.sync_param_mappings.call_count == 0

    def test_explicit_relation_keeps_behavior(self):
        svc, repo = _fake_service()
        resp = svc.create_dimension(dict(
            _PAYLOAD,
            associated_algorithms=[{'algorithm_type': 'asr', 'is_default': True}],
        ))

        assert resp['success'] is True
        assert repo.sync_param_mappings.call_count == 2
        algorithm_types = {c.args[3] for c in repo.sync_param_mappings.call_args_list}
        assert algorithm_types == {'asr'}
        directions = {c.args[2] for c in repo.sync_param_mappings.call_args_list}
        assert directions == {'input', 'output'}


# ==================== 3. 命令层：update ====================

def _existing_dimension():
    return SimpleNamespace(
        id=101, deleted=False, visibility='shared',
        created_by_user_id=None, dimension_type=None, api_settings=None)


class TestUpdateDimension:
    def test_explicit_empty_relations_clears_and_writes_no_mappings(self):
        svc, repo = _fake_service(dimension=_existing_dimension())
        resp = svc.update_dimension(101, dict(
            _PAYLOAD, associated_algorithms=[]))

        assert resp['success'] is True, resp
        repo.sync_relations.assert_called_once_with(101, [])
        assert repo.sync_param_mappings.call_count == 0
        # 显式空列表不应去查库内关系
        repo.list_relations_by_dimension.assert_not_called()

    def test_absent_relations_uses_existing_relation_not_default(self):
        svc, repo = _fake_service(
            dimension=_existing_dimension(),
            relations=[{'algorithm_type': 'asr', 'is_default': True}],
        )
        resp = svc.update_dimension(101, dict(_PAYLOAD))

        assert resp['success'] is True, resp
        repo.sync_relations.assert_not_called()
        repo.list_relations_by_dimension.assert_called_once_with(101)
        assert repo.sync_param_mappings.call_count == 2
        algorithm_types = {c.args[3] for c in repo.sync_param_mappings.call_args_list}
        assert algorithm_types == {'asr'}

    def test_absent_relations_and_no_db_relation_writes_no_mappings(self):
        svc, repo = _fake_service(
            dimension=_existing_dimension(), relations=[])
        resp = svc.update_dimension(101, dict(_PAYLOAD))

        assert resp['success'] is True, resp
        assert repo.sync_param_mappings.call_count == 0


# ==================== 4. algorithm_service 侧拒绝缺省 algorithm_type ====================

def test_sync_for_dimension_rejects_missing_algorithm_type():
    from algorithm_service.infrastructure.persistence.algorithm_repository import (
        param_mapping_query_repository,
    )
    with pytest.raises(ValueError):
        param_mapping_query_repository.sync_for_dimension(
            101, [{'param_code': 'q2355_in'}], direction='input')


def test_grpc_sync_param_mappings_without_algorithm_type_is_rejected(monkeypatch):
    from algorithm_service.infrastructure.persistence.algorithm_repository import (
        param_mapping_query_repository,
    )
    from algorithm_service.interfaces.grpc.mixins.dimension_mixin import _DimensionMixin

    called = []
    monkeypatch.setattr(
        param_mapping_query_repository, 'sync_for_dimension',
        lambda *a, **kw: called.append((a, kw)))

    resp = _DimensionMixin.SyncParamMappings(
        _DimensionMixin(),
        SimpleNamespace(
            dimension_id=101,
            data=json.dumps({'params': [{'param_code': 'q2355_in'}],
                             'direction': 'input'}),
        ),
    )

    assert resp.success is False
    assert 'algorithm_type' in resp.message
    assert called == [], '缺 algorithm_type 时不得落库'
