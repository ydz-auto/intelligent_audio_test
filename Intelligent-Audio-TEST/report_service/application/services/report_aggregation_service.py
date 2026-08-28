# -*- coding: utf-8 -*-
"""报告聚合统计服务。

职责：
- 从 TestResult / Dimension / Device / API 等数据源计算平均值、正态分布、资源列表等统计信息
- 从报告用例子实体构建分页/过滤/排序后的用例列表
- 构建导出数据及文件载荷

遵循 DDD 分层：application 层服务，被 handler 调用，
不感知 ORM/PO，通过 gRPC 客户端和仓储获取数据。
"""
from __future__ import annotations

from typing import List, Optional
import logging

from shared.utils.audio_path_utils import normalize_audio_path
from report_service.application.services.report_helpers import ReportHelpers
from report_service.application.services.report_utils import ReportUtils
from report_service.infrastructure.clients.grpc_clients import (
    _grpc_list_dimensions_all,
    _grpc_get_dimension_params,
    _grpc_get_dimension_results_by_result_ids as _grpc_get_dim_results,
    _grpc_get_task_devices,
    _grpc_get_task_apis,
    _grpc_get_devices_by_ids,
    _grpc_get_apis_by_ids,
    _grpc_list_testcases_by_ids,
    _dim_id, _dim_name,
)

logger = logging.getLogger(__name__)


def _r_get(r, key, default=None):
    """从 dict 或对象中安全取值。"""
    if isinstance(r, dict):
        return r.get(key, default)
    return getattr(r, key, default)


class ReportAggregationService:
    """报告聚合统计服务。

    将原 ReportQueryHandler._calculate_averages 中的业务逻辑拆分至此，
    handler 仅负责请求解析和响应格式化。
    """

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
        used_dim_ids = ReportAggregationService._collect_used_dim_ids(test_results)
        all_dimensions = [d for d in all_dimensions_all if _dim_id(d) in used_dim_ids] if used_dim_ids else all_dimensions_all

        # 过滤掉 visible_in_report=False 的维度
        all_output_dim_ids, visible_dim_ids = ReportAggregationService._collect_visible_dim_ids(all_dimensions_all)
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
    # 子方法：资源列表聚合
    # ------------------------------------------------------------------

    @staticmethod
    def _aggregate_resource_list(task, task_id: int) -> tuple:
        """聚合设备/API 资源列表，返回 (resources, resource_headers)。"""
        task_devices = _grpc_get_task_devices(task_id)
        task_apis = _grpc_get_task_apis(task_id)

        device_ids = [td.get('device_id') if isinstance(td, dict) else getattr(td, 'device_id', None) for td in task_devices]
        device_ids = [did for did in device_ids if did is not None]
        api_ids = [ta.get('api_id') if isinstance(ta, dict) else getattr(ta, 'api_id', None) for ta in task_apis]
        api_ids = [aid for aid in api_ids if aid is not None]

        devices_map = _grpc_get_devices_by_ids(device_ids) if device_ids else {}
        apis_map = _grpc_get_apis_by_ids(api_ids) if api_ids else {}

        time_prefix = ReportHelpers.get_task_time_prefix(task)
        resources = []
        resource_headers = []

        # 设备资源
        for td in task_devices:
            td_device_id = td.get('device_id') if isinstance(td, dict) else getattr(td, 'device_id', None)
            d = devices_map.get(td_device_id) if td_device_id else None
            if d:
                key = ReportAggregationService._build_device_resource_key(time_prefix, d)
                resources.append(key)
                resource_headers.append(
                    ReportAggregationService._build_device_resource_header(task, key, d)
                )

        # API 资源
        for ta in task_apis:
            ta_api_id = ta.get('api_id') if isinstance(ta, dict) else getattr(ta, 'api_id', None)
            a = apis_map.get(ta_api_id) if ta_api_id else None
            if a:
                key = ReportAggregationService._build_api_resource_key(time_prefix, a)
                resources.append(key)
                resource_headers.append(
                    ReportAggregationService._build_api_resource_header(task, key, a)
                )

        return resources, resource_headers

    @staticmethod
    def _build_device_resource_key(time_prefix: str, d) -> str:
        """构建设备资源唯一键。"""
        d_id = d.get('id') if isinstance(d, dict) else getattr(d, 'id', None)
        d_name = d.get('name') if isinstance(d, dict) else getattr(d, 'name', '')
        return f"{time_prefix}-{d_id}-{str(d_name).lower()}"

    @staticmethod
    def _build_device_resource_header(task, key: str, d) -> dict:
        """构建设备资源表头。"""
        d_id = d.get('id') if isinstance(d, dict) else getattr(d, 'id', None)
        d_name = d.get('name') if isinstance(d, dict) else getattr(d, 'name', '')
        d_app_version = d.get('app_version') if isinstance(d, dict) else getattr(d, 'app_version', None)
        return {
            "key": key,
            "label": ReportUtils._format_resource_label(task, d_name, d_app_version, use_time_prefix=False) or key,
            "type": "device",
            "id": int(d_id) if d_id is not None else None,
            "name": str(d_name),
            "version": str(d_app_version) if d_app_version is not None else None,
            "editable": True,
        }

    @staticmethod
    def _build_api_resource_key(time_prefix: str, a) -> str:
        """构建 API 资源唯一键。"""
        a_id = a.get('id') if isinstance(a, dict) else getattr(a, 'id', None)
        a_name = a.get('name') if isinstance(a, dict) else getattr(a, 'name', '')
        return f"{time_prefix}-{a_id}-{str(a_name).lower()}"

    @staticmethod
    def _build_api_resource_header(task, key: str, a) -> dict:
        """构建 API 资源表头。"""
        a_id = a.get('id') if isinstance(a, dict) else getattr(a, 'id', None)
        a_name = a.get('name') if isinstance(a, dict) else getattr(a, 'name', '')
        version = ReportUtils._extract_api_version(a)
        return {
            "key": key,
            "label": ReportUtils._format_resource_label(task, a_name, version, use_time_prefix=False) or key,
            "type": "api",
            "id": int(a_id) if a_id is not None else None,
            "name": str(a_name),
            "version": version,
            "editable": True,
        }

    # ------------------------------------------------------------------
    # 子方法：测试用例映射
    # ------------------------------------------------------------------

    @staticmethod
    def _load_test_cases_map(test_results: list) -> dict:
        """加载测试用例映射表，返回 {test_case_id: test_case}。"""
        test_case_ids_to_fetch = set()
        for result in test_results:
            tc_id = _r_get(result, 'test_case_id')
            if tc_id is not None:
                test_case_ids_to_fetch.add(tc_id)
        test_cases_map = {}
        if test_case_ids_to_fetch:
            tcs = _grpc_list_testcases_by_ids(list(test_case_ids_to_fetch))
            for tc in tcs.values() if isinstance(tcs, dict) else tcs:
                tc_id = tc.get('id') if isinstance(tc, dict) else getattr(tc, 'id', None)
                if tc_id is not None:
                    test_cases_map[tc_id] = tc
        return test_cases_map

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
            cat_name = ReportAggregationService._get_case_category_name(test_case)

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
    # 用例列表构建（供 handle_get_report_cases / handle_search_report_cases 调用）
    # ==================================================================

    @staticmethod
    def build_case_dict_from_entity(c) -> dict:
        """从用例子实体构建统一的 case dict。"""
        rs = c.result_summary or {}
        return {
            'test_case_id': c.test_case_id,
            'name': rs.get('name'),
            'description': rs.get('description'),
            'category': rs.get('category'),
            'tags': rs.get('tags') or [],
            'metrics': rs.get('metrics') or {},
            'results': rs.get('results') or [],
            'audios': rs.get('audios') or [],
            'reference_params': rs.get('reference_params') or {},
            'algorithm_results': rs.get('algorithm_results') or {},
            'algorithm_type': rs.get('algorithm_type'),
            'logs': rs.get('logs'),
        }

    @staticmethod
    def build_case_item(case: dict) -> dict:
        """构建前端用例项（展开算法结果和参考参数）。"""
        raw_algo_results = case.get('algorithm_results')
        raw_ref_params = case.get('reference_params')
        expanded_algo = ReportAggregationService._expand_algorithm_results_for_report(
            raw_algo_results, case.get('algorithm_type')
        )
        expanded_ref = ReportAggregationService._expand_reference_params_for_report(raw_ref_params)
        return {
            "id": case.get('test_case_id'),
            "name": case.get('name'),
            "description": case.get('description') or "",
            "category": case.get('category'),
            "tags": case.get('tags') or [],
            "metrics": case.get('metrics') or {},
            "results": case.get('results') or [],
            "audios": case.get('audios') or [],
            "referenceParams": expanded_ref,
            "algorithmResults": expanded_algo,
            "algorithmType": case.get('algorithm_type'),
            "logs": case.get('logs')
        }

    @staticmethod
    def filter_cases(all_cases: list, keyword: str, category: str, tags: list) -> list:
        """按 keyword/category/tags 客户端过滤用例列表。"""
        filtered = []
        for case in all_cases:
            if not isinstance(case, dict):
                continue
            if keyword:
                kw = str(keyword).lower()
                case_name = str(case.get('name') or '').lower()
                case_desc = str(case.get('description') or '').lower()
                if kw not in case_name and kw not in case_desc:
                    continue
            if category:
                if str(case.get('category')) != str(category):
                    continue
            if tags:
                case_tags = case.get('tags') or []
                if not all(str(t) in [str(ct) for ct in case_tags] for t in tags):
                    continue
            filtered.append(case)
        return filtered

    @staticmethod
    def paginate(cases: list, page: int, per_page: int) -> tuple:
        """分页，返回 (paged_cases, total, pages)。"""
        total = len(cases)
        start = (page - 1) * per_page
        end = start + per_page
        paged = cases[start:end]
        pages = (total + per_page - 1) // per_page if per_page > 0 else 1
        return paged, total, pages

    @staticmethod
    def parse_tags(raw_tags) -> list:
        """解析 tags 参数，支持逗号分隔字符串或列表。"""
        tags = []
        if isinstance(raw_tags, list):
            for t in raw_tags:
                if t is None:
                    continue
                parts = [p.strip() for p in str(t).split(',') if p.strip()]
                tags.extend(parts)
        else:
            tags = [t.strip() for t in str(raw_tags).split(',') if t.strip()]
        return tags

    @staticmethod
    def filter_cases_advanced(
        all_cases: list, keyword, category, categories, tags,
        include_untagged: bool, metrics_filter: list
    ) -> list:
        """高级过滤：支持 keyword/category/categories/tags/metrics 多条件。"""
        filtered = []
        tag_set = set(str(t) for t in tags)
        cat_list = [str(c) for c in categories if c] if categories else []
        cat_set = set(cat_list) if cat_list else None

        for case in all_cases:
            if not isinstance(case, dict):
                continue
            if not ReportAggregationService._match_keyword(case, keyword):
                continue
            if category and str(case.get('category')) != str(category):
                continue
            if cat_set and str(case.get('category')) not in cat_set:
                continue
            if not ReportAggregationService._match_tags(case, tag_set, tags, include_untagged):
                continue
            if metrics_filter and not ReportAggregationService._match_metrics(case, metrics_filter):
                continue
            filtered.append(case)
        return filtered

    @staticmethod
    def _match_keyword(case: dict, keyword) -> bool:
        """检查 case 是否匹配 keyword（name/description/test_case_id）。"""
        if not keyword:
            return True
        kw = str(keyword).lower()
        case_name = str(case.get('name') or '').lower()
        case_desc = str(case.get('description') or '').lower()
        case_tc_id = str(case.get('test_case_id') or '').lower()
        return kw in case_name or kw in case_desc or kw in case_tc_id

    @staticmethod
    def _match_tags(case: dict, tag_set: set, tags: list, include_untagged: bool) -> bool:
        """检查 case 是否匹配 tags 过滤条件。"""
        case_tags = case.get('tags') or []
        if include_untagged and not tag_set:
            return not case_tags
        if tag_set:
            case_tag_strs = [str(ct) for ct in case_tags]
            return any(str(t) in case_tag_strs for t in tags)
        return True

    @staticmethod
    def _match_metrics(case: dict, metrics_filter: list) -> bool:
        """检查 case 的 metrics 中是否包含任一筛选指标名。"""
        case_metrics = case.get('metrics') or {}
        if not isinstance(case_metrics, dict):
            return False
        metric_names = set()
        for v in case_metrics.values():
            if isinstance(v, dict):
                metric_names.update(v.keys())
        return any(str(m) in metric_names for m in metrics_filter)

    @staticmethod
    def sort_and_paginate_cases(
        filtered: list, sort_by: str, sort_order: str,
        sort_metric: str, page: int, per_page: int
    ) -> tuple:
        """排序并分页用例列表，返回 (paged_cases, total, pages)。"""
        asc = (sort_order != 'desc')

        if sort_by == 'metric' and sort_metric:
            return ReportAggregationService._sort_by_metric_and_paginate(
                filtered, str(sort_metric), asc, page, per_page
            )

        # 常规排序
        if sort_by == 'category':
            filtered.sort(key=lambda c: str(c.get('category') or ''), reverse=not asc)
        elif sort_by == 'createdat':
            filtered.sort(key=lambda c: str(c.get('test_case_id') or ''), reverse=not asc)
        else:
            filtered.sort(key=lambda c: str(c.get('name') or ''), reverse=not asc)

        total = len(filtered)
        start = (page - 1) * per_page
        paged_cases = filtered[start:start + per_page]
        pages = (total + per_page - 1) // per_page if per_page > 0 else 1
        return paged_cases, total, pages

    @staticmethod
    def _sort_by_metric_and_paginate(filtered: list, metric_name: str, asc: bool, page: int, per_page: int) -> tuple:
        """按评估维度排序并分页。"""
        def _metric_key(case_item):
            m = case_item.get('metrics') or {}
            if isinstance(m, dict):
                vals = []
                for v in m.values():
                    if isinstance(v, dict) and metric_name in v:
                        try:
                            vals.append(float(v[metric_name]))
                        except (TypeError, ValueError):
                            pass
                if vals:
                    avg = sum(vals) / len(vals)
                    return (0, avg)
            return (1, 0)

        with_metric = [c for c in filtered if _metric_key(c)[0] == 0]
        without_metric = [c for c in filtered if _metric_key(c)[1] == 1]
        with_metric.sort(key=lambda c: _metric_key(c)[1], reverse=not asc)
        filtered = with_metric + without_metric
        total = len(filtered)
        start = (page - 1) * per_page
        paged_cases = filtered[start:start + per_page]
        pages = (total + per_page - 1) // per_page if per_page > 0 else 1
        return paged_cases, total, pages

    # ==================================================================
    # 导出数据处理（供 handle_export_reports 调用）
    # ==================================================================

    @staticmethod
    def build_export_data(report_ids: list, repository) -> list:
        """查询指定报告及其摘要信息，构建导出数据列表。"""
        export_data = []
        for rid in report_ids:
            try:
                aggregate = repository.get_by_id(int(rid))
                if aggregate is None:
                    continue
                summaries = repository.load_summaries(int(rid))
            except Exception:
                continue

            summary_info = summaries[0].metadata if summaries else {}
            if summary_info:
                total_cases = summary_info.get('total_cases') or 0
                pass_rate = summary_info.get('pass_rate') or 0
            else:
                total_cases = 0
                pass_rate = 0

            gen_time = ReportAggregationService._format_generation_time(aggregate.created_at)

            export_data.append({
                "报告ID": str(aggregate.id),
                "报告名称": aggregate.config.get('name') if aggregate.config else None,
                "报告类型": aggregate.report_type,
                "生成时间": gen_time,
                "总用例数": str(total_cases),
                "成功率": f"{pass_rate}%",
                "分析结论": (aggregate.config.get('analysis') if aggregate.config else None) or "无"
            })
        return export_data if export_data else None

    @staticmethod
    def _format_generation_time(created_at) -> str:
        """格式化报告生成时间。"""
        if not created_at:
            return "N/A"
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(str(created_at).replace('Z', '+00:00'))
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            return "N/A"

    @staticmethod
    def build_export_payload(export_data: list, format_type: str) -> dict:
        """根据格式类型构建导出响应，返回包含 base64 编码文件内容的字典。"""
        import base64
        import io as _io
        from shared.utils.query_utils import now_cst

        if format_type == 'excel':
            return ReportAggregationService._build_excel_payload(export_data, _io, base64, now_cst)
        elif format_type == 'pdf':
            return ReportAggregationService._build_pdf_payload(export_data, _io, base64, now_cst)
        else:
            return ReportAggregationService._build_csv_payload(export_data, _io, base64, now_cst)

    @staticmethod
    def _build_excel_payload(export_data: list, _io, base64, now_cst) -> dict:
        """构建 Excel 导出响应。"""
        import pandas as pd
        df = pd.DataFrame(export_data)
        output = _io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='报告')
        output.seek(0)
        filename = f"reports_export_{now_cst().strftime('%Y%m%d')}.xlsx"
        mime_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        return {
            'filename': filename,
            'format': 'excel',
            'content_base64': base64.b64encode(output.getvalue()).decode('utf-8'),
            'mime_type': mime_type,
        }

    @staticmethod
    def _build_pdf_payload(export_data: list, _io, base64, now_cst) -> dict:
        """构建 PDF 导出响应。"""
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

        output = _io.BytesIO()
        doc = SimpleDocTemplate(output, pagesize=landscape(A4))
        elements = []

        data = [list(export_data[0].keys())]
        for item in export_data:
            data.append(list(item.values()))

        table = Table(data)
        style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.gray),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ])
        table.setStyle(style)
        elements.append(table)

        doc.build(elements)
        output.seek(0)
        filename = f"reports_export_{now_cst().strftime('%Y%m%d')}.pdf"
        mime_type = 'application/pdf'
        return {
            'filename': filename,
            'format': 'pdf',
            'content_base64': base64.b64encode(output.getvalue()).decode('utf-8'),
            'mime_type': mime_type,
        }

    @staticmethod
    def _build_csv_payload(export_data: list, _io, base64, now_cst) -> dict:
        """构建 CSV 导出响应。"""
        buf = _io.BytesIO()
        buf.write('\ufeff'.encode('utf-8-sig'))
        headers = list(export_data[0].keys())
        buf.write((",".join(headers) + "\n").encode('utf-8-sig'))
        for row in export_data:
            csv_row = [row[h] for h in headers]
            csv_row = [f'"{r}"' if ',' in str(r) else str(r) for r in csv_row]
            buf.write((",".join(csv_row) + "\n").encode('utf-8-sig'))
        buf.seek(0)
        filename = f"reports_export_{now_cst().strftime('%Y%m%d')}.csv"
        mime_type = 'text/csv'
        return {
            'filename': filename,
            'format': 'csv',
            'content_base64': base64.b64encode(buf.getvalue()).decode('utf-8'),
            'mime_type': mime_type,
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
            return ReportAggregationService._normalize_audio_paths_in_results(algorithm_results)

        rounds_value = rounds_item.get('value')
        logger.debug('[expand_algo] rounds_item found, value type=%s, is_list=%s, len=%s',
                     type(rounds_value).__name__, isinstance(rounds_value, list),
                     len(rounds_value) if isinstance(rounds_value, list) else 'N/A')
        if not isinstance(rounds_value, list) or not rounds_value:
            return ReportAggregationService._normalize_audio_paths_in_results(algorithm_results)

        # 构建展开后的新列表
        expanded = ReportAggregationService._expand_rounds(algorithm_results, rounds_item, rounds_value)
        return ReportAggregationService._normalize_audio_paths_in_results(expanded)

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
