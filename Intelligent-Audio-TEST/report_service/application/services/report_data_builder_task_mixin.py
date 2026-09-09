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

        task_type = task.get('type') if isinstance(task, dict) else task.type
        task_status = task.get('status') if isinstance(task, dict) else task.status

        if task_type == 'merged' and task_status == TaskStatus.COMPLETED.value:
            merge_relations = _grpc_get_task_merge_relations(task_id)
            if merge_relations:
                source_task_ids = [r.get('source_task_id') for r in merge_relations]
                results = _grpc_get_test_results_by_task_ids(source_task_ids)
            else:
                results = _grpc_get_test_results_by_task_ids([task_id])
            if not results:
                return None, None, error_response("生成失败: 合并任务没有测试结果数据")
            return task, results, None

        elif task_type == 'merged':
            merge_relations = _grpc_get_task_merge_relations(task_id)
            if merge_relations:
                source_task_ids = [r.get('source_task_id') for r in merge_relations]
                results = _grpc_get_test_results_by_task_ids(source_task_ids)
            else:
                results = _grpc_get_test_results_by_task_ids([task_id])
            if not results:
                return None, None, error_response("生成失败: 合并任务没有测试结果数据")
            return task, results, None

        elif task_status == TaskStatus.MERGED.value:
            merge_relations = _grpc_get_task_merge_relations_by_source(task_id)
            if merge_relations:
                merged_task_id = merge_relations[0].get('merged_task_id')
                source_relations = _grpc_get_task_merge_relations(merged_task_id)
                source_task_ids = [r.get('source_task_id') for r in source_relations]
                results = _grpc_get_test_results_by_task_ids(source_task_ids)
            else:
                results = _grpc_get_test_results_by_task_ids([task_id])
            if not results:
                return None, None, error_response("生成失败: 任务没有测试结果数据")
            return task, results, None

        elif task_status not in [TaskStatus.COMPLETED.value, TaskStatus.FAILED.value]:
            return None, None, error_response("只有任务状态为completed、failed或merged时才能生成报告")

        results = _grpc_get_test_results_by_task_ids([task_id])
        if not results:
            return None, None, error_response("生成失败: 任务没有测试结果数据")

        return task, results, None

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
