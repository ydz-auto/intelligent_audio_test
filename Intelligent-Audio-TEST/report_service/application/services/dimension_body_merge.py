# -*- coding: utf-8 -*-
"""维度结果行级合并（INT-2379 C1）。

背景：报告链先以非 body 拉取得到完整维度结果（基础 map）作为完整性基准，
存在加权维度时再带 `api_raw_response` 拉一次。旧实现「body map 非空即整体
替换」——任一 body 块失败，该块所有 result 的维度行整体消失，导致用例明细行
丢失、平均维度静默偏小、加权维度部分覆盖却不打标。

本模块把替换改为**行级合并**：
- 基础 map 的 key 集合（result_id × dimension_id × round_number）是最终 key 集合（不变量 I1）；
- body 行按同一 key 逐行覆盖，只补 body 字段（api_raw_response 等）；
- 基础 map 有而 body 没返回的行**保留**（只缺 body 字段），任何 body 块失败都不得删行；
- 合并后 dimension_value / score / evaluation_status 与基础 map 逐行相等（不变量 I2）。

报告主生成链、二次对比链、查询链共用本模块，不留第二份实现。
"""
from __future__ import annotations

#: body 只补字段，不改变基础 map 的取值列（I2：body 与基础来自同一批库数据）。
_VALUE_FIELDS = ('dimension_value', 'score', 'evaluation_status')


def _row_key(rid, row):
    """行合并键：result_id × dimension_id × round_number。"""
    dim_id = row.get('dimension_id')
    if dim_id is None:
        dim_id = row.get('id')
    return (rid, dim_id, row.get('round_number'))


def _has_body(row):
    """该行是否真的带回了原始响应（None / 空值不算）。"""
    return row.get('api_raw_response') is not None


def merge_body_into_base(base_map: dict, body_map: dict) -> tuple:
    """把 body map 行级合并进基础 map。

    Args:
        base_map: {result_id: [row, ...]} —— 非 body 拉取的完整结果（完整性基准）
        body_map: {result_id: [row, ...]} —— 带 api_raw_response 的拉取结果

    Returns:
        (merged_map, stats)
        stats = {
            'total_rows', 'body_rows_applied', 'rows_without_body',
            'matched_result_ids', 'missing_result_ids',
            'ignored_body_rows',
        }
        missing_result_ids：至少一行没拿到 body 的 result_id（升序）。
    """
    base_map = base_map or {}
    body_map = body_map or {}
    merged = {}
    total_rows = 0
    applied_rows = 0
    rows_without_body = 0
    matched_ids = []
    missing_ids = []
    ignored_body_rows = 0

    for rid, base_rows in base_map.items():
        body_rows = body_map.get(rid) or []
        body_index = {}
        for row in body_rows:
            if isinstance(row, dict):
                body_index.setdefault(_row_key(rid, row), row)
        used_keys = set()
        out_rows = []
        rid_missing = False
        for base_row in base_rows:
            if not isinstance(base_row, dict):
                out_rows.append(base_row)
                continue
            key = _row_key(rid, base_row)
            body_row = body_index.get(key)
            row = dict(base_row)
            if body_row is not None:
                row.update(body_row)
                # body 只补字段：取值列以基础 map 为准（I2）
                for field in _VALUE_FIELDS:
                    if field in base_row:
                        row[field] = base_row[field]
                used_keys.add(key)
                applied_rows += 1
                if not _has_body(row):
                    rid_missing = True
            else:
                rid_missing = True
            if not _has_body(row):
                rows_without_body += 1
            out_rows.append(row)
            total_rows += 1
        # body 返回但基础 map 没有的行忽略（不变量 I1：key 集合与基础 map 完全一致）
        ignored_body_rows += sum(1 for k in body_index if k not in used_keys)
        merged[rid] = out_rows
        if rid_missing:
            missing_ids.append(rid)
        else:
            matched_ids.append(rid)

    return merged, {
        'total_rows': total_rows,
        'body_rows_applied': applied_rows,
        'rows_without_body': rows_without_body,
        'matched_result_ids': matched_ids,
        'missing_result_ids': sorted(missing_ids),
        'ignored_body_rows': ignored_body_rows,
    }


def build_coverage(acl_coverage: dict, merge_stats: dict,
                   missing_limit: int = 50) -> dict:
    """生成覆盖摘要（ACL 失败块信息 + 行级合并缺失结果口径）。

    缺失口径以「基础 map 中没拿到 body 的 result_id」为准（只统计确有维度行的
    结果），避免把本来就没有维度结果的结果误记为缺失。
    """
    acl_coverage = acl_coverage or {}
    missing = list(merge_stats.get('missing_result_ids') or [])
    matched = set(merge_stats.get('matched_result_ids') or [])
    requested = len(matched) + len(missing)
    reason = ('partial_api_raw_response_coverage' if missing else None)
    return {
        'requested': requested,
        'covered': len(matched),
        'missing': missing[:missing_limit],
        'missing_total': len(missing),
        'failed_chunks': list(acl_coverage.get('failed_chunks') or []),
        'dropped_ids': list(acl_coverage.get('dropped_ids') or []),
        'rows_without_body': merge_stats.get('rows_without_body', 0),
        'total_rows': merge_stats.get('total_rows', 0),
        'reason': reason,
    }
