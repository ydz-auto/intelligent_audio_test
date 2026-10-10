# -*- coding: utf-8 -*-
"""报告数据构建器 —— 任务数据收集 Mixin。

从 report_data_builder.py 拆分而来，承载：
- _validate_task_and_get_results: 任务状态校验 + 收集测试结果（含合并任务溯源）
- _get_dimension_results_batch / _get_aux_params_batch: 批量查询维度结果与 aux 参数
- _get_resource_result_types_batch / _extract_result_type: 批量提取资源结果类型
"""
import json

from shared.models.common_enums import TaskStatus
from shared.utils.response import error_response
from shared.utils.result_data_store import load_full_result_data

from report_service.infrastructure.clients.grpc_clients import (
    _grpc_get_dimension_results_by_result_ids as _grpc_get_dim_results,
    _grpc_get_dimension_params,
    _grpc_get_task_case_ids,
    _grpc_get_test_results_by_task_ids,
    _grpc_get_task_merge_relations,
    _grpc_get_task_merge_relations_by_source,
    _grpc_get_tasks_by_ids,
)


class ReportDataTaskMixin:
    """任务数据收集：任务校验、维度结果/aux 参数批量查询、结果类型提取。"""

    @staticmethod
    def _validate_task_and_get_results(task_id):
        # 通过 gRPC 获取 Task
        tasks = _grpc_get_tasks_by_ids([task_id])
        task = tasks[0] if tasks else None
        if not task:
            return None, None, error_response("未找到指定任务")

        # 差异#2 收尾：合并容器任务由 TaskMergeRelation(merged_task_id) 存在性判定（task.type 已废弃）
        task_status = task.get('status') if isinstance(task, dict) else task.status

        source_task_ids = []

        merge_relations = _grpc_get_task_merge_relations(task_id)
        if merge_relations:
            # 合并任务：结果取自其源任务（含合并任务重新生成的场景）
            source_task_ids = [r.get('source_task_id') for r in merge_relations]

        elif task_status == TaskStatus.MERGED.value:
            # 源任务被合并后重新生成报告：取最新的合并任务，结果取自其全部原始源任务
            merge_relations = _grpc_get_task_merge_relations_by_source(task_id)
            if merge_relations:
                latest_merged_id = merge_relations[0].get('merged_task_id')
                source_relations = _grpc_get_task_merge_relations(latest_merged_id)
                source_task_ids = [r.get('source_task_id') for r in source_relations]

        elif task_status not in [TaskStatus.COMPLETED.value, TaskStatus.FAILED.value]:
            return None, None, error_response("只有任务状态为completed、failed或merged时才能生成报告")

        if source_task_ids:
            # 源任务集合里若包含合并任务（历史链式合并数据），递归展开为原始源任务
            result_task_ids = ReportDataTaskMixin._expand_leaf_source_task_ids(source_task_ids)
        else:
            result_task_ids = [task_id]

        results = _grpc_get_test_results_by_task_ids(result_task_ids)
        if not results:
            return None, None, error_response("生成失败: 任务没有测试结果数据")

        # 只统计任务 TaskCase 中仍存在的用例结果，避免把已删除用例的执行记录计入统计，
        # 导致设备/API 用例数与任务总用例数（以 TaskCase 为准）不一致
        valid_case_ids = set()
        for tid in result_task_ids:
            for item in _grpc_get_task_case_ids(tid):
                if isinstance(item, dict):
                    valid_case_ids.add(item.get('test_case_id'))
                else:
                    valid_case_ids.add(getattr(item, 'test_case_id', item))
        if valid_case_ids:
            results = [r for r in results if r.get('test_case_id') in valid_case_ids]
        if not results:
            return None, None, error_response("生成失败: 任务没有测试结果数据")

        return task, results, None

    @staticmethod
    def _expand_leaf_source_task_ids(task_ids):
        """递归展开合并任务为原始源任务（叶子），兼容历史链式合并数据。"""
        leaf_ids = set()
        pending = list(task_ids)
        visited = set()
        while pending:
            tid = pending.pop()
            if tid in visited:
                continue
            visited.add(tid)
            tasks = _grpc_get_tasks_by_ids([tid])
            t = tasks[0] if tasks else None
            if not t:
                continue
            t_type = t.get('type') if isinstance(t, dict) else t.type
            if t_type == 'merged':
                relations = _grpc_get_task_merge_relations(tid)
                if relations:
                    pending.extend(r.get('source_task_id') for r in relations)
                    continue
            leaf_ids.add(tid)
        return list(leaf_ids)

    @staticmethod
    def _get_dimension_results_batch(result_ids):
        if not result_ids:
            return {}, []

        dim_map = _grpc_get_dim_results(result_ids)

        dim_results_map = {}
        dim_stats = {}

        for rid, items in dim_map.items():
            for it in items:
                if not isinstance(it, dict):
                    continue
                dim_id = it.get('dimension_id')
                dim_val = it.get('dimension_value') or 0
                dim_name = it.get('dimension_name') or it.get('name')

                if rid not in dim_results_map:
                    dim_results_map[rid] = []
                dim_results_map[rid].append(it)

                if dim_id is not None:
                    if dim_id not in dim_stats:
                        dim_stats[dim_id] = {
                            "name": dim_name,
                            "total_dimension_value": 0,
                            "count": 0
                        }
                    dim_stats[dim_id]["total_dimension_value"] += dim_val
                    dim_stats[dim_id]["count"] += 1

        return dim_results_map, dim_stats

    @staticmethod
    def _get_resource_result_types_batch(task_id_or_ids, device_ids, api_ids):
        device_result_types = {}
        api_result_types = {}

        if isinstance(task_id_or_ids, list):
            results = _grpc_get_test_results_by_task_ids(task_id_or_ids)
        else:
            results = _grpc_get_test_results_by_task_ids([task_id_or_ids])

        if device_ids:
            dev_id_set = set(device_ids)
            device_results = [r for r in results if r.get('device_id') in dev_id_set]
            for result in device_results:
                if result.get('device_id') and result.get('result_data'):
                    full_data = load_full_result_data(result.get('result_data'), result.get('result_data_path'))
                    result_type = ReportDataTaskMixin._extract_result_type(full_data)
                    device_result_types[result.get('device_id')] = result_type

        if api_ids:
            api_id_set = set(api_ids)
            api_results = [r for r in results if r.get('api_id') in api_id_set]
            for result in api_results:
                if result.get('api_id') and result.get('result_data'):
                    full_data = load_full_result_data(result.get('result_data'), result.get('result_data_path'))
                    result_type = ReportDataTaskMixin._extract_result_type(full_data)
                    api_result_types[result.get('api_id')] = result_type

        return device_result_types, api_result_types

    @staticmethod
    def _extract_result_type(result_data):
        if not result_data:
            return 'default'
        try:
            if isinstance(result_data, str) and result_data.strip():
                result_data_dict = json.loads(result_data)
            elif isinstance(result_data, dict):
                result_data_dict = result_data
            else:
                return 'default'
            return result_data_dict.get('result_type', 'default') if isinstance(result_data_dict, dict) else 'default'
        except Exception:
            return 'default'
