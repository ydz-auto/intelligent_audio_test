# -*- coding: utf-8 -*-
"""INT-1379 后端修复测试：POST /algorithm/bulk-delete 应真正软删算法定义。

历史缺陷：task_service 兼容层 AlgorithmDimensionRelationService.bulk_delete
只 list_algorithm_definitions_for_bulk_delete 收集 type 并返回 deleted_types，
从不调用 soft_delete_algorithm，导致 HTTP 报成功但记录残留（批量后列表/详情仍可见）。

修复：逐条调用 repo.soft_delete_algorithm（与单删 delete_algorithm 同一条 gRPC 路径）。

覆盖：
1. 批量删除 3 条：deleted_types 与实际落删一致、每条都调用 soft_delete、提交；
2. 空 algorithm_types：直接 400，不触发任何软删；
3. 只命中未删除项：软删调用数与命中数一致；
4. 软删中途抛异常：返回失败并回滚。
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from task_service.application.algorithm.algorithm_param_crud_service import (
    AlgorithmParamCrudService,
)


class FakeBulkDeleteRepo:
    """最小内存仓储桩：只实现 bulk_delete 路径所需方法。"""

    def __init__(self, defs):
        self.defs = list(defs)
        self.soft_deleted = []
        self.committed = False
        self.rolled_back = False
        self.fail_soft_delete_on = None

    def list_algorithm_definitions_for_bulk_delete(self, algorithm_types):
        # 模拟只返回未删除且 type 命中的记录
        return [d for d in self.defs if d['type'] in algorithm_types]

    def soft_delete_algorithm(self, algo_def):
        algo_id = algo_def.get('id') if isinstance(algo_def, dict) else getattr(algo_def, 'id', None)
        if self.fail_soft_delete_on is not None and algo_id == self.fail_soft_delete_on:
            raise RuntimeError('boom')
        self.soft_deleted.append(algo_id)

    def flush(self):
        pass

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def _make_service(repo):
    svc = AlgorithmParamCrudService.__new__(AlgorithmParamCrudService)
    svc.repo = repo
    return svc


def _defs(types):
    return [
        {'id': i, 'type': t}
        for i, t in enumerate(types, start=1)
    ]


def test_bulk_delete_actually_soft_deletes_each_found():
    repo = FakeBulkDeleteRepo(_defs(['jxcs_1', 'jxcs_2', 'jxcs_3']))
    svc = _make_service(repo)

    result = svc.bulk_delete({'algorithm_types': ['jxcs_1', 'jxcs_2', 'jxcs_3']})

    assert result['success'] is True
    assert result['data']['deleted_types'] == ['jxcs_1', 'jxcs_2', 'jxcs_3']
    assert repo.soft_deleted == [1, 2, 3]   # 每条都实际落软删
    assert repo.committed is True
    assert repo.rolled_back is False


def test_bulk_delete_only_soft_deletes_found_types():
    repo = FakeBulkDeleteRepo(_defs(['jxcs_1', 'jxcs_2']))
    svc = _make_service(repo)

    result = svc.bulk_delete({'algorithm_types': ['jxcs_1', 'jxcs_2', 'jxcs_missing']})

    assert result['success'] is True
    assert result['data']['deleted_types'] == ['jxcs_1', 'jxcs_2']
    assert repo.soft_deleted == [1, 2]   # 未命中的不调用软删
    assert repo.committed is True


def test_bulk_delete_empty_types_rejected_without_soft_delete():
    repo = FakeBulkDeleteRepo(_defs(['jxcs_1']))
    svc = _make_service(repo)

    result = svc.bulk_delete({})

    assert result['success'] is False
    assert result['code'] == 400
    assert repo.soft_deleted == []
    assert repo.committed is False


def test_bulk_delete_soft_delete_failure_rolls_back():
    repo = FakeBulkDeleteRepo(_defs(['jxcs_1', 'jxcs_2']))
    repo.fail_soft_delete_on = 2
    svc = _make_service(repo)

    result = svc.bulk_delete({'algorithm_types': ['jxcs_1', 'jxcs_2']})

    assert result['success'] is False
    assert 'boom' in result['message']
    assert repo.rolled_back is True
