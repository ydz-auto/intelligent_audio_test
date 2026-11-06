# -*- coding: utf-8 -*-
"""二次对比报告 summary 统计字段形态回归。

问题：secondary_comparison 生成路径未做 normalize，metric_data / tag_metric_data /
case_type_stats / raw_data 以历史 dict 形态落库（任务报告/对比报告是数组）。
前端详情页按数组消费（report.summary.metric_data.map）→ TypeError，页面白屏
（实测报告 424）。

覆盖：
- normalize_summary_metric_dicts：dict 形态归一为数组，已是数组的原样返回；
- _build_secondary_summary：生成期 summary 即为数组形态；
- ReportQueryHandler.handle_get：读侧归一历史 dict 摘要（存量报告修复）。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from report_service.application.handlers.report_handlers import ReportQueryHandler  # noqa: E402
from report_service.application.queries.report_queries import GetReportQuery  # noqa: E402
from report_service.application.services.normalize import (  # noqa: E402
    normalize_summary_metric_dicts,
)
from report_service.application.services.report_compare_generator_secondary_mixin import (  # noqa: E402
    ReportSecondaryDataMixin,
)
from report_service.domain.entities import ReportAggregate  # noqa: E402


_ALL_METRICS = [{'id': 88, 'name': '打断成功数量'}]

_LEGACY_SUMMARY = {
    'resources': ['9-pura90小艺-1.0.0'],
    'all_metrics': _ALL_METRICS,
    'case_categories': [{'id': 'c1', 'name': '打断'}],
    'all_case_tags': [{'id': 't1', 'name': '标签1'}],
    'metric_data': {'9-pura90小艺-1.0.0': {'打断成功数量': 34.68}},
    'tag_metric_data': {'t1': {'9-pura90小艺-1.0.0': {'打断成功数量': 12.0}}},
    'case_type_stats': {'c1': {'打断成功数量': 34.68}},
    'raw_data': {'9-pura90小艺-1.0.0': {'打断成功数量': [1.0, 2.0]}},
}


class TestNormalizeSummaryMetricDicts:
    def test_dict_shapes_become_arrays(self):
        out = normalize_summary_metric_dicts(_LEGACY_SUMMARY)

        assert isinstance(out['metric_data'], list)
        assert out['metric_data'][0]['resource'] == '9-pura90小艺-1.0.0'
        assert out['metric_data'][0]['metrics'] == [
            {'id': 88, 'metric': '打断成功数量', 'value': 34.68}
        ]
        assert isinstance(out['tag_metric_data'], list)
        assert out['tag_metric_data'][0]['tags'][0]['tag_name'] == '标签1'
        assert isinstance(out['case_type_stats'], list)
        assert out['case_type_stats'][0]['group_name'] == '打断'
        assert out['raw_data'] == [
            {'resource': '9-pura90小艺-1.0.0',
             'metrics': [{'metric': '打断成功数量', 'values': [1.0, 2.0]}]}
        ]

    def test_array_shapes_are_untouched(self):
        summary = {
            'metric_data': [{'resource': 'r1', 'metrics': [{'metric': 'm', 'value': 1}]}],
            'tag_metric_data': [{'resource': 'r1', 'tags': []}],
            'case_type_stats': [{'group_id': 'g1', 'group_name': 'G', 'metrics': []}],
            'raw_data': [{'resource': 'r1', 'metrics': []}],
        }

        out = normalize_summary_metric_dicts(summary)

        assert out == summary


class TestBuildSecondarySummary:
    def test_secondary_summary_metric_data_is_array(self):
        data_dict = {
            'case_categories_list': [{'id': 'c1', 'name': '打断'}],
            'case_tags_list': [{'id': 't1', 'name': '标签1'}],
            'devices_list': [],
            'apis_list': [],
            'resources': ['9-pura90小艺-1.0.0'],
            'resource_headers': [],
            'all_metrics': _ALL_METRICS,
            'raw_data': {'9-pura90小艺-1.0.0': {'打断成功数量': [1.0]}},
            'metric_data': {'9-pura90小艺-1.0.0': {'打断成功数量': 1.0}},
            'tag_metric_data': {'t1': {'9-pura90小艺-1.0.0': {'打断成功数量': 1.0}}},
            'case_type_stats': {'c1': {'打断成功数量': 1.0}},
            'device_stats': [],
            'api_stats': [],
            'source_cases': [],
            'comparison_matrix_data': {},
        }

        summary = ReportSecondaryDataMixin._build_secondary_summary([], [], [], data_dict)

        assert isinstance(summary['metric_data'], list)
        assert isinstance(summary['tag_metric_data'], list)
        assert isinstance(summary['case_type_stats'], list)
        assert isinstance(summary['raw_data'], list)


class _StubRepository:
    def __init__(self, aggregate, full_summary):
        self._aggregate = aggregate
        self._full_summary = full_summary

    def get_by_id(self, report_id):
        return self._aggregate

    def load_summaries(self, report_id):
        return []

    def load_full_report_data(self, report_id):
        return self._full_summary


class TestHandleGetNormalizesLegacySummary:
    def test_legacy_dict_summary_is_normalized_on_read(self):
        aggregate = ReportAggregate(
            id=424, task_id=0, report_type='secondary_comparison',
            status='draft', config={'name': '二次对比报告'}, deleted=False,
        )
        handler = ReportQueryHandler(repository=_StubRepository(aggregate, _LEGACY_SUMMARY))

        result = handler.handle_get(GetReportQuery(report_id=424))

        assert isinstance(result.full_summary['metric_data'], list)
        assert isinstance(result.full_summary['tag_metric_data'], list)

    def test_missing_full_summary_stays_none(self):
        aggregate = ReportAggregate(
            id=425, task_id=0, report_type='task',
            status='draft', config={'name': '任务报告'}, deleted=False,
        )
        handler = ReportQueryHandler(repository=_StubRepository(aggregate, None))

        result = handler.handle_get(GetReportQuery(report_id=425))

        assert result.full_summary is None
