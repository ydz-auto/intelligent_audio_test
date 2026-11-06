# -*- coding: utf-8 -*-
"""INT-2183 专项：报告 CSV 导出每一行都前置 UTF-8 BOM。

修复前 `_build_csv_payload` 在循环里逐行 `encode('utf-8-sig')`（编码器每次都会写
BOM），开头又单独写了一次，单条报告导出得到 4 个 BOM、三条得到 6 个，首列数据
变成 `\\ufeff669`；按行解析的消费方拿到带前缀的第一列。

期望：整段一次编码，文件头仅一个 BOM（或 0 个），数据行首列是原值。

覆盖：
- 报告导出 `build_export_payload(..., 'csv')`（`/api/v1/reports/export` 默认路径）
- 统计报表 `statistics_service._build_csv_payload`（同一模式的历史副本）
"""
import base64
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from datetime import datetime

BOM = b'\xef\xbb\xbf'

EXPORT_ROWS = [
    {'报告ID': '669', '报告名称': 'matrix_report_777',
     '报告类型': 'matrix_report', '生成时间': '2026-10-30 10:00:00',
     '总用例数': '10', '成功率': '90%', '分析结论': '无'},
    {'报告ID': '563', '报告名称': 'a,b',
     '报告类型': 'comparison_report', '生成时间': '2026-10-30 11:00:00',
     '总用例数': '2', '成功率': '50%', '分析结论': '含,逗号'},
    {'报告ID': '497', '报告名称': 'single_report',
     '报告类型': 'single_report', '生成时间': '2026-10-30 12:00:00',
     '总用例数': '3', '成功率': '100%', '分析结论': '无'},
]


def _now_cst():
    return datetime(2026, 10, 31, 9, 0, 0)


def _csv_bytes(payload):
    return base64.b64decode(payload['content_base64'])


class TestReportExportCsv:
    def test_bom_only_at_file_head(self):
        from report_service.application.services.report_aggregation.export_mixin import (
            _AggregationExportMixin,
        )

        for count in (1, 3):
            payload = _AggregationExportMixin.build_export_payload(
                EXPORT_ROWS[:count], 'csv')
            raw = _csv_bytes(payload)
            # 修复前：单条 4 个、三条 6 个
            assert raw.count(BOM) == 1, raw[:120]
            assert raw.startswith(BOM)

    def test_data_rows_start_with_original_value(self):
        from report_service.application.services.report_aggregation.export_mixin import (
            _AggregationExportMixin,
        )

        raw = _csv_bytes(_AggregationExportMixin.build_export_payload(
            EXPORT_ROWS, 'csv'))
        lines = raw.decode('utf-8-sig').splitlines()
        assert len(lines) == len(EXPORT_ROWS) + 1
        assert lines[0].split(',')[0] == '报告ID'
        for expected, line in zip(EXPORT_ROWS, lines[1:]):
            assert line.split(',')[0] == expected['报告ID']
            assert '﻿' not in line

    def test_no_bom_inside_file_body(self):
        from report_service.application.services.report_aggregation.export_mixin import (
            _AggregationExportMixin,
        )

        raw = _csv_bytes(_AggregationExportMixin.build_export_payload(
            EXPORT_ROWS, 'csv'))
        assert BOM not in raw[3:]


class TestStatisticsReportCsv:
    def test_statistics_csv_bom_only_at_file_head(self):
        from report_service.application.services.report_aggregation.statistics_service import (
            _build_csv_payload,
        )

        table = [
            {'报告ID': 669, '设备名称': '设备A', '总用例数': 10},
            {'报告ID': 563, '设备名称': '设备B', '总用例数': 2},
        ]
        raw = _csv_bytes(_build_csv_payload(table, _now_cst))
        assert raw.count(BOM) == 1, raw[:120]
        lines = raw.decode('utf-8-sig').splitlines()
        assert len(lines) == len(table) + 1
        assert lines[1].split(',')[0] == '669'

    def test_statistics_empty_table_keeps_bom_only(self):
        from report_service.application.services.report_aggregation.statistics_service import (
            _build_csv_payload,
        )

        raw = _csv_bytes(_build_csv_payload([], _now_cst))
        assert raw == BOM
