# -*- coding: utf-8 -*-
"""报告聚合统计 — 统计计算 Mixin（P4-5 大文件拆分）。

职责：
- 编排入口 calculate_averages：计算平均值、正态分布、资源列表等统计信息
- 维度过滤与名称映射、全局加权平均、分类×资源平均值矩阵
- 算法结果展开 / 音频路径规范化（从 handler 迁移）
"""
from __future__ import annotations

import logging

from shared.utils.audio_path_utils import normalize_audio_path
from report_service.application.services.report_aggregation.common import _r_get
from report_service.application.services.report_helpers import ReportHelpers
from report_service.infrastructure.clients.grpc_clients import (
    _grpc_list_dimensions_all,
    _grpc_get_dimension_params,
    _grpc_get_dimension_results_by_result_ids as _grpc_get_dim_results,
    _dim_id, _dim_name,
)

logger = logging.getLogger(__name__)


class _AggregationStatsMixin:
    """统计计算 Mixin：平均值计算、维度过滤、算法结果展开等。"""

    # ==================================================================
    # _calculate_averages 拆分：编排方法 + 子方法
    # ==================================================================

    @classmethod
    def calculate_averages(cls, task, filtered_case_ids: list, test_results: list, task_id: int) -> dict:
        """计算平均值、正态分布、资源列表等统计信息（编排入口）。

        Args:
            task: 任务对象
            filtered_case_ids: 过滤后的用例 ID 列表
            test_results: 测试结果列表
            task_id: 任务 ID

        Returns:
            dict: 统计信息字典
        """
        # 1. 维度过滤与名称映射
        all_dimensions, metric_name_to_id = cls._filter_visible_dimensions(test_results)

        # 2. 收集维度得分并计算全局加权平均
        averages_map, overall_averages = cls._compute_weighted_averages(
            test_results, all_dimensions, metric_name_to_id
        )

        # 3. 聚合设备/API 资源列表
        resources, resource_headers = cls._aggregate_resource_list(task, task_id)

        # 4. 加载测试用例映射表
        test_cases_map = cls._load_test_cases_map(test_results)

        # 5. 按分类×资源累积维度分数和原始数据
        dim_names = [_dim_name(dim) for dim in all_dimensions]
        raw_data = {res: {dn: [] for dn in dim_names} for res in resources}
        accumulator = {}
        cls._accumulate_category_resource_scores(
            test_results, test_cases_map, all_dimensions,
            dim_names, resources, raw_data, accumulator
        )

        # 6. 计算分类×资源的平均值矩阵
        metric_data = cls._compute_category_resource_averages(accumulator)

        # 7. 计算正态分布
        normal_distribution_data = ReportHelpers.calculate_normal_distribution(raw_data)

        return cls._build_summary_result(
            filtered_case_ids, test_results, overall_averages, averages_map,
            metric_data, raw_data, normal_distribution_data,
            resources, resource_headers, metric_name_to_id
        )

    # ------------------------------------------------------------------
    # 子方法：维度过滤
    # ------------------------------------------------------------------

    @staticmethod
    def _filter_visible_dimensions(test_results: list) -> tuple:
        """过滤可见维度，返回 (all_dimensions, metric_name_to_id)。

        根据 TestResult 关联的 dimension_results 确定实际使用的维度，
        再排除 visible_in_report=False 的维度。
        """
        all_dimensions_all = _grpc_list_dimensions_all()
        used_dim_ids = _AggregationStatsMixin._collect_used_dim_ids(test_results)
        all_dimensions = [d for d in all_dimensions_all if _dim_id(d) in used_dim_ids] if used_dim_ids else all_dimensions_all

        # 过滤掉 visible_in_report=False 的维度
        all_output_dim_ids, visible_dim_ids = _AggregationStatsMixin._collect_visible_dim_ids(all_dimensions_all)
        hidden_dim_ids = all_output_dim_ids - visible_dim_ids
        if hidden_dim_ids:
            all_dimensions = [d for d in all_dimensions if _dim_id(d) not in hidden_dim_ids]

        metric_name_to_id = {
            str(_dim_name(dim)): int(_dim_id(dim))
            for dim in all_dimensions
            if _dim_id(dim) is not None and _dim_name(dim) is not None
        }
        return all_dimensions, metric_name_to_id

    @staticmethod
    def _collect_used_dim_ids(test_results: list) -> set:
        """从测试结果中收集实际使用的维度 ID 集合。"""
        used_dim_ids = set()
        res_ids = [_r_get(r, 'id') for r in test_results]
        res_ids = [rid for rid in res_ids if rid is not None]
        if res_ids:
            dim_map = _grpc_get_dim_results(res_ids)
            for rid, items in dim_map.items():
                for it in items:
                    if isinstance(it, dict):
                        dim_id = it.get('dimension_id')
                        if dim_id is not None:
                            used_dim_ids.add(dim_id)
        return used_dim_ids

    @staticmethod
    def _collect_visible_dim_ids(all_dimensions_all: list) -> tuple:
        """遍历所有维度参数，返回 (all_output_dim_ids, visible_dim_ids)。"""
        all_output_dim_ids = set()
        visible_dim_ids = set()
        for dim in all_dimensions_all:
            dim_id = _dim_id(dim)
            if dim_id is None:
                continue
            params = _grpc_get_dimension_params(dim_id)
            for p in params:
                if not isinstance(p, dict):
                    continue
                if p.get('param_direction') != 'output':
                    continue
                if p.get('deleted', False):
                    continue
                all_output_dim_ids.add(dim_id)
                if p.get('visible_in_report', True):
                    visible_dim_ids.add(dim_id)
        return all_output_dim_ids, visible_dim_ids

    # ------------------------------------------------------------------
    # 子方法：全局加权平均
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_weighted_averages(test_results: list, all_dimensions: list, metric_name_to_id: dict) -> tuple:
        """计算全局加权平均，返回 (averages_map, overall_averages)。"""
        dimension_scores = {}
        dimension_counts = {}

        for result in test_results:
            result_id = _r_get(result, 'id')
            dim_values = ReportHelpers.extract_dimension_values(result_id, all_dimensions)
            for dim_name, score in dim_values.items():
                if score is not None:
                    if dim_name not in dimension_scores:
                        dimension_scores[dim_name] = 0
                        dimension_counts[dim_name] = 0
                    dimension_scores[dim_name] += score
                    dimension_counts[dim_name] += 1

        averages_map = {
            dim_name: (total / dimension_counts[dim_name])
            for dim_name, total in dimension_scores.items()
            if dimension_counts[dim_name] > 0
        }
        overall_averages = [
            {"id": metric_name_to_id.get(str(dim_name)), "metric": str(dim_name), "value": value}
            for dim_name, value in sorted(averages_map.items(), key=lambda kv: kv[0])
        ]
        return averages_map, overall_averages

    # ------------------------------------------------------------------
    # 子方法：按分类×资源累积维度分数
    # ------------------------------------------------------------------

    @staticmethod
    def _accumulate_category_resource_scores(
        test_results: list, test_cases_map: dict, all_dimensions: list,
        dim_names: list, resources: list, raw_data: dict, accumulator: dict
    ) -> None:
        """遍历测试结果，按分类×资源累积维度分数和原始数据。

        结果直接写入 accumulator 和 raw_data（原地修改）。
        """
        for result in test_results:
            resource = ReportHelpers.get_resource_name(result, task=None, use_time_prefix=False)
            if resource not in resources:
                continue

            result_tc_id = _r_get(result, 'test_case_id')
            test_case = test_cases_map.get(result_tc_id) if result_tc_id else None
            if not test_case:
                continue

            # 获取 group name 作为分类名
            cat_name = _AggregationStatsMixin._get_case_category_name(test_case)

            if cat_name not in accumulator:
                accumulator[cat_name] = {}
            if resource not in accumulator[cat_name]:
                accumulator[cat_name][resource] = {dn: {'sum': 0, 'count': 0} for dn in dim_names}

            result_id = _r_get(result, 'id')
            dim_values = ReportHelpers.extract_dimension_values(result_id, all_dimensions)
            for dim_name, score in dim_values.items():
                if score is not None:
                    accumulator[cat_name][resource][dim_name]['sum'] += score
                    accumulator[cat_name][resource][dim_name]['count'] += 1
                    if dim_name in raw_data[resource]:
                        raw_data[resource][dim_name].append(score)

    @staticmethod
    def _get_case_category_name(test_case) -> str:
        """从测试用例中提取分类名称（group.name），缺失则返回"未分类"。"""
        if isinstance(test_case, dict):
            g = test_case.get('group')
            if isinstance(g, dict):
                return g.get('name') or "未分类"
            elif g is not None:
                return getattr(g, 'name', None) or "未分类"
            else:
                return "未分类"
        else:
            g = getattr(test_case, 'group', None)
            return getattr(g, 'name', None) if g else "未分类"

    # ------------------------------------------------------------------
    # 子方法：分类×资源平均值
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_category_resource_averages(accumulator: dict) -> dict:
        """根据累积器计算分类×资源的平均值矩阵。"""
        metric_data = {}
        for cat_name, res_data in accumulator.items():
            metric_data[cat_name] = {}
            for res, dims in res_data.items():
                metric_data[cat_name][res] = {}
                for dim_name, stats in dims.items():
                    metric_data[cat_name][res][dim_name] = (stats['sum'] / stats['count']) if stats['count'] > 0 else 0
        return metric_data

    # ------------------------------------------------------------------
    # 子方法：构建最终结果字典
    # ------------------------------------------------------------------

    @staticmethod
    def _build_summary_result(
        filtered_case_ids: list, test_results: list, overall_averages: list,
        averages_map: dict, metric_data: dict, raw_data: dict,
        normal_distribution_data: dict, resources: list, resource_headers: list,
        metric_name_to_id: dict
    ) -> dict:
        """构建最终统计结果字典。"""
        return {
            'filtered_case_ids': filtered_case_ids,
            'test_results': test_results,
            'overall_averages': overall_averages,
            'averages_map': averages_map,
            'metric_data': metric_data,
            'raw_data': raw_data,
            'normal_distribution_data': normal_distribution_data,
            'resources': resources,
            'resource_headers': resource_headers,
            'metric_name_to_id': metric_name_to_id,
        }

    # ==================================================================
    # 算法结果展开 / 音频路径规范化（从 handler 迁移）
    # ==================================================================

    @staticmethod
    def _normalize_audio_paths_in_results(algorithm_results):
        """将 algorithm_results 中 audio_file 类型字段的绝对路径转为相对路径。

        使用 shared/utils/audio_path_utils.normalize_audio_path 完成路径规范化。
        """
        if not isinstance(algorithm_results, list):
            return algorithm_results
        from report_service.config.config import Config
        static_base = getattr(Config, 'STATIC_BASE_PATH', '')
        if not static_base:
            return algorithm_results
        for item in algorithm_results:
            if not isinstance(item, dict):
                continue
            param_type = item.get('param_type') or item.get('paramType') or item.get('field_type')
            if param_type != 'audio_file':
                continue
            val = item.get('value')
            if not isinstance(val, str) or not val:
                continue
            # 使用共享工具函数规范化音频路径
            normalized = normalize_audio_path(val, static_base)
            if normalized != val:
                item['value'] = normalized
        return algorithm_results

    @staticmethod
    def _expand_algorithm_results_for_report(algorithm_results, algorithm_type=None):
        """报告页 algorithm_results 后处理：

        对 voice_llm 多轮场景，把 rounds 数组展开成
        各 output 字段@round:N 文本字段（跳过 evaluation）。
        """
        if not isinstance(algorithm_results, list):
            return algorithm_results  # 非列表类型不处理

        # 找到 rounds 字段
        rounds_item = None
        for item in algorithm_results:
            if not isinstance(item, dict):
                continue
            code = item.get('paramCode') or item.get('param_code')
            if code == 'rounds':
                rounds_item = item
                break
        if not rounds_item:
            return _AggregationStatsMixin._normalize_audio_paths_in_results(algorithm_results)

        rounds_value = rounds_item.get('value')
        logger.debug('[expand_algo] rounds_item found, value type=%s, is_list=%s, len=%s',
                     type(rounds_value).__name__, isinstance(rounds_value, list),
                     len(rounds_value) if isinstance(rounds_value, list) else 'N/A')
        if not isinstance(rounds_value, list) or not rounds_value:
            return _AggregationStatsMixin._normalize_audio_paths_in_results(algorithm_results)

        # 构建展开后的新列表
        expanded = _AggregationStatsMixin._expand_rounds(algorithm_results, rounds_item, rounds_value)
        return _AggregationStatsMixin._normalize_audio_paths_in_results(expanded)

    @staticmethod
    def _expand_rounds(algorithm_results: list, rounds_item: dict, rounds_value: list) -> list:
        """将 rounds 数组展开为各 output 字段@round:N 文本字段。"""
        expanded = []
        device = rounds_item.get('device', 'default')

        # 保留非 rounds 字段
        for item in algorithm_results:
            if item is rounds_item:
                continue
            expanded.append(item)

        # 展开各轮 output 字段
        for r_idx, r_item in enumerate(rounds_value):
            if not isinstance(r_item, dict):
                continue
            raw_round = r_item.get('round')
            rn = (raw_round + 1) if isinstance(raw_round, int) else (r_idx + 1)
            output = r_item.get('output') or {}
            if isinstance(output, dict):
                for sub_key, val in output.items():
                    if val is None or sub_key == 'evaluation':
                        continue
                    expanded.append({
                        'device': device,
                        'param_code': f'{sub_key}@round:{rn}',
                        'paramCode': f'{sub_key}@round:{rn}',
                        'param_type': 'text',
                        'paramType': 'text',
                        'label': f'{sub_key} (第{rn}轮)',
                        'value': val,
                        'round_number': rn,
                        'roundNumber': rn,
                    })

        # rounds 整体保留（标记为 json）
        rounds_item_copy = dict(rounds_item)
        rounds_item_copy['param_type'] = 'json'
        rounds_item_copy['paramType'] = 'json'
        expanded.append(rounds_item_copy)
        return expanded

    @staticmethod
    def _expand_reference_params_for_report(reference_params):
        """报告页 reference_params 后处理：

        调用 algo_get_reference_params_for_report 做多轮展开，
        兼容 reference_params 是字典（已是报告格式）或 DB 原始列格式。
        """
        if not reference_params:
            return {}
        try:
            from report_service.infrastructure.clients.grpc_clients import _grpc_algo_get_reference_params_for_report
            # 如果已经是扁平字典格式（code -> {code, type, value}），直接原样返回
            if isinstance(reference_params, dict):
                if any(isinstance(v, dict) and ('reference_params_path' in v or 'referenceParamsPath' in v) for v in reference_params.values()):
                    return _grpc_algo_get_reference_params_for_report(reference_params)
                return reference_params
            if isinstance(reference_params, list):
                return _grpc_algo_get_reference_params_for_report(reference_params)
        except Exception:
            logger.debug("gRPC 展开参考参数失败", exc_info=True)
        return reference_params
