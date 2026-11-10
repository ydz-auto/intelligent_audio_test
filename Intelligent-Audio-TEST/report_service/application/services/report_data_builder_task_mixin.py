# -*- coding: utf-8 -*-
"""报告数据构建器 —— 任务数据收集 Mixin。

从 report_data_builder.py 拆分而来，承载：
- _validate_task_and_get_results: 任务状态校验 + 收集测试结果（含合并任务溯源）
- _get_dimension_results_batch / _get_aux_params_batch: 批量查询维度结果与 aux 参数
- _get_resource_result_types_batch / _extract_result_type: 批量提取资源结果类型
"""
import json
import logging

from shared.models.common_enums import TaskStatus
from shared.utils.response import error_response
from shared.utils.result_data_store import load_full_result_data

from report_service.application.services.dimension_body_merge import (
    build_coverage,
    merge_body_into_base,
)
from report_service.domain.services.aggregation_strategies import (
    extract_raw_fields,
    needs_raw_response,
)
from report_service.infrastructure.clients.grpc_clients import (
    _grpc_get_dimension_results_by_result_ids as _grpc_get_dim_results,
    _grpc_iter_dimension_results_with_body,
    _grpc_get_dimension_params,
    _grpc_get_task_case_ids,
    _grpc_get_test_results_by_task_ids,
    _grpc_get_test_results_by_ids,
    _grpc_get_cherry_pick_relations,
    _grpc_get_task_merge_relations,
    _grpc_get_task_merge_relations_by_source,
    _grpc_get_tasks_by_ids,
    _dim_id,
    _dim_statistic_method,
)

logger = logging.getLogger(__name__)


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

        # INT-339：cherry-pick 容器任务按挑选关系引用源结果（引用方案 A），
        # 优先于合并关系判定（两容器身份互斥：无 TaskMergeRelation 行）
        cherry_relations = _grpc_get_cherry_pick_relations(task_id)
        if cherry_relations:
            cherry_result_ids = [r.get('result_id') for r in cherry_relations
                                 if r.get('result_id') is not None]
            if not cherry_result_ids:
                return None, None, error_response("生成失败: 挑选合并任务没有引用的测试结果")
            results = _grpc_get_test_results_by_ids(cherry_result_ids)
            if not results:
                return None, None, error_response("生成失败: 挑选合并任务的源结果已全部缺失")
            return task, results, None

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
            if not tasks:
                continue
            # 差异#2 收尾：合并容器任务由 TaskMergeRelation(merged_task_id) 存在性判定（task.type 已废弃）
            relations = _grpc_get_task_merge_relations(tid)
            if relations:
                pending.extend(r.get('source_task_id') for r in relations)
                continue
            leaf_ids.add(tid)
        return list(leaf_ids)

    @staticmethod
    def _get_dimension_results_batch(result_ids):
        """批量查询维度评估结果（轻量：不携带原始响应）。

        INT-2381：原始响应只经 _get_dimension_results_compressed 逐块拉取并在
        块内提取，本方法不再提供 include_body 形态，避免整份 body map 常驻。
        """
        if not result_ids:
            return {}, []

        dim_map = _grpc_get_dim_results(result_ids, include_body=False)

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
    def _load_raw_field_params(all_dimensions):
        """加权维度的 output 参数（dim_id -> [param, ...]），供块内标量提取。"""
        params_by_dim = {}
        for dim in all_dimensions or []:
            if not needs_raw_response(_dim_statistic_method(dim)):
                continue
            dim_id = _dim_id(dim)
            if dim_id is None:
                continue
            try:
                params = _grpc_get_dimension_params(dim_id) or []
            except Exception as e:  # noqa: BLE001 —— 取不到参数时按策略默认路径提取
                logger.warning(
                    "load output params for weighted dimension %s failed: %s", dim_id, e)
                params = []
            params_by_dim[dim_id] = [
                p for p in params
                if isinstance(p, dict) and p.get('param_direction') == 'output'
            ]
        return params_by_dim

    @staticmethod
    def _get_dimension_results_compressed(base_map, result_ids, output_params_by_dim=None):
        """逐块拉取带 body 的维度结果，块内提取标量后立即释放原始响应（INT-2381）。

        旧的「整份 body map 常驻 + 行级合并」在真实任务 402/407 上峰值 ~2.7GB
        （docker VM 6GB 共享 13 服务）。本方法沿用 INT-2379 的行级合并（I1：key
        集合与基础 map 一致；body 失败只丢字段不丢行），但每块拿到后：
          1. 按行合并进基础 map 的行（取值列仍以基础 map 为准）；
          2. 每行调用 extract_raw_fields 把 api_raw_response 压成 raw_fields 标量；
          3. 丢弃原始响应，只保留压缩后的行。
        因此峰值 = 基础 map + 单块原始响应，与总结果数无关。

        Args:
            base_map: 非 body 拉取的完整结果 {result_id: [row, ...]}（完整性基准）
            result_ids: 本次参与聚合的 result_id 列表
            output_params_by_dim: {dimension_id: [output_param, ...]}，加权维度需要
                提取的 field_path 来源；缺省时用加权策略默认路径 errors / length

        Returns:
            (compressed_map, coverage)
            compressed_map：行集合与基础 map 一致，行内不再含 api_raw_response，
                只带 raw_fields（{present, values} 或 None）；
            coverage：沿用 INT-2379 C2 结构（requested/covered/missing/
                missing_total/failed_chunks/dropped_ids/rows_without_body/total_rows/reason）
        """
        base_map = base_map or {}
        params_by_dim = output_params_by_dim or {}
        requested = list(dict.fromkeys(result_ids or []))
        # 只拷贝行列表，行 dict 在块内由 merge_body_into_base 复制后替换
        compressed = {rid: list(rows) for rid, rows in base_map.items()}
        failed_chunks = []
        dropped_ids = []
        matched_ids = []
        missing_ids = []
        total_rows = body_rows_applied = rows_without_body = ignored_body_rows = 0

        for chunk_map, chunk_coverage in _grpc_iter_dimension_results_with_body(requested):
            failed_chunks.extend(chunk_coverage.get('failed_chunks') or [])
            dropped_ids.extend(chunk_coverage.get('dropped_ids') or [])
            # 失败块也必须按基础行参与合并，才能记成 missing（而不是静默消失）
            chunk_ids = [rid for rid in (chunk_coverage.get('requested_ids') or [])
                         if rid in compressed]
            sub_base = {rid: compressed[rid] for rid in chunk_ids}
            merged, stats = merge_body_into_base(sub_base, chunk_map)

            for rid, rows in merged.items():
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    # 聚合只需要原始响应里的标量；请求报文与原始响应同量级，
                    # 一并丢弃（否则整份 body 仍随行常驻，压缩失效）。
                    raw_response = row.pop('api_raw_response', None)
                    row.pop('api_request_body', None)
                    row['raw_fields'] = extract_raw_fields(
                        raw_response, params_by_dim.get(row.get('dimension_id')))
                compressed[rid] = rows

            total_rows += stats['total_rows']
            body_rows_applied += stats['body_rows_applied']
            rows_without_body += stats['rows_without_body']
            ignored_body_rows += stats['ignored_body_rows']
            matched_ids.extend(stats['matched_result_ids'])
            missing_ids.extend(stats['missing_result_ids'])

        coverage = build_coverage(
            {'failed_chunks': failed_chunks, 'dropped_ids': dropped_ids},
            {
                'total_rows': total_rows,
                'body_rows_applied': body_rows_applied,
                'rows_without_body': rows_without_body,
                'ignored_body_rows': ignored_body_rows,
                'matched_result_ids': matched_ids,
                'missing_result_ids': missing_ids,
            },
        )
        return compressed, coverage

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
