# -*- coding: utf-8 -*-
"""报告聚合统计 — 用例列表 Mixin（P4-5 大文件拆分）。

职责：从报告用例子实体构建统一的 case dict，
并完成分页/过滤/排序（供 handle_get_report_cases / handle_search_report_cases 调用）。
"""
from __future__ import annotations

from report_service.application.services.report_aggregation.stats_mixin import _AggregationStatsMixin


class _AggregationCasesMixin:
    """用例列表 Mixin：用例 dict 构建、过滤、分页与排序。"""

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
        expanded_algo = _AggregationStatsMixin._expand_algorithm_results_for_report(
            raw_algo_results, case.get('algorithm_type')
        )
        expanded_ref = _AggregationStatsMixin._expand_reference_params_for_report(raw_ref_params)
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
            if not _AggregationCasesMixin._match_keyword(case, keyword):
                continue
            if category and str(case.get('category')) != str(category):
                continue
            if cat_set and str(case.get('category')) not in cat_set:
                continue
            if not _AggregationCasesMixin._match_tags(case, tag_set, tags, include_untagged):
                continue
            if metrics_filter and not _AggregationCasesMixin._match_metrics(case, metrics_filter):
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
            return _AggregationCasesMixin._sort_by_metric_and_paginate(
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
