# -*- coding: utf-8 -*-
"""报告查询处理器 Mixin — 平均值统计 / 用例日志下载（从 report_handlers.py 拆分，P4-5）。

handle_get_case_averages / handle_download_case_logs 及其私有查询辅助。
"""
import logging

from report_service.application.handlers._report_case_filters import (
    extract_case_ids,
    filter_results_by_case_ids,
    filter_test_cases,
    find_result_by_case_id,
)

logger = logging.getLogger(__name__)


class ReportStatsQueryMixin:
    """平均值统计与日志下载（依赖 self.repository）"""

    def handle_get_case_averages(self, params_dict: dict) -> dict:
        """处理按分组和标签查询用例平均值。

        流程：解析参数 -> 查询用例和结果 -> 计算平均值/正态分布/资源列表 -> 格式化响应。

        Args:
            params_dict: 参数字典，含 task_id/category/tags/categories/include_untagged

        Returns:
            dict: 平均值统计响应
        """
        from report_service.application.services.report_helpers import ReportHelpers
        from report_service.application.services.report_utils import ReportUtils

        task_id = params_dict.get('task_id')
        category = params_dict.get('category')
        tags = params_dict.get('tags') or []
        categories = params_dict.get('categories') or []
        include_untagged = params_dict.get('include_untagged') or False

        if not task_id:
            return {'success': False, 'message': '缺少必要参数: task_id'}

        query_result = self._query_cases_for_averages(
            task_id, category, categories, tags, include_untagged
        )
        if not isinstance(query_result, tuple):
            return query_result
        task, filtered_case_ids, test_results = query_result

        stats = self._calculate_averages(task, filtered_case_ids, test_results, task_id)

        return {
            "total_cases": len(stats['filtered_case_ids']),
            "total_results": len(stats['test_results']),
            "overall_averages": stats['overall_averages'],
            "overall_averages_map": stats['averages_map'],
            "metric_data": ReportUtils.flatten_metric_data(stats['metric_data'], {}, stats['metric_name_to_id']),
            "raw_data": ReportUtils.flatten_raw_data(stats['raw_data']),
            "normal_distribution": stats['normal_distribution_data'],
            "resources": stats['resources'],
            "resource_headers": stats['resource_headers'],
            "filters": {
                "category": category,
                "tags": tags
            }
        }

    def handle_download_case_logs(self, report_id: int, case_id: str) -> dict:
        """处理下载用例日志。

        查询报告关联任务的合并关系、TestResult，从存储列出 case 日志文件，
        打包成 ZIP 以 base64 编码返回。

        Args:
            report_id: 报告 ID
            case_id: 用例 ID

        Returns:
            dict: {filename, content_base64, size} 或 {success: False, message}
        """
        query_result = self._query_case_logs(report_id, case_id)
        if not isinstance(query_result, tuple):
            return query_result
        task_ids_to_search, test_result = query_result

        return self._format_logs_download(task_ids_to_search, test_result, report_id, case_id)

    # ---- 日志下载私有辅助 ----

    def _query_case_logs(self, report_id: int, case_id: str):
        """查询用例日志相关数据。

        Args:
            report_id: 报告 ID
            case_id: 用例 ID

        Returns:
            tuple(task_ids_to_search, test_result) 或错误 dict
        """
        from report_service.infrastructure.clients.grpc_clients import _grpc_get_test_results_by_task_ids

        aggregate = self.repository.get_by_id(report_id)
        if aggregate is None:
            return {'success': False, 'message': '未找到测试报告'}

        task_id = aggregate.task_id
        if not task_id:
            return {'success': False, 'message': '该报告没有关联的任务ID'}

        # 通过 gRPC 查询 TaskMergeRelation
        task_ids_to_search = [task_id]
        try:
            from report_service.infrastructure.clients.grpc_clients import _grpc_get_task_merge_relations
            relations = _grpc_get_task_merge_relations(task_id)
            if relations:
                task_ids_to_search = [it.get('source_task_id') for it in relations]
        except Exception:
            logger.debug("gRPC 查询任务合并关系失败 task_id=%s", task_id, exc_info=True)

        # 通过 gRPC 查询 TestResult（按 task_id 批量查询后客户端过滤 test_case_id）
        all_test_results = _grpc_get_test_results_by_task_ids(task_ids_to_search)
        test_result = find_result_by_case_id(all_test_results, case_id)

        return task_ids_to_search, test_result

    @staticmethod
    def _format_logs_download(task_ids_to_search: list, test_result, report_id: int, case_id: str) -> dict:
        """根据查询到的日志数据构建 ZIP 并以 base64 编码返回。

        Args:
            task_ids_to_search: 需搜索的任务 ID 列表
            test_result: 测试结果对象
            report_id: 报告 ID
            case_id: 用例 ID

        Returns:
            dict: {filename, content_base64, size} 或 {success: False, message}
        """
        import base64
        import io as _io
        import json as _json
        import os as _os
        import zipfile as _zipfile
        from shared.infrastructure.storage import storage
        from shared.utils.result_data_store import load_full_result_data

        zip_filename = f"case_{case_id}_logs.zip"

        zip_buffer = _io.BytesIO()
        found_any = False
        with _zipfile.ZipFile(zip_buffer, 'w', _zipfile.ZIP_DEFLATED) as zf:
            found_any = ReportStatsQueryMixin._write_case_log_files(
                zf, task_ids_to_search, case_id, found_any)

            full_data = {}
            if test_result:
                tr_result_data = test_result.get('result_data') if isinstance(test_result, dict) else getattr(test_result, 'result_data', None)
                tr_result_data_path = test_result.get('result_data_path') if isinstance(test_result, dict) else getattr(test_result, 'result_data_path', None)
                full_data = load_full_result_data(tr_result_data, tr_result_data_path)
            if test_result and full_data and 'adjusted_reference_params' in full_data:
                adjusted_params = full_data['adjusted_reference_params']
                if adjusted_params:
                    params_json = _json.dumps(adjusted_params, ensure_ascii=False, indent=2)
                    zf.writestr("adjusted_reference_params.json", params_json)

        if not found_any:
            return {'success': False, 'message': '未找到用例日志目录'}

        zip_buffer.seek(0)
        zip_data = zip_buffer.getvalue()
        total_size = len(zip_data)

        return {
            'filename': zip_filename,
            'content_base64': base64.b64encode(zip_data).decode('utf-8'),
            'size': total_size,
        }

    @staticmethod
    def _write_case_log_files(zf, task_ids_to_search: list, case_id: str, found_any: bool) -> bool:
        """遍历各任务从存储收集 case 日志文件写入 ZIP。返回是否有文件被写入。"""
        from shared.infrastructure.storage import storage

        for search_task_id in task_ids_to_search:
            # OSS: 列出 case-result bucket 下 {task_id}/{case_id}/ 的所有文件
            oss_prefix = f'{search_task_id}/{case_id}/'
            try:
                oss_keys = storage.list_objects('case_result', prefix=oss_prefix)
            except Exception:
                oss_keys = []
            if not oss_keys:
                continue
            found_any = True
            for oss_key in oss_keys:
                # 下载文件内容
                try:
                    file_data = storage.load_bytes(f'case_result/{oss_key}')
                    arcname = oss_key[len(oss_prefix):]  # 去掉前缀
                    if len(task_ids_to_search) > 1:
                        arcname = _os_path_join(f"task_{search_task_id}", arcname)
                    zf.writestr(arcname, file_data)
                except Exception:
                    continue
        return found_any

    # ---- 平均值统计私有辅助 ----

    def _query_cases_for_averages(self, task_id: int, category, categories, tags, include_untagged):
        """查询用例和结果（含任务解析、合并关系处理）。

        Args:
            task_id: 任务 ID
            category: 单个分类
            categories: 分类列表
            tags: 标签列表
            include_untagged: 是否包含未标记用例

        Returns:
            tuple(task, filtered_case_ids, test_results) 或错误 dict
        """
        from report_service.infrastructure.clients.grpc_clients import _grpc_get_tasks_by_ids

        _tasks = _grpc_get_tasks_by_ids([task_id])
        task = _tasks[0] if _tasks else None
        if not task:
            return {'success': False, 'message': '未找到指定任务'}

        # 通过 gRPC 查询 TaskMergeRelation
        task_type = task.get('type') if isinstance(task, dict) else getattr(task, 'type', None)
        if task_type == 'merged':
            merge_relations = []
            try:
                from report_service.infrastructure.clients.grpc_clients import _grpc_get_task_merge_relations
                merge_relations = _grpc_get_task_merge_relations(task_id)
            except Exception:
                logger.debug("gRPC 查询合并任务关系失败 task_id=%s", task_id, exc_info=True)
            if merge_relations:
                source_task_ids = [it.get('source_task_id') for it in merge_relations]
                task_id_filter = source_task_ids
                result_task_filter = source_task_ids
            else:
                task_id_filter = task_id
                result_task_filter = task_id
        else:
            task_id_filter = task_id
            result_task_filter = task_id

        filtered_case_ids, test_results = self._query_test_cases_and_results(
            task_id_filter, result_task_filter,
            category, categories, tags, include_untagged
        )
        return task, filtered_case_ids, test_results

    def _query_test_cases_and_results(self, task_id_filter, result_task_filter,
                                      category, categories, tags, include_untagged):
        """查询测试用例和结果，返回 (filtered_case_ids, test_results)。

        Args:
            task_id_filter: 任务 ID 过滤（int 或 list）
            result_task_filter: 结果任务过滤（int 或 list）
            category: 单个分类
            categories: 分类列表
            tags: 标签列表
            include_untagged: 是否包含未标记用例

        Returns:
            tuple(filtered_case_ids, test_results)
        """
        from report_service.application.services.report_query_builder import (
            _grpc_get_task_case_ids,
        )
        from report_service.infrastructure.clients.grpc_clients import (
            _grpc_list_testcases_by_ids,
            _grpc_get_test_results_by_task_ids,
        )

        # 通过 gRPC 查询 TaskCase（获取 task 关联的 test_case_id 列表）
        if isinstance(task_id_filter, list):
            all_tc_ids = set()
            for tid in task_id_filter:
                tc_ids = _grpc_get_task_case_ids(tid)
                all_tc_ids.update(tc_ids)
            test_case_ids = list(all_tc_ids)
        else:
            test_case_ids = _grpc_get_task_case_ids(task_id_filter)

        # 通过 gRPC 批量查询 TestCase
        test_cases = _grpc_list_testcases_by_ids(test_case_ids) if test_case_ids else {}

        # 客户端按 category / categories / tags 过滤
        filtered_cases = filter_test_cases(test_cases, category, categories, tags, include_untagged)
        filtered_case_ids = extract_case_ids(filtered_cases)

        # 通过 gRPC 查询 TestResult 并按 test_case_id 过滤
        result_task_ids = result_task_filter if isinstance(result_task_filter, list) else [result_task_filter]
        all_test_results = _grpc_get_test_results_by_task_ids(result_task_ids)
        test_results = filter_results_by_case_ids(all_test_results, filtered_case_ids)

        return filtered_case_ids, test_results

    def _calculate_averages(self, task, filtered_case_ids: list, test_results: list, task_id: int) -> dict:
        """计算平均值、正态分布、资源列表等统计信息（委托服务层）。

        Args:
            task: 任务对象
            filtered_case_ids: 过滤后的用例 ID 列表
            test_results: 测试结果列表
            task_id: 任务 ID

        Returns:
            dict: 统计信息字典
        """
        from report_service.application.services.report_aggregation_service import ReportAggregationService
        return ReportAggregationService.calculate_averages(task, filtered_case_ids, test_results, task_id)


def _os_path_join(*parts) -> str:
    """os.path.join 的模块级代理（保持 _format_logs_download 结构清晰）。"""
    import os
    return os.path.join(*parts)
