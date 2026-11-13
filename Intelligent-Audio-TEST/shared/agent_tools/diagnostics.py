# -*- coding: utf-8 -*-
"""任务 / 日志只读诊断聚合（INT-2461，方案 §6.1 task_diagnose / log_diagnose）。

本模块只做**纯函数聚合**：输入是网关真实响应体里的 ``data``，输出结构化
诊断。所有数值、行、ID 都直接取自输入；取不到就写进 ``notes`` 说明缺什么，
不估算、不补默认值、不凭日志模块名推断根因（模块聚合只是线索，带样本 ID）。

- ``build_task_diagnosis``：任务进度 / 用例统计 / 失败用例 / ERROR 日志归因 /
  重测建议（只建议，不触发重跑）；
- ``build_log_diagnosis``：日志级别统计 + 错误样本按模块 / 分类聚合。

输出里的 ``sources`` 记录每个结论来自哪个接口与字段路径，行级证据带真实 ID
（日志 ``id``、用例 ``case_id``），满足卡面验收「失败诊断输出必须引用真实
日志行或接口字段（带来源 ID）」。
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from shared.utils.status_constants import ExecutionStatus

# 诊断只看错误级日志；日志接口的 level 支持逗号分隔多级别
DIAGNOSIS_LOG_LEVELS: Tuple[str, ...] = ('error', 'critical')
# 用例失败判定：执行状态为 failed（历史行可能只落 status）
FAILED_EXECUTION_STATUSES: Tuple[str, ...] = (ExecutionStatus.FAILED,)
# 日志取样上限（工具层同一口径，见 intent_tools.LOG_DIAGNOSE_*）
DEFAULT_LOG_ROWS = 20
MAX_LOG_ROWS = 100
# 单行日志内容截断长度（避免把整段堆栈灌进上下文）
SAMPLE_CONTENT_LIMIT = 500


def _pick(*values: Any) -> Any:
    """返回第一个非 None 的值（0 / False / 空串都算有效值）。"""
    for value in values:
        if value is not None:
            return value
    return None


# ---------------------------------------------------------------- 任务诊断


def _case_summary(item: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        'case_id': item.get('case_id'),
        'name': item.get('name'),
        'status': item.get('status'),
        'execution_status': item.get('execution_status'),
        'evaluation_status': item.get('evaluation_status'),
        'error_message': item.get('error_message'),
        'started_at': item.get('started_at'),
        'completed_at': item.get('completed_at'),
        'duration': item.get('duration'),
    }


def _is_failed_case(item: Mapping[str, Any]) -> bool:
    status = str(item.get('execution_status') or item.get('status') or '').lower()
    return status in FAILED_EXECUTION_STATUSES


def select_cases(task_detail: Optional[Mapping[str, Any]],
                 case_id: Optional[str] = None) -> List[Mapping[str, Any]]:
    """取任务详情 ``cases[]``（可按 case_id 过滤）；不存在的 key 返回空列表。"""
    items = (task_detail or {}).get('cases') if isinstance(task_detail, dict) else None
    selected: List[Mapping[str, Any]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        if case_id is not None and str(item.get('case_id')) != str(case_id):
            continue
        selected.append(item)
    return selected


def failed_cases(task_detail: Optional[Mapping[str, Any]],
                 case_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """失败用例清单（来自 GET /api/v1/tasks/{task_id} 的 ``cases[]``）。"""
    return [_case_summary(item)
            for item in select_cases(task_detail, case_id)
            if _is_failed_case(item)]


def log_rows(items: Optional[Sequence[Mapping[str, Any]]]) -> List[Dict[str, Any]]:
    """日志行归一：只保留诊断需要的字段，内容截断到 SAMPLE_CONTENT_LIMIT。"""
    rows: List[Dict[str, Any]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        content = item.get('content') or ''
        rows.append({
            'id': item.get('id'),
            'time': item.get('time'),
            'level': item.get('level'),
            'module': item.get('module'),
            'category': item.get('category'),
            'source': item.get('source'),
            'content': content[:SAMPLE_CONTENT_LIMIT],
            'task_id': item.get('task_id'),
            'test_case_id': item.get('test_case_id'),
        })
    return rows


def log_attribution(rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """按 (module, category) 聚合错误样本；每条带样本日志 ID 与首行内容。

    这是「线索」而不是根因判定：计数只对**取样行**成立，全量计数以
    ``log_stats`` 的级别统计为准。
    """
    buckets: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in rows:
        module = str(row.get('module') or '')
        category = str(row.get('category') or '')
        bucket = buckets.setdefault((module, category), {
            'module': module or None,
            'category': category or None,
            'count': 0,
            'log_ids': [],
            'sample_content': None,
        })
        bucket['count'] += 1
        if row.get('id') is not None:
            bucket['log_ids'].append(row['id'])
        if bucket['sample_content'] is None and row.get('content'):
            bucket['sample_content'] = row['content']
    return sorted(
        buckets.values(),
        key=lambda b: (-b['count'], b['module'] or '', b['category'] or ''))


def _log_ids_by_case(rows: Sequence[Mapping[str, Any]]) -> Dict[str, List[Any]]:
    grouped: Dict[str, List[Any]] = {}
    for row in rows:
        case = row.get('test_case_id')
        if case is None or row.get('id') is None:
            continue
        grouped.setdefault(str(case), []).append(row['id'])
    return grouped


def build_task_diagnosis(
        *,
        task_id: int,
        detail: Optional[Mapping[str, Any]],
        progress: Optional[Mapping[str, Any]] = None,
        stats: Optional[Mapping[str, Any]] = None,
        log_items: Optional[Sequence[Mapping[str, Any]]] = None,
        log_total: Optional[int] = None,
        case_id: Optional[str] = None,
        keyword: Optional[str] = None,
        logs_available: bool = True,
        log_denied: bool = False,
        log_error: Optional[str] = None,
        progress_error: Optional[str] = None,
        stats_error: Optional[str] = None,
        log_filter: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """任务失败诊断：真实接口字段 + 真实日志行，带来源 ID。"""
    detail = detail or {}
    progress = progress or {}
    counts = dict(stats) if isinstance(stats, Mapping) else {}
    selected = select_cases(detail, case_id)
    failed = failed_cases(detail, case_id)
    rows = log_rows(log_items)
    attribution = log_attribution(rows)
    ids_by_case = _log_ids_by_case(rows)

    suggestions: List[Dict[str, Any]] = []
    for case in failed:
        evidence: List[Dict[str, Any]] = [{
            'source': 'task_detail',
            'endpoint': f'/api/v1/tasks/{task_id}',
            'field': f'cases[case_id={case["case_id"]}].execution_status',
            'value': case.get('execution_status') or case.get('status'),
        }]
        if case.get('error_message'):
            evidence.append({
                'source': 'task_detail',
                'endpoint': f'/api/v1/tasks/{task_id}',
                'field': f'cases[case_id={case["case_id"]}].error_message',
                'value': case['error_message'],
            })
        case_log_ids = ids_by_case.get(str(case.get('case_id')), [])
        if case_log_ids:
            evidence.append({
                'source': 'log_list',
                'endpoint': '/api/v1/logs',
                'field': 'id',
                'value': case_log_ids,
            })
        suggestions.append({
            'case_id': case.get('case_id'),
            'name': case.get('name'),
            'action': 'retest_case',
            'executed': False,
            'evidence': evidence,
        })

    notes: List[str] = []
    if case_id is not None and not selected:
        notes.append(f'任务详情 cases[] 中没有 case_id={case_id} 的用例行')
    if case_id is not None and selected and not failed:
        notes.append(f'case_id={case_id} 当前不是失败状态，没有失败证据可归因')
    if not failed:
        notes.append('任务详情中没有执行失败的用例（execution_status=failed）')
    if not logs_available:
        if log_denied:
            notes.append('当前账号缺少 log:read，未拉取日志；失败归因仅含接口字段')
        else:
            notes.append(f'日志接口本轮不可用（{log_error or "未知原因"}），'
                         '未纳入日志归因')
    elif not rows:
        notes.append('查询窗口内没有 ERROR / CRITICAL 日志行；这不等于执行正常，'
                     '只表示该任务没有对应级别的日志')
    if log_total is not None and len(rows) < int(log_total):
        notes.append(f'日志样本 {len(rows)} 行，接口统计共 {log_total} 行；'
                     '模块聚合只对样本成立')
    if progress_error:
        notes.append(f'进度接口本轮不可用（{progress_error}），进度字段可能为空')
    if stats_error:
        notes.append(f'用例统计接口本轮不可用（{stats_error}），统计字段可能为空')
    if rows and not attribution:  # pragma: no cover - 防御：有行必有桶
        notes.append('日志样本缺少 module / category 字段，无法按来源聚合')

    return {
        'tool': 'task_diagnose',
        'task_id': task_id,
        'case_filter': case_id,
        'keyword': keyword,
        'status': {
            'task_status': _pick(detail.get('status'), progress.get('status')),
            'execution_status': _pick(detail.get('execution_status'),
                                      progress.get('execution_status')),
            'evaluation_status': _pick(detail.get('evaluation_status'),
                                       progress.get('evaluation_status')),
            'progress': progress.get('progress'),
            'total_cases': _pick(progress.get('total_cases'),
                                 detail.get('total_cases'),
                                 detail.get('case_count')),
            'completed_cases': _pick(progress.get('completed_cases'),
                                     detail.get('completed_cases')),
            'failed_cases': _pick(progress.get('failed_cases'),
                                  detail.get('failed_cases')),
            'current_case': progress.get('current_case'),
            'started_at': detail.get('started_at'),
            'completed_at': detail.get('completed_at'),
            'updated_at': progress.get('updated_at') or detail.get('updated_at'),
        },
        'counts': counts,
        'failed_cases': failed,
        'error_logs': {
            'levels': list(DIAGNOSIS_LOG_LEVELS),
            'filters': dict(log_filter or {}),
            'sampled': len(rows),
            'total_matched': log_total,
            'rows': rows,
        },
        'attribution': attribution,
        'retest': {
            'executed': False,
            'note': '只读诊断不触发重跑；重测执行在 M2（task_run）',
            'suggestions': suggestions,
        },
        'sources': [
            {'kind': 'task_detail',
             'endpoint': f'/api/v1/tasks/{task_id}',
             'fields': ['status', 'execution_status',
                        'cases[].case_id', 'cases[].execution_status',
                        'cases[].error_message']},
            {'kind': 'task_progress',
             'endpoint': f'/api/v1/tasks/{task_id}/progress',
             'available': progress_error is None,
             'fields': ['progress', 'total_cases', 'completed_cases',
                        'failed_cases']},
            {'kind': 'task_stats',
             'endpoint': f'/api/v1/tasks/{task_id}/stats',
             'available': stats_error is None,
             'fields': ['total', 'completed', 'failed', 'pending', 'skipped',
                        'pass_rate']},
            {'kind': 'log_list',
             'endpoint': '/api/v1/logs',
             'available': logs_available,
             'filters': dict(log_filter or {}),
             'rows': len(rows),
             'total': log_total},
        ],
        'notes': notes,
    }


# ---------------------------------------------------------------- 日志诊断


def _level_count(stats: Optional[Mapping[str, Any]],
                 levels: Sequence[str]) -> Optional[int]:
    """取样级别的总行数：只读接口返回的级别统计，任一缺失返回 None（不补 0）。"""
    if not isinstance(stats, Mapping):
        return None
    values = []
    for level in levels:
        value = stats.get(level)
        if not isinstance(value, int) or isinstance(value, bool):
            return None
        values.append(value)
    return sum(values)


def build_log_diagnosis(
        *,
        stats_filters: Optional[Mapping[str, Any]] = None,
        list_filters: Optional[Mapping[str, Any]] = None,
        levels: Optional[Sequence[str]] = None,
        stats: Optional[Mapping[str, Any]] = None,
        items: Optional[Sequence[Mapping[str, Any]]] = None,
        total: Optional[int] = None,
        max_rows: Optional[int] = None,
        stats_error: Optional[str] = None,
        list_error: Optional[str] = None) -> Dict[str, Any]:
    """日志诊断：级别统计（接口原值）+ 错误样本按来源聚合（带日志 ID）。"""
    levels = tuple(levels or DIAGNOSIS_LOG_LEVELS)
    stats_filters = dict(stats_filters or {})
    list_filters = dict(list_filters or {})
    stats_dict = dict(stats) if isinstance(stats, Mapping) else {}
    rows = log_rows(items)
    attribution = log_attribution(rows)
    sample_total = _level_count(stats_dict, levels)

    notes: List[str] = []
    if stats_error:
        notes.append(f'日志统计接口本轮不可用（{stats_error}），级别统计为空')
    if list_error:
        notes.append(f'日志列表接口本轮不可用（{list_error}），没有样本可聚合')
    if sample_total is not None and len(rows) < sample_total:
        notes.append(f'样本 {len(rows)} 行 / 接口统计 {"/".join(levels)} '
                     f'共 {sample_total} 行；按来源聚合只对样本成立')
    if not rows and not list_error:
        notes.append('没有命中该级别的日志行；这不等于「服务正常」，只表示该'
                     '筛选窗口内没有对应级别的行')

    return {
        'tool': 'log_diagnose',
        'action': 'diagnose',
        'sample_levels': list(levels),
        'stats_filters': stats_filters,
        'list_filters': list_filters,
        'stats': stats_dict,
        'sampled_rows': len(rows),
        'max_rows': max_rows,
        'total_matched': total,
        'attribution': attribution,
        'log_rows': rows,
        'sources': [
            {'kind': 'log_stats',
             'endpoint': '/api/v1/logs/stats',
             'available': stats_error is None,
             'filters': stats_filters,
             'fields': ['total', 'debug', 'info', 'warning', 'error',
                        'critical']},
            {'kind': 'log_list',
             'endpoint': '/api/v1/logs',
             'available': list_error is None,
             'filters': list_filters,
             'rows': len(rows),
             'total': total},
        ],
        'notes': notes,
    }


__all__ = [
    'DEFAULT_LOG_ROWS', 'DIAGNOSIS_LOG_LEVELS', 'FAILED_EXECUTION_STATUSES',
    'MAX_LOG_ROWS', 'SAMPLE_CONTENT_LIMIT', 'build_log_diagnosis',
    'build_task_diagnosis', 'failed_cases', 'log_attribution', 'log_rows',
    'select_cases',
]
