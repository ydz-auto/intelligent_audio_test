# -*- coding: utf-8 -*-
"""INT-604 评估收敛期望数单测（评审技术补充：评估收敛期望数改按路由行求和）。

覆盖 `_result_status_mixin._get_expected_result_count`：
- 路由级绑定行（device_id 非空）每行预期 1 个结果（混选多路由下按行求和）；
- legacy 未绑定行（device_id 空）按该路由类型 len(devices)/len(apis) 预期（零回归）；
- 无用例行 → 兜底 1；
- 混合（绑定行 + legacy 行）按行求和。

mock task_acl_repository 的读取方法，不触真实 DB/gRPC。
"""
import os
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest  # noqa: E402


def _tc(device_type, device_id=None):
    return SimpleNamespace(device_type=device_type, device_id=device_id)


def _call(case_rows, devices=(), apis=()):
    from evaluation_service.infrastructure.persistence import _result_status_mixin as m

    mixin = m.ResultStatusMixin()
    with mock.patch.object(m, 'task_acl_repository') as repo:
        repo.get_task_case_by_ids.return_value = case_rows
        repo.get_task_devices.return_value = list(devices)
        repo.get_task_apis.return_value = list(apis)
        return mixin._get_expected_result_count(1, SimpleNamespace(), 'case-1')


class TestExpectedCountByRouteRows:
    def test_mixed_both_bound_rows_count_one_each(self):
        """同一用例设备侧 + API 侧各绑定 ID：每行预期 1 个结果，共 2。"""
        got = _call([
            _tc('physical', '101'),
            _tc('http_api', '202'),
        ])
        assert got == 2

    def test_legacy_physical_without_device_id_counts_devices(self):
        """legacy 未绑定行（physical, device_id 空）：按任务设备数预期。"""
        got = _call([_tc('physical')], devices=(101, 102, 103))
        assert got == 3

    def test_legacy_api_without_device_id_counts_apis(self):
        """legacy 未绑定行（http_api, device_id 空）：按任务 API 数预期。"""
        got = _call([_tc('http_api')], apis=(202, 303))
        assert got == 2

    def test_empty_case_rows_fallback_one(self):
        """无用例行：兜底预期 1。"""
        got = _call([])
        assert got == 1

    def test_mixed_bound_and_legacy_sums(self):
        """混合：物理绑定行 +1，legacy API 行按 len(apis)。"""
        got = _call([
            _tc('physical', '101'),
            _tc('http_api'),  # legacy API 未绑定
        ], apis=(202, 303, 404))
        assert got == 4

    def test_null_device_type_normalized_to_physical(self):
        """device_type 缺省（NULL/None）归一 physical：legacy 行按设备数预期。"""
        got = _call([_tc(None)], devices=(1, 2))
        assert got == 2
