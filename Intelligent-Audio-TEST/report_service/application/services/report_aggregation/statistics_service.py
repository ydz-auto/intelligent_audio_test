# -*- coding: utf-8 -*-
"""报告统计分析服务（INT-791：/reports/statistics* 三端点核心计算）

实现 G04 报告统计分析页所需的三类统计：

- get_statistics：按维度（time|task_type|device_type|evaluation_metric）
  聚合，结果含 overview / detail / chart / anomaly（异常统计识别）四形态
- get_trend：趋势时间序列（trend_type=time|dimension；只返回序列数据，
  预测呈现归前端，不引入后端 ML 预测）
- generate_report：统计报表文件载荷（csv/excel/pdf/html，复用
  mime_type/filename/content_base64 binary 下载结构）

数据来源：report 7 表只读（test_reports / report_summaries /
report_summary_meta / report_metric_stats），不引入 DB 迁移。
task_type 维度按报告级设备/API 参与形态派生（api=无物理设备、e2e=含
物理设备且无 API、mixed=物理+API 兼有；对照任务级 INT-273 派生口径）。
algorithm_type 可选过滤按 report_cases.algorithm_type 存在性匹配
（报告主表无该列，以用例级算法类型归属）。

异常统计识别规则（实施裁定 INT-791，schema 见 doc/接口文档/06_报告管理.md）：
- pass_rate < 60 → 通过率偏低
- total_cases = 0 → 无用例数据
- failed_cases > total_cases 或 pass_rate > 100 → 数据异常
"""
from __future__ import annotations

import base64
import io
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 中国标准时区 UTC+8（对齐 shared.utils.query_utils.now_cst）
_CST = timezone(timedelta(hours=8))

_DIMENSIONS = ('time', 'task_type', 'device_type', 'evaluation_metric')
_TREND_TYPES = ('time', 'dimension')
_REPORT_TYPES = ('report_count', 'case_execution', 'evaluation_metric', 'device_performance')
_FORMATS = ('csv', 'excel', 'pdf', 'html')

# 异常统计识别阈值
_PASS_RATE_LOW = 60.0


# ======================================================================
# 基础辅助
# ======================================================================

def _to_cst_naive(value) -> Optional[datetime]:
    """ISO 时间字符串 → CST 无时区 datetime（对齐 DB 列 utc8now 口径）。

    时区时间转 CST 后去 tzinfo；无时区字符串视为 CST；非法值返回 None。
    """
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if dt.tzinfo is not None:
            dt = dt.astimezone(_CST).replace(tzinfo=None)
        return dt
    except (TypeError, ValueError):
        return None


def _num(source, key, default=0) -> float:
    """从 ReportSummary PO（或 dict）读取数值字段，非法值归零。"""
    if source is None:
        return default
    try:
        val = source.get(key) if isinstance(source, dict) else getattr(source, key, None)
    except Exception:
        return default
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def _meta_list(meta, key) -> list:
    """从 ReportSummaryMeta PO 读取 JSON 列表字段，兼容 str/None。"""
    if meta is None:
        return []
    try:
        val = meta.get(key) if isinstance(meta, dict) else getattr(meta, key, None)
    except Exception:
        return []
    if val is None:
        return []
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
        except (ValueError, TypeError):
            return []
        return parsed if isinstance(parsed, list) else []
    return val if isinstance(val, list) else []


def _round(value, ndigits=2) -> float:
    """安全 round：非数值归零。"""
    try:
        return round(float(value), ndigits)
    except (TypeError, ValueError):
        return 0.0


# ======================================================================
# 统计分析（GET /reports/statistics）
# ======================================================================

def _summarize_rows(rows: List[Tuple[Any, Any, Any]]) -> dict:
    """对一批 (Report, ReportSummary, ReportSummaryMeta) 计算总览聚合。

    已完成报告按 published 计数：报告生成完成置 published（ReportStatus
    仅 draft/published，见 shared/models/common_enums.py），draft 计入
    report_count 但不计入已完成；报告表无 failed 状态（生成失败留 draft
    或未落行），overview 不含 failed_reports，失败口径以用例级
    failed_cases 体现。
    """
    report_count = len(rows)
    completed_reports = sum(1 for r, _s, _m in rows if r.status == 'published')
    total_cases = int(sum(_num(s, 'total_cases') for _r, s, _m in rows))
    completed_cases = int(sum(_num(s, 'completed_cases') for _r, s, _m in rows))
    failed_cases = int(sum(_num(s, 'failed_cases') for _r, s, _m in rows))
    pass_rate = _weighted_pass_rate(rows)
    duration = _round(sum(_num(s, 'duration') for _r, s, _m in rows))
    return {
        'report_count': report_count,
        'completed_reports': completed_reports,
        'total_cases': total_cases,
        'completed_cases': completed_cases,
        'failed_cases': failed_cases,
        'pass_rate': pass_rate,
        'duration': duration,
    }


def _weighted_pass_rate(rows: List[Tuple[Any, Any, Any]]) -> float:
    """用例数加权通过率（只统计有用例数据的报告，避免空报告拉低口径）。"""
    total = 0
    passed = 0.0
    for _r, s, _m in rows:
        tc = _num(s, 'total_cases')
        if tc > 0:
            total += tc
            passed += tc * _num(s, 'pass_rate') / 100.0
    return _round(passed / total * 100, 2) if total > 0 else 0.0


def _derive_task_type(meta) -> str:
    """报告级任务类型派生（api/e2e/mixed，对照任务级 INT-273 口径）。"""
    has_physical = bool(_meta_list(meta, 'devices'))
    has_api = bool(_meta_list(meta, 'apis'))
    if has_physical and has_api:
        return 'mixed'
    if has_physical:
        return 'e2e'
    return 'api'


def _date_key(created_at) -> str:
    """报告 created_at → 日期分组键（YYYY-MM-DD）。"""
    if created_at is None:
        return 'unknown'
    if isinstance(created_at, str):
        try:
            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        except ValueError:
            return 'unknown'
    return created_at.strftime('%Y-%m-%d') if hasattr(created_at, 'strftime') else 'unknown'


def _group_rows(rows: List[Tuple[Any, Any, Any]], dimension: str) -> Dict[str, List[Tuple[Any, Any, Any]]]:
    """按维度将报告基础行分组，返回 {group_key: rows}。"""
    groups: Dict[str, List[Tuple[Any, Any, Any]]] = {}
    for row in rows:
        r, _s, meta = row
        keys = []
        if dimension == 'time':
            keys = [_date_key(r.created_at)]
        elif dimension == 'task_type':
            keys = [_derive_task_type(meta)]
        elif dimension == 'device_type':
            devices = _meta_list(meta, 'devices')
            # 按报告对设备类型去重：同报告多台同型设备计为该类型一次，
            # 避免 report_count/用例数被重复放大（device_count 另收集全部设备 id）
            keys = sorted({d.get('type') or 'unknown' for d in devices if isinstance(d, dict)})
            if not keys:
                keys = ['unknown']
        else:  # evaluation_metric
            dim_values = _meta_list(meta, 'dimension_values')
            keys = [dv.get('name') or str(dv.get('id')) for dv in dim_values
                    if isinstance(dv, dict) and dv.get('name')]
            if not keys:
                keys = ['unknown']
        for key in keys:
            groups.setdefault(key, []).append(row)
    return groups


def _build_metric_detail(rows: List[Tuple[Any, Any, Any]], metric: str) -> List[dict]:
    """评估指标维度明细：每个报告取其维度平均值，聚合该指标的 min/avg/max。"""
    values = []
    report_count = 0
    for _r, _s, meta in rows:
        dim_values = _meta_list(meta, 'dimension_values')
        found = None
        for dv in dim_values:
            if isinstance(dv, dict) and (dv.get('name') == metric or str(dv.get('id')) == metric):
                found = dv.get('average_value')
                break
        if found is not None:
            try:
                values.append(float(found))
                report_count += 1
            except (TypeError, ValueError):
                pass
    if not values:
        return [{'metric': metric, 'report_count': 0, 'average_value': 0.0,
                 'min': 0.0, 'max': 0.0}]
    return [{
        'metric': metric,
        'report_count': report_count,
        'average_value': _round(sum(values) / len(values)),
        'min': _round(min(values)),
        'max': _round(max(values)),
    }]


def _build_device_detail(rows: List[Tuple[Any, Any, Any]], device_type: str) -> dict:
    """设备类型维度明细：按设备类型聚合报告数据。"""
    base = _summarize_rows(rows)
    device_ids = set()
    for _r, _s, meta in rows:
        for d in _meta_list(meta, 'devices'):
            if isinstance(d, dict) and (d.get('type') or 'unknown') == device_type \
                    and d.get('id') is not None:
                device_ids.add(str(d.get('id')))
    base['device_type'] = device_type
    base['device_count'] = len(device_ids)
    return base


def _build_detail(dimension: str, rows: List[Tuple[Any, Any, Any]]) -> List[dict]:
    """按维度构建 detail 明细表。"""
    groups = _group_rows(rows, dimension)
    detail = []
    if dimension == 'evaluation_metric':
        # 评估指标维度：聚合所有指标（含无数据指标补 0 行）
        metric_names = set()
        for _r, _s, meta in rows:
            for dv in _meta_list(meta, 'dimension_values'):
                if isinstance(dv, dict) and dv.get('name'):
                    metric_names.add(dv.get('name'))
        if not metric_names:
            return []
        for metric in sorted(metric_names):
            detail.extend(_build_metric_detail(rows, metric))
        return detail
    for key, group_rows in groups.items():
        item = _summarize_rows(group_rows)
        if dimension == 'device_type':
            item = _build_device_detail(group_rows, key)
        item['group'] = key
        detail.append(item)
    return detail


def _build_chart(dimension: str, detail: List[dict]) -> dict:
    """从 detail 构建图表序列数据（categories + series）。"""
    if not detail:
        return {'categories': [], 'series': []}
    if dimension == 'evaluation_metric':
        return {
            'categories': [d.get('metric') for d in detail],
            'series': [{'name': '平均得分', 'data': [d.get('average_value', 0) for d in detail]}],
        }
    if dimension == 'device_type':
        return {
            'categories': [d.get('device_type') for d in detail],
            'series': [
                {'name': '设备数', 'data': [d.get('device_count', 0) for d in detail]},
                {'name': '总用例数', 'data': [d.get('total_cases', 0) for d in detail]},
                {'name': '通过率', 'data': [d.get('pass_rate', 0) for d in detail]},
            ],
        }
    return {
        'categories': [d.get('group') for d in detail],
        'series': [
            {'name': '报告数量', 'data': [d.get('report_count', 0) for d in detail]},
            {'name': '总用例数', 'data': [d.get('total_cases', 0) for d in detail]},
            {'name': '通过率', 'data': [d.get('pass_rate', 0) for d in detail]},
        ],
    }


def _detect_anomalies(rows: List[Tuple[Any, Any, Any]]) -> List[dict]:
    """异常统计识别：按实施裁定规则标记单报告异常。"""
    anomalies = []
    for r, s, _m in rows:
        total = int(_num(s, 'total_cases'))
        failed = int(_num(s, 'failed_cases'))
        pass_rate = _num(s, 'pass_rate')
        if total == 0:
            anomalies.append({
                'type': 'no_cases',
                'report_id': r.id,
                'report_name': r.name,
                'message': '无用例数据',
                'value': 0,
            })
        elif pass_rate < _PASS_RATE_LOW:
            anomalies.append({
                'type': 'low_pass_rate',
                'report_id': r.id,
                'report_name': r.name,
                'message': '通过率偏低',
                'value': _round(pass_rate),
            })
        if failed > total or pass_rate > 100:
            anomalies.append({
                'type': 'data_error',
                'report_id': r.id,
                'report_name': r.name,
                'message': '数据异常',
                'value': _round(pass_rate),
            })
    return anomalies


# ======================================================================
# 趋势分析（GET /reports/statistics/trend）
# ======================================================================

def _build_time_trend(rows: List[Tuple[Any, Any, Any]]) -> List[dict]:
    """时间趋势：按日期聚合报告数/用例/通过率/时长序列。"""
    groups: Dict[str, List[Tuple[Any, Any, Any]]] = {}
    for row in rows:
        r, _s, _m = row
        groups.setdefault(_date_key(r.created_at), []).append(row)
    trend = []
    for date_key in sorted(groups.keys()):
        agg = _summarize_rows(groups[date_key])
        trend.append({
            'date': date_key,
            'report_count': agg['report_count'],
            'total_cases': agg['total_cases'],
            'pass_rate': agg['pass_rate'],
            'duration': agg['duration'],
        })
    return trend


def _build_dimension_trend(rows: List[Tuple[Any, Any, Any]], metric: str) -> List[dict]:
    """维度趋势：按评估指标聚合并按日期展开时间序列。

    未指定 metric 时返回全部指标（每指标一条 points 序列）。
    """
    metric_names = set()
    for _r, _s, meta in rows:
        for dv in _meta_list(meta, 'dimension_values'):
            if isinstance(dv, dict) and dv.get('name'):
                metric_names.add(dv.get('name'))
    if metric:
        metric_names = {m for m in metric_names if m == metric}
    if not metric_names:
        return []
    # 每指标 → {date: value}
    per_metric: Dict[str, Dict[str, float]] = {}
    for r, _s, meta in rows:
        date_key = _date_key(r.created_at)
        for dv in _meta_list(meta, 'dimension_values'):
            if not isinstance(dv, dict):
                continue
            name = dv.get('name')
            if name not in metric_names:
                continue
            try:
                value = float(dv.get('average_value'))
            except (TypeError, ValueError):
                continue
            per_metric.setdefault(name, {})[date_key] = value
    return [
        {
            'metric': name,
            'points': [
                {'date': d, 'value': _round(per_metric[name][d])}
                for d in sorted(per_metric[name].keys())
            ],
        }
        for name in sorted(per_metric.keys())
    ]


# ======================================================================
# 报表生成（POST /reports/statistics/report）
# ======================================================================

def _build_report_table(report_type: str, rows: List[Tuple[Any, Any, Any]],
                        repository) -> List[dict]:
    """按报表类型构建表格行（表头为 dict 键，顺序为插入序）。"""
    if report_type == 'report_count':
        groups: Dict[str, List[Tuple[Any, Any, Any]]] = {}
        for row in rows:
            r, _s, _m = row
            groups.setdefault(_date_key(r.created_at), []).append(row)
        table = []
        for date_key in sorted(groups.keys()):
            agg = _summarize_rows(groups[date_key])
            table.append({
                '日期': date_key,
                '报告数量': agg['report_count'],
                '已完成': agg['completed_reports'],
            })
        return table

    if report_type == 'case_execution':
        groups = {}
        for row in rows:
            r, _s, _m = row
            groups.setdefault(_date_key(r.created_at), []).append(row)
        table = []
        for date_key in sorted(groups.keys()):
            agg = _summarize_rows(groups[date_key])
            table.append({
                '日期': date_key,
                '总用例数': agg['total_cases'],
                '完成用例数': agg['completed_cases'],
                '失败用例数': agg['failed_cases'],
                '通过率(%)': agg['pass_rate'],
            })
        return table

    if report_type == 'evaluation_metric':
        metric_names = set()
        for _r, _s, meta in rows:
            for dv in _meta_list(meta, 'dimension_values'):
                if isinstance(dv, dict) and dv.get('name'):
                    metric_names.add(dv.get('name'))
        table = []
        for metric in sorted(metric_names):
            row_meta = _build_metric_detail(rows, metric)[0]
            table.append({
                '评估维度': metric,
                '报告数': row_meta['report_count'],
                '平均得分': row_meta['average_value'],
                '最低': row_meta['min'],
                '最高': row_meta['max'],
            })
        return table

    # device_performance：逐设备行（来自 report_metric_stats.device_stats 快照）
    stats_map = repository.get_metric_stats_for_report_ids(
        [r.id for r, _s, _m in rows])
    table = []
    for report_id, stats_po in stats_map.items():
        device_stats = _meta_list(stats_po, 'device_stats')
        for d in device_stats:
            if not isinstance(d, dict):
                continue
            total = int(_num(d, 'total_cases'))
            completed = int(_num(d, 'completed_cases'))
            table.append({
                '报告ID': report_id,
                '设备名称': d.get('name') or '',
                '设备类型': d.get('type') or '',
                '型号': d.get('model') or '',
                '总用例数': total,
                '完成用例数': completed,
                '失败用例数': int(_num(d, 'failed_cases')),
                '通过率(%)': _round(_num(d, 'success_rate')),
            })
    if not table:
        table = [{'报告ID': report_id, '设备名称': '', '设备类型': '',
                  '型号': '', '总用例数': 0, '完成用例数': 0,
                  '失败用例数': 0, '通过率(%)': 0} for report_id, _s, _m in rows]
    return table


def _build_file_payload(table: List[dict], format_type: str) -> dict:
    """按格式构建报表文件载荷（base64），返回 binary 下载结构。"""
    from shared.utils.query_utils import now_cst

    if format_type == 'excel':
        return _build_excel_payload(table, now_cst)
    if format_type == 'pdf':
        return _build_pdf_payload(table, now_cst)
    if format_type == 'html':
        return _build_html_payload(table, now_cst)
    return _build_csv_payload(table, now_cst)


def _build_csv_payload(table: List[dict], now_cst) -> dict:
    """构建 CSV 载荷（UTF-8 BOM）。"""
    buf = io.BytesIO()
    buf.write('﻿'.encode('utf-8-sig'))
    if table:
        headers = list(table[0].keys())
        buf.write((",".join(headers) + "\n").encode('utf-8-sig'))
        for row in table:
            csv_row = [f'"{str(row[h])}"' if ',' in str(row[h]) else str(row[h])
                       for h in headers]
            buf.write((",".join(csv_row) + "\n").encode('utf-8-sig'))
    buf.seek(0)
    filename = f"statistics_report_{now_cst().strftime('%Y%m%d')}.csv"
    return {
        'filename': filename,
        'format': 'csv',
        'content_base64': base64.b64encode(buf.getvalue()).decode('utf-8'),
        'mime_type': 'text/csv',
    }


def _build_excel_payload(table: List[dict], now_cst) -> dict:
    """构建 Excel 载荷（openpyxl）。"""
    import pandas as pd
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        pd.DataFrame(table).to_excel(writer, index=False, sheet_name='统计分析')
    output.seek(0)
    filename = f"statistics_report_{now_cst().strftime('%Y%m%d')}.xlsx"
    return {
        'filename': filename,
        'format': 'excel',
        'content_base64': base64.b64encode(output.getvalue()).decode('utf-8'),
        'mime_type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    }


def _build_pdf_payload(table: List[dict], now_cst) -> dict:
    """构建 PDF 载荷（reportlab，横向表格）。"""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=landscape(A4))
    data = [list(table[0].keys())] if table else [['无数据']]
    for row in table:
        data.append(list(row.values()))
    tbl = Table(data)
    tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.gray),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    doc.build([tbl])
    output.seek(0)
    filename = f"statistics_report_{now_cst().strftime('%Y%m%d')}.pdf"
    return {
        'filename': filename,
        'format': 'pdf',
        'content_base64': base64.b64encode(output.getvalue()).decode('utf-8'),
        'mime_type': 'application/pdf',
    }


def _build_html_payload(table: List[dict], now_cst) -> dict:
    """构建 HTML 载荷（内嵌表格，前端可直接渲染）。"""
    rows_html = []
    if table:
        headers = list(table[0].keys())
        head_html = "".join(f"<th>{h}</th>" for h in headers)
        rows_html.append(f"<thead><tr>{head_html}</tr></thead><tbody>")
        for row in table:
            cells = "".join(f"<td>{row.get(h, '')}</td>" for h in headers)
            rows_html.append(f"<tr>{cells}</tr>")
        rows_html.append("</tbody>")
    else:
        rows_html.append("<tbody><tr><td>无数据</td></tr></tbody>")
    html = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<title>报告统计分析</title></head><body>"
        "<h3>报告统计分析报表</h3>"
        f"<table border='1' style='border-collapse:collapse;font-size:12px;'>{''.join(rows_html)}</table>"
        "</body></html>"
    )
    encoded = html.encode('utf-8')
    filename = f"statistics_report_{now_cst().strftime('%Y%m%d')}.html"
    return {
        'filename': filename,
        'format': 'html',
        'content_base64': base64.b64encode(encoded).decode('utf-8'),
        'mime_type': 'text/html',
    }


# ======================================================================
# 对外入口（module-level 单例）
# ======================================================================

class StatisticsService:
    """报告统计分析服务（门面）。"""

    @staticmethod
    def get_statistics(params: dict, repository) -> dict:
        """统计分析（GET /reports/statistics）。

        Args:
            params: {dimension, start_time, end_time, algorithm_type}
            repository: ReportRepository 实例（查询报告基础行）

        Returns:
            {dimension, overview, detail, chart, anomaly}
        """
        dimension = (params.get('dimension') or 'time').strip()
        if dimension not in _DIMENSIONS:
            return {'success': False,
                    'message': f'dimension 非法值: {dimension}，可选 {"|".join(_DIMENSIONS)}'}
        start_time = _to_cst_naive(params.get('start_time'))
        end_time = _to_cst_naive(params.get('end_time'))
        algorithm_type = (params.get('algorithm_type') or '').strip() or None

        rows = repository.get_statistics_rows(start_time, end_time, algorithm_type)

        overview = _summarize_rows(rows)
        detail = _build_detail(dimension, rows)
        chart = _build_chart(dimension, detail)
        anomaly = _detect_anomalies(rows)
        return {
            'dimension': dimension,
            'overview': overview,
            'detail': detail,
            'chart': chart,
            'anomaly': anomaly,
        }

    @staticmethod
    def get_trend(params: dict, repository) -> dict:
        """趋势分析（GET /reports/statistics/trend）。

        Args:
            params: {trend_type, metric, start_time, end_time}
            repository: ReportRepository 实例

        Returns:
            {trend_type, metric?, time_trend, dimension_trend}
        """
        trend_type = (params.get('trend_type') or 'time').strip()
        if trend_type not in _TREND_TYPES:
            return {'success': False,
                    'message': f'trend_type 非法值: {trend_type}，可选 {"|".join(_TREND_TYPES)}'}
        metric = (params.get('metric') or '').strip() or ''
        start_time = _to_cst_naive(params.get('start_time'))
        end_time = _to_cst_naive(params.get('end_time'))

        rows = repository.get_statistics_rows(start_time, end_time)

        if trend_type == 'dimension':
            return {
                'trend_type': 'dimension',
                'metric': metric,
                'time_trend': [],
                'dimension_trend': _build_dimension_trend(rows, metric),
            }
        return {
            'trend_type': 'time',
            'time_trend': _build_time_trend(rows),
            'dimension_trend': [],
        }

    @staticmethod
    def generate_report(params: dict, repository) -> dict:
        """统计分析报表生成（POST /reports/statistics/report）。

        Args:
            params: {report_type, content, format, time_range: {start_time, end_time}}
            repository: ReportRepository 实例

        Returns:
            binary 下载结构 {filename, format, content_base64, mime_type}
        """
        report_type = (params.get('report_type') or 'report_count').strip()
        if report_type not in _REPORT_TYPES:
            return {'success': False,
                    'message': f'report_type 非法值: {report_type}，可选 {"|".join(_REPORT_TYPES)}'}
        format_type = (params.get('format') or 'csv').strip()
        if format_type not in _FORMATS:
            return {'success': False,
                    'message': f'format 非法值: {format_type}，可选 {"|".join(_FORMATS)}'}
        time_range = params.get('time_range') or {}
        if not isinstance(time_range, dict):
            return {'success': False, 'message': 'time_range 格式错误，应为对象'}
        start_time = _to_cst_naive(time_range.get('start_time'))
        end_time = _to_cst_naive(time_range.get('end_time'))

        rows = repository.get_statistics_rows(start_time, end_time)
        table = _build_report_table(report_type, rows, repository)
        return _build_file_payload(table, format_type)


# 模块级单例（对齐 ReportAggregationService 等门面服务风格）
statistics_service = StatisticsService()
