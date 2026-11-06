# -*- coding: utf-8 -*-
"""INT-1571 报告生成回落：结果引用的维度已停用/软删时按 ID 补全历史维度。

缺陷（真实库 397 复现）：
  test_result_dimensions 记录的是“评估当时使用的维度”。维度后来被停用/软删
  （dimensions.status=false, deleted=true）后不再出现在 ListDimensions 结果里；
  report_service._prepare_report_data 按活跃维度列表取交集 → all_dimensions 为空 →
  all_metrics 为空 → 报告恒判「任务没有关联任何评估维度」生成失败。

修复：
  - _get_result_dimensions：活跃维度 + 按 ID 解析结果引用但已非活跃的历史维度；
  - evaluation_service GetDimensionByIds 返回报告指标口径字段（按 ID 解析不过滤软删）。

纯单测，不触真实 DB/gRPC/Redis。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

import report_service.application.services.report_data_builder_resource_mixin as rdb_rm
import report_service.application.services.report_task_generator as gen_mod
from report_service.application.services.report_data_builder import ReportDataBuilder


def _dim(dim_id, name, statistic_method='average', score_unit='', sort_order=0,
         dimension_type='main', parent=None, agg_denominator='case'):
    """构造维度 dict（形状对齐 evaluation_service GetDimensionByIds / ListDimensions 载荷）。"""
    return {
        'id': dim_id, 'name': name,
        'statistic_method': statistic_method, 'score_unit': score_unit,
        'sort_order': sort_order, 'dimension_type': dimension_type,
        'parent_dimension_id': parent, 'agg_denominator': agg_denominator,
        'decimal_places': 2,
    }


class TestGetResultDimensions:
    """结果引用维度取集：活跃优先 + 历史维度按 ID 补全。"""

    def test_all_active_returns_active_only(self, monkeypatch):
        called = []
        monkeypatch.setattr(rdb_rm, '_grpc_get_dimension_by_ids',
                            lambda ids: called.append(ids) or {})
        active = [_dim(121, '活跃A'), _dim(122, '活跃B')]
        selected = ReportDataBuilder._get_result_dimensions(active, {121: {}, 122: {}})
        assert [d['id'] for d in selected] == [121, 122]
        assert called == []  # 全部活跃时不发按 ID 查询

    def test_supplements_deleted_dimension_by_id(self, monkeypatch):
        requested = []

        def _fake_by_ids(ids):
            requested.append(list(ids))
            return {str(d): _dim(d, '历史维度%s' % d, statistic_method='pass_rate')
                    for d in ids}

        monkeypatch.setattr(rdb_rm, '_grpc_get_dimension_by_ids', _fake_by_ids)
        active = [_dim(121, '活跃A')]
        # 结果引用了 121（活跃）+ 75/77（已软删）
        selected = ReportDataBuilder._get_result_dimensions(active, {121: {}, 75: {}, 77: {}})
        assert [d['id'] for d in selected] == [121, 75, 77]
        assert requested == [[75, 77]]

    def test_empty_dim_stats_falls_back_to_active_list(self, monkeypatch):
        monkeypatch.setattr(rdb_rm, '_grpc_get_dimension_by_ids',
                            lambda ids: pytest.fail('空 dim_stats 不应按 ID 解析'))
        active = [_dim(121, '活跃A')]
        selected = ReportDataBuilder._get_result_dimensions(active, {})
        assert [d['id'] for d in selected] == [121]

    def test_unresolved_dimension_skipped_with_warning(self, monkeypatch, caplog):
        """维度已被硬删（按 ID 也查不到）时跳过该列，不影响其余维度出报告。"""
        monkeypatch.setattr(rdb_rm, '_grpc_get_dimension_by_ids',
                            lambda ids: {} if ids == [999] else {str(i): _dim(i, 'x') for i in ids})
        active = [_dim(121, '活跃A')]
        with caplog.at_level('WARNING', logger=rdb_rm.logger.name):
            selected = ReportDataBuilder._get_result_dimensions(active, {121: {}, 999: {}})
        assert [d['id'] for d in selected] == [121]
        assert '999' in caplog.text

    def test_build_all_metrics_keeps_historical_config(self):
        """历史维度口径（pass_rate/%/sort_order）还原到指标列，不退化为默认值。"""
        metrics = ReportDataBuilder._build_all_metrics([
            _dim(75, '拒识成功率占比', statistic_method='weighted_wer',
                 score_unit='%', sort_order=25),
            _dim(77, '拒识失败率占比', statistic_method='pass_rate',
                 score_unit='%', sort_order=27),
        ])
        assert [m['id'] for m in metrics] == [75, 77]
        assert metrics[0]['statistic_method'] == 'weighted_wer'
        assert metrics[0]['unit'] == '%'
        assert metrics[1]['statistic_method'] == 'pass_rate'


class TestPrepareReportDataLegacyDimensions:
    """_prepare_report_data 端到端切片：只有历史维度时仍产出指标，不再判失败。"""

    def _patch_chain(self, monkeypatch, dim_stats):
        events = []
        monkeypatch.setattr(gen_mod, '_emit_report_event',
                            lambda name, data: events.append((name, data)))
        monkeypatch.setattr(gen_mod, 'log_and_emit', lambda *a, **k: None)
        monkeypatch.setattr(gen_mod, '_grpc_list_dimensions_all', lambda: [])
        monkeypatch.setattr(
            gen_mod.ReportDataBuilder, '_get_dimension_results_batch',
            staticmethod(lambda ids: (
                {rid: [{'dimension_id': d, 'dimension_value': 1.0,
                        'evaluation_status': 'completed'} for d in dim_stats]
                 for rid in ids},
                {d: {'name': '历史维度%s' % d, 'total_dimension_value': 1.0, 'count': 1}
                 for d in dim_stats})))
        monkeypatch.setattr(
            gen_mod.ReportDataBuilder, '_get_task_test_cases',
            staticmethod(lambda tids: ([], [])))
        monkeypatch.setattr(
            gen_mod.ReportDataBuilder, '_get_task_resources',
            staticmethod(lambda tids: ([{'id': 9, 'name': 'dev'}], [], [9], [])))
        monkeypatch.setattr(
            gen_mod.ReportDataBuilder, '_get_resource_result_types_batch',
            staticmethod(lambda tids, dids, aids: ({}, {})))
        monkeypatch.setattr(gen_mod, '_grpc_get_devices_by_ids',
                            lambda ids: {9: {'id': 9, 'name': 'dev', 'app_version': '1.0.0'}})
        monkeypatch.setattr(gen_mod, '_grpc_get_apis_by_ids', lambda ids: {})
        monkeypatch.setattr(
            rdb_rm, '_grpc_get_dimension_by_ids',
            lambda ids: {str(d): _dim(d, '历史维度%s' % d) for d in ids})
        return events

    def test_only_deleted_dimensions_still_build_metrics(self, monkeypatch):
        events = self._patch_chain(monkeypatch, [75, 77, 118])
        task = {'id': 397, 'name': 't', 'status': 'completed', 'total_cases': 1,
                'completed_cases': 1, 'failed_cases': 0}
        results = [{'id': 3834, 'test_case_id': 'c1', 'device_id': 9}]

        data = gen_mod.ReportTaskGenerator._prepare_report_data(task, 397, results)

        assert data is not None
        assert [m['id'] for m in data['all_metrics']] == [75, 77, 118]
        assert events == []  # 不再发失败事件
