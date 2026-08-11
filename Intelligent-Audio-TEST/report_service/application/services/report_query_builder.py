# -*- coding: utf-8 -*-
"""报告查询构建器（report_service 版本）。

从 api_gateway/application/services/report/report_query_builder.py 迁移而来，
保持 ReportQueryBuilder 类及 gRPC helper 函数原有逻辑不变，仅做以下调整：
- 移除 api_gateway 专属依赖（report_utils.metrics_mixin / report_compare_helpers /
  report_utils.resource_mixin），gRPC helper 统一从
  report_service.infrastructure.clients.grpc_clients 导入
- 移除未使用的 typing / query_utils 导入
"""

from typing import List, Optional

# 复用 grpc_clients 中已定义的 gRPC helper，避免重复实现
from report_service.infrastructure.clients.grpc_clients import (
    _grpc_get_dimension_results_by_result_ids as _grpc_get_dim_results,
    _grpc_get_task_case_ids,
    _grpc_get_task_case_ids_batch,
    _grpc_get_test_results_by_task_and_case,
    _grpc_list_testcases_by_ids,
    _grpc_get_task_devices,
    _grpc_get_task_apis,
    _grpc_get_devices_by_ids,
    _grpc_get_apis_by_ids,
)


class ReportQueryBuilder:
    @staticmethod
    def build_test_case_query(
        task_id: int,
        category: Optional[str] = None,
        categories: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        include_untagged: bool = False
    ) -> tuple:
        """
        构建测试用例查询

        Returns:
            (test_cases, test_case_ids, task_cases)
        """
        # 通过 gRPC 获取 TaskCase 列表
        task_cases = _grpc_get_task_case_ids(task_id)
        test_case_ids = [tc.get('test_case_id') for tc in task_cases if tc.get('test_case_id')]

        # 通过 gRPC 批量获取 TestCase 详情
        tc_map = _grpc_list_testcases_by_ids(test_case_ids)
        test_cases = list(tc_map.values())

        # 客户端过滤 category / categories / tags
        if category and category != 'all':
            test_cases = [
                tc for tc in test_cases
                if _tc_group_name(tc) == category
            ]

        if categories and len(categories) > 0:
            cat_set = set(categories)
            test_cases = [
                tc for tc in test_cases
                if _tc_group_name(tc) in cat_set
            ]

        if include_untagged:
            if tags and len(tags) > 0:
                tag_set = set(tags)
                test_cases = [
                    tc for tc in test_cases
                    if _tc_has_any_tag(tc, tag_set) or not _tc_has_tags(tc)
                ]
            else:
                test_cases = [tc for tc in test_cases if not _tc_has_tags(tc)]
        elif tags and len(tags) > 0:
            tag_set = set(tags)
            test_cases = [tc for tc in test_cases if _tc_has_any_tag(tc, tag_set)]

        return test_cases, test_case_ids, task_cases

    @staticmethod
    def build_merged_task_test_case_query(
        source_task_ids: List[int],
        category: Optional[str] = None,
        categories: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        include_untagged: bool = False
    ) -> tuple:
        task_cases = _grpc_get_task_case_ids_batch(source_task_ids)
        test_case_ids = [tc.get('test_case_id') for tc in task_cases if tc.get('test_case_id')]

        tc_map = _grpc_list_testcases_by_ids(test_case_ids)
        test_cases = list(tc_map.values())

        if category and category != 'all':
            test_cases = [tc for tc in test_cases if _tc_group_name(tc) == category]

        if categories and len(categories) > 0:
            cat_set = set(categories)
            test_cases = [tc for tc in test_cases if _tc_group_name(tc) in cat_set]

        if include_untagged:
            if tags and len(tags) > 0:
                tag_set = set(tags)
                test_cases = [tc for tc in test_cases if _tc_has_any_tag(tc, tag_set) or not _tc_has_tags(tc)]
            else:
                test_cases = [tc for tc in test_cases if not _tc_has_tags(tc)]
        elif tags and len(tags) > 0:
            tag_set = set(tags)
            test_cases = [tc for tc in test_cases if _tc_has_any_tag(tc, tag_set)]

        return test_cases, test_case_ids, task_cases

    @staticmethod
    def get_test_results_batch(
        test_case_ids: List[int],
        task_ids: Optional[List[int]] = None
    ) -> List:
        if not test_case_ids:
            return []
        return _grpc_get_test_results_by_task_and_case(test_case_ids, task_ids)

    @staticmethod
    def get_dimension_results_batch(
        result_ids: List[int]
    ) -> tuple:
        """返回 (dim_results_map, dim_stats) 元组，保持与原接口兼容。

        dim_results_map: {result_id: [item_dict, ...]}
        dim_stats: {dimension_id: {name, total_dimension_value, count}}
        """
        if not result_ids:
            return {}, {}
        dim_map = _grpc_get_dim_results(result_ids)
        # 构建 dim_stats
        dim_stats = {}
        for rid, items in dim_map.items():
            for it in items:
                if not isinstance(it, dict):
                    continue
                dim_id = it.get('dimension_id')
                dim_val = it.get('dimension_value') or 0
                dim_name = it.get('dimension_name') or it.get('name')
                if dim_id is None:
                    continue
                if dim_id not in dim_stats:
                    dim_stats[dim_id] = {
                        "name": dim_name,
                        "total_dimension_value": 0,
                        "count": 0
                    }
                dim_stats[dim_id]["total_dimension_value"] += dim_val
                dim_stats[dim_id]["count"] += 1
        return dim_map, dim_stats

    @staticmethod
    def get_task_devices_apis(task_id: int) -> tuple:
        # 通过 gRPC 获取 TaskDevice / TaskAPI
        task_devices = _grpc_get_task_devices(task_id)
        task_apis = _grpc_get_task_apis(task_id)

        device_ids = [td.get('device_id') for td in task_devices if td.get('device_id')]
        api_ids = [ta.get('api_id') for ta in task_apis if ta.get('api_id')]

        devices_map = _grpc_get_devices_by_ids(device_ids) if device_ids else {}
        apis_map = _grpc_get_apis_by_ids(api_ids) if api_ids else {}
        devices = list(devices_map.values())
        apis = list(apis_map.values())

        return devices, apis, task_devices, task_apis

    @staticmethod
    def get_result_types_batch(
        task_id: int,
        device_ids: List[int],
        api_ids: List[int]
    ) -> tuple:
        device_result_types = {}
        api_result_types = {}

        # 通过 gRPC 获取 TestResult
        results = _grpc_get_test_results_by_task_and_case([], task_ids=[task_id])

        if device_ids:
            dev_id_set = set(device_ids)
            device_results = [r for r in results if r.get('device_id') in dev_id_set]
            for result in device_results:
                if result.get('device_id') and result.get('result_data'):
                    import json
                    try:
                        rd = result.get('result_data')
                        if isinstance(rd, str) and rd.strip():
                            result_data = json.loads(rd)
                        elif isinstance(rd, dict):
                            result_data = rd
                        else:
                            result_data = {}
                        result_type = result_data.get('result_type', 'default') if isinstance(result_data, dict) else 'default'
                    except Exception:
                        result_type = 'default'
                    device_result_types[result.get('device_id')] = result_type

        if api_ids:
            api_id_set = set(api_ids)
            api_results = [r for r in results if r.get('api_id') in api_id_set]
            for result in api_results:
                if result.get('api_id') and result.get('result_data'):
                    import json
                    try:
                        rd = result.get('result_data')
                        if isinstance(rd, str) and rd.strip():
                            result_data = json.loads(rd)
                        elif isinstance(rd, dict):
                            result_data = rd
                        else:
                            result_data = {}
                        result_type = result_data.get('result_type', 'default') if isinstance(result_data, dict) else 'default'
                    except Exception:
                        result_type = 'default'
                    api_result_types[result.get('api_id')] = result_type

        return device_result_types, api_result_types

    @staticmethod
    def extract_case_categories_and_tags(test_cases: List) -> tuple:
        case_categories_list = []
        case_tags_list = []
        seen_categories = set()
        seen_tags = set()

        for test_case in test_cases:
            group = _tc_get_group(test_case)
            if group:
                cat_id = group.get('id') if isinstance(group, dict) else getattr(group, 'id', None)
                cat_name = group.get('name') if isinstance(group, dict) else getattr(group, 'name', None)
                if cat_id is not None and cat_id not in seen_categories:
                    seen_categories.add(cat_id)
                    case_categories_list.append({
                        "id": cat_id,
                        "name": cat_name or "未命名分组"
                    })

            tc_tags = _tc_get_tags(test_case)
            for tag in tc_tags:
                tag_id = tag.get('id') if isinstance(tag, dict) else getattr(tag, 'id', None)
                tag_name = tag.get('name') if isinstance(tag, dict) else getattr(tag, 'name', None)
                if tag_id is not None and tag_id not in seen_tags:
                    seen_tags.add(tag_id)
                    case_tags_list.append({
                        "id": tag_id,
                        "name": tag_name or "未命名标签"
                    })

        if not case_categories_list:
            case_categories_list.append({"id": "default_group", "name": "未分类"})

        if not case_tags_list:
            case_tags_list.append({"id": "default_tag", "name": "无标签"})

        return case_categories_list, case_tags_list

    @staticmethod
    def safe_keyword_filter(query, model_class, field_name: str, keyword: Optional[str]):
        """保留原签名，但在 gRPC 模式下不适用——返回原 query。"""
        if not keyword:
            return query
        # gRPC 模式下不支持 SQLAlchemy query 过滤，返回原样
        return query


# ---- TestCase dict/ORM 兼容辅助函数 ----

def _tc_group_name(tc):
    """获取 TestCase 的 group name。"""
    group = _tc_get_group(tc)
    if group is None:
        return None
    return group.get('name') if isinstance(group, dict) else getattr(group, 'name', None)


def _tc_get_group(tc):
    """从 TestCase（dict 或 ORM）读取 group。"""
    if isinstance(tc, dict):
        return tc.get('group')
    return getattr(tc, 'group', None)


def _tc_get_tags(tc):
    """从 TestCase（dict 或 ORM）读取 tags 列表。"""
    if isinstance(tc, dict):
        return tc.get('tags') or []
    return getattr(tc, 'tags', []) or []


def _tc_has_tags(tc):
    """判断 TestCase 是否有 tags。"""
    tags = _tc_get_tags(tc)
    return len(tags) > 0


def _tc_has_any_tag(tc, tag_set):
    """判断 TestCase 是否有任意一个 tag 在 tag_set 中。"""
    tags = _tc_get_tags(tc)
    for tag in tags:
        tag_name = tag.get('name') if isinstance(tag, dict) else getattr(tag, 'name', None)
        if tag_name and tag_name in tag_set:
            return True
    return False
