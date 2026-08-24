# -*- coding: utf-8 -*-
"""
维度聚合策略（策略模式 + 注册表）。

每个维度的 statistic_method 字段决定报告统计时用哪种聚合方式。
策略类通过 output_params 的 agg_role 知道用哪些字段做聚合：
  - numerator:   分子（加权求和）
  - denominator: 分母（加权求和）
  - value:       直接值（简单平均）

新增聚合方式只需实现 AggregationStrategy 并注册到 registry。
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import json
import logging

logger = logging.getLogger(__name__)


def _extract_by_path(data: Dict[str, Any], path: str) -> Optional[Any]:
    """简单路径提取，支持 a.b.c 格式。"""
    if not path or not data:
        return None
    try:
        for part in path.split('.'):
            if isinstance(data, dict):
                data = data.get(part)
            elif isinstance(data, list) and part.isdigit():
                data = data[int(part)]
            else:
                return None
        return data
    except Exception:
        return None


def _parse_raw_response(raw: Any) -> Optional[dict]:
    """解析 api_raw_response，返回 result 对象。"""
    if not raw:
        return None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
    if not isinstance(raw, dict):
        return None
    # eval_server 响应格式: {code:0, data:{result:{...}}}
    if raw.get('code') == 0:
        result_obj = raw.get('data', {}).get('result', {})
    else:
        result_obj = raw
    return result_obj if isinstance(result_obj, dict) else None


def _find_by_role(output_params: List[Dict], role: str) -> Optional[str]:
    """按 agg_role 找 field_path，找不到返回 None。"""
    for p in output_params or []:
        if p.get('agg_role') == role and p.get('field_path'):
            return p['field_path']
    return None


class AggregationStrategy(ABC):
    """聚合策略基类。"""

    @abstractmethod
    def aggregate(self, items: List[Dict[str, Any]], output_params: List[Dict[str, Any]] = None) -> Optional[float]:
        """
        聚合计算。

        Args:
            items: 该分组下所有结果的列表，每项包含:
                - dimension_value: 维度原始值
                - score: 维度得分
                - api_raw_response: eval_server 完整响应
                - test_result_id: TestResult.id
            output_params: 维度的 output 参数配置，每项含:
                - param_code: 参数代码
                - field_path: 提取路径
                - field_type: 字段类型
                - agg_role: 聚合角色 (numerator/denominator/value)

        Returns:
            聚合后的值，None 表示无法计算
        """
        ...


class SimpleAverageStrategy(AggregationStrategy):
    """简单平均：sum(values) / count。默认策略。"""

    def aggregate(self, items: List[Dict[str, Any]], output_params: List[Dict[str, Any]] = None) -> Optional[float]:
        values = [item['dimension_value'] for item in items if item.get('dimension_value') is not None]
        if not values:
            return None
        return sum(values) / len(values)


class WeightedSumRatioStrategy(AggregationStrategy):
    """
    加权比率：Σ(numerator) / Σ(denominator)。

    按 agg_role 找分子和分母的 field_path，从每条结果的 api_raw_response 提取值后累加。
    典型场景：WER = Σerrors / Σlength（按字数加权）。
    """

    def aggregate(self, items: List[Dict[str, Any]], output_params: List[Dict[str, Any]] = None) -> Optional[float]:
        numerator_path = _find_by_role(output_params, 'numerator') or 'errors'
        denominator_path = _find_by_role(output_params, 'denominator') or 'length'

        total_num = 0
        total_den = 0

        for item in items:
            result_obj = _parse_raw_response(item.get('api_raw_response'))
            if not result_obj:
                continue

            num_val = _extract_by_path(result_obj, numerator_path)
            den_val = _extract_by_path(result_obj, denominator_path)

            if num_val is not None and den_val is not None and den_val > 0:
                total_num += num_val
                total_den += den_val

        if total_den == 0:
            return None

        return round(total_num / total_den, 4)


def _parse_numeric(value: Any) -> Optional[float]:
    """把 default_value / 字段值解析成 float，失败返回 None。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (ValueError, TypeError):
        return None


class PassRateStrategy(AggregationStrategy):
    """
    达标率/占比：达标用例数 / 分组总用例数。

    通过 output_params 的 agg_role 判断达标条件（读取该 param 的 pass_threshold 作为阈值/目标值）：
      - pass_le: dimension_value <= pass_threshold（及格线型，越低越好，如 WER ≤ 0.1）
      - pass_ge: dimension_value >= pass_threshold（及格线型，越高越好，如 准确率 ≥ 0.9）
      - pass_eq: dimension_value == pass_threshold（精确匹配型，如 唤醒成功率 == 1.0）

    若未配置上述任一 agg_role 或 pass_threshold 为空，则回退到 value > 0 判定。
    """

    def aggregate(self, items: List[Dict[str, Any]], output_params: List[Dict[str, Any]] = None) -> Optional[float]:
        threshold, compare_op = _find_pass_condition(output_params)

        # 只统计 dimension_value 非 None 的条目，null 值既不计入达标数也不计入总数
        valid_items = [item for item in items if _parse_numeric(item.get('dimension_value')) is not None]
        total = len(valid_items)
        if total == 0:
            return None

        pass_count = 0
        for item in valid_items:
            val = item.get('dimension_value')
            num_val = _parse_numeric(val)
            if num_val is None:
                continue
            if _is_pass(num_val, threshold, compare_op):
                pass_count += 1

        # 转为百分比制 (0~100)，配合 score_unit='%' 显示为 "75%"
        return round(pass_count / total * 100, 2)


def _find_pass_condition(output_params: List[Dict[str, Any]]) -> tuple:
    """
    从 output_params 中查找达标条件。

    返回 (threshold, compare_op)：
      compare_op ∈ {'le', 'ge', 'eq', 'gt0'}
      threshold 为 float（gt0 时为 0.0）
    优先级：pass_eq > pass_ge > pass_le > 默认(value>0)
    """
    for role, op in (('pass_eq', 'eq'), ('pass_ge', 'ge'), ('pass_le', 'le')):
        for p in output_params or []:
            if p.get('agg_role') == role:
                threshold = _parse_numeric(p.get('pass_threshold'))
                if threshold is not None:
                    return threshold, op
    return 0.0, 'gt0'


def _is_pass(value: float, threshold: float, compare_op: str) -> bool:
    """按比较算符判定是否达标。"""
    if compare_op == 'le':
        return value <= threshold
    if compare_op == 'ge':
        return value >= threshold
    if compare_op == 'eq':
        return value == threshold
    # 默认: value > 0
    return value > 0


# ------------------------------------------------------------------
#  注册表
# ------------------------------------------------------------------

_REGISTRY: Dict[str, AggregationStrategy] = {
    'average': SimpleAverageStrategy(),
    'weighted_wer': WeightedSumRatioStrategy(),
    'pass_rate': PassRateStrategy(),
}


def register_strategy(name: str, strategy: AggregationStrategy):
    """注册自定义聚合策略。"""
    _REGISTRY[name] = strategy


def get_strategy(statistic_method: str) -> AggregationStrategy:
    """按 statistic_method 值获取策略，未知则回退到简单平均。"""
    return _REGISTRY.get(statistic_method, _REGISTRY['average'])


def get_available_strategies() -> List[str]:
    """返回所有已注册的策略名。"""
    return list(_REGISTRY.keys())
