# -*- coding: utf-8 -*-
"""维度轮次口径取值（查询链与报告主生成链的共用口径源）。

对齐"多轮评估维度隔离与报告聚合设计文档"§3.6/§3.7/§3.9：
- collect_dim_items：非 average 维度（pass_rate/ratio/weighted_wer 等）策略聚合的
  item 收集——取值优先级：无排除配置且整体存在 → 只取整体 1 个 item；有排除配置
  或无整体 → 取各轮独立 item（跳过被排除轮次）；否则整体兜底。每项携带
  round_count（该用例该维度有值轮次数），供按轮次口径取分母。
- get_round_value_samples：average 维度按轮次口径（agg_denominator='round'）的
  样本收集——各轮 dimension_value（跳过被排除轮次），无轮次记录回退整体值。
- resolve_exclude_rounds：exclude_rounds 中 -1（"最后一轮"哨兵）解析为该用例
  该维度的最大轮次；无轮次记录时 -1 无效。

纯逻辑，不触 DB/gRPC；report_service 查询链（report_aggregation.stats_mixin）与
报告主生成链（report_utils.metrics_mixin）共用本模块，保证两条链口径一致。
"""


def resolve_exclude_rounds(result_id, dim_id, dim_results_map: dict, exclude_set) -> set:
    """解析排除轮次集合：将 -1（"最后一轮"选项）替换为该用例该维度的最大轮次。

    无轮次记录时 -1 无效（无最后一轮可排除）；返回不含 -1 的集合。
    """
    exclude_set = set(exclude_set or [])
    if -1 not in exclude_set:
        return exclude_set
    max_round = None
    if dim_results_map and result_id in dim_results_map:
        for dr in dim_results_map.get(result_id, []):
            if not isinstance(dr, dict):
                continue
            if (dr.get('dimension_id') or dr.get('id')) != dim_id:
                continue
            dr_round = dr.get('round_number')
            if dr_round is not None and (max_round is None or dr_round > max_round):
                max_round = dr_round
    if max_round is not None:
        exclude_set = (exclude_set - {-1}) | {max_round}
    else:
        exclude_set = exclude_set - {-1}
    return exclude_set


def get_round_value_samples(result_id, dim_id, dim_results_map: dict, exclude_set,
                            fallback_score) -> list:
    """按轮次口径取样本：各轮 dimension_value（排除轮次过滤），无轮次记录回退 [fallback_score]。"""
    exclude_set = resolve_exclude_rounds(result_id, dim_id, dim_results_map, exclude_set)
    if not dim_results_map or result_id not in dim_results_map:
        return [fallback_score]
    vals = []
    for dr in dim_results_map.get(result_id, []):
        if not isinstance(dr, dict):
            continue
        if dr.get('dimension_id') != dim_id:
            continue
        dr_val = dr.get('dimension_value')
        dr_round = dr.get('round_number')
        if dr_val is None or dr_round is None:
            continue
        if exclude_set and dr_round in exclude_set:
            continue
        vals.append(dr_val)
    return vals if vals else [fallback_score]


def collect_dim_items(result_id, dim_id, dim_results_map: dict, exclude_set) -> list:
    """收集某用例某维度用于策略聚合的 item 列表。

    取值优先级（与 V9.7.10 对齐）：
      无排除配置且整体存在 → 只取整体 1 个 item；
      有排除配置或无整体 → 取各轮独立 item（跳过被排除轮次）；否则整体兜底。
    每项含 dimension_value / api_raw_response / test_result_id / round_count
    （round_count = 该用例该维度有值轮次数，ratio 策略按轮次口径用）。
    """
    exclude_set = resolve_exclude_rounds(result_id, dim_id, dim_results_map, exclude_set)
    if not dim_results_map or result_id not in dim_results_map:
        return []
    overall_item = None
    round_items = []
    for dr in dim_results_map.get(result_id, []):
        if not isinstance(dr, dict):
            continue
        if dr.get('dimension_id') != dim_id:
            continue
        dr_val = dr.get('dimension_value')
        dr_round = dr.get('round_number')
        if dr_val is None:
            continue
        item = {
            'dimension_value': dr_val,
            'api_raw_response': dr.get('api_raw_response'),
            'test_result_id': result_id,
        }
        if dr_round is None:
            overall_item = item
        else:
            if exclude_set and dr_round in exclude_set:
                continue  # 排除轮次不参与分子/分母
            round_items.append(item)

    if overall_item and not exclude_set:
        collected = [overall_item]
    elif round_items:
        collected = round_items
    elif overall_item:
        collected = [overall_item]
    else:
        collected = []
    if collected:
        round_count = len(round_items)
        for it in collected:
            it['round_count'] = round_count
    return collected
