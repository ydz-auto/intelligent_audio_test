# -*- coding: utf-8 -*-
"""报告查询处理器 Mixin — 平均值统计 / 用例日志下载 / 报告统计分析
（从 report_handlers.py 拆分，P4-5）。

handle_get_case_averages / handle_download_case_logs 及其私有查询辅助；
INT-791 新增 handle_get_statistics / handle_get_statistics_trend /
handle_generate_statistics_report（委托 StatisticsService）。
"""
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from report_service.application.handlers._report_case_filters import (
    extract_case_ids,
    filter_results_by_case_ids,
    filter_test_cases,
    find_result_by_case_id,
)

logger = logging.getLogger(__name__)


class ReportStatsQueryMixin:
    """平均值统计 / 日志下载 / 报告统计分析（依赖 self.repository）"""

    # ==================================================================
    # 报告统计分析（INT-791：/reports/statistics* 三端点）
    # ==================================================================

    def handle_get_statistics(self, params_dict: dict) -> dict:
        """处理统计分析查询（GET /reports/statistics）。

        委托 StatisticsService，按维度聚合 report 7 表只读数据。

        Args:
            params_dict: {dimension, start_time, end_time, algorithm_type}

        Returns:
            成功：{dimension, overview, detail, chart, anomaly}
            失败：{success: False, message}
        """
        from report_service.application.services.report_aggregation.statistics_service import (
            statistics_service,
        )
        return statistics_service.get_statistics(params_dict, self.repository)

    def handle_get_statistics_trend(self, params_dict: dict) -> dict:
        """处理趋势分析查询（GET /reports/statistics/trend）。

        委托 StatisticsService，返回时间序列（time_trend/dimension_trend）。

        Args:
            params_dict: {trend_type, metric, start_time, end_time}

        Returns:
            成功：{trend_type, time_trend, dimension_trend}
            失败：{success: False, message}
        """
        from report_service.application.services.report_aggregation.statistics_service import (
            statistics_service,
        )
        return statistics_service.get_trend(params_dict, self.repository)

    def handle_generate_statistics_report(self, params_dict: dict) -> dict:
        """处理统计分析报表生成（POST /reports/statistics/report）。

        委托 StatisticsService，复用 binary 下载结构。

        Args:
            params_dict: {report_type, content, format, time_range}

        Returns:
            成功：{filename, format, content_base64, mime_type}
            失败：{success: False, message}
        """
        from report_service.application.services.report_aggregation.statistics_service import (
            statistics_service,
        )
        return statistics_service.generate_report(params_dict, self.repository)

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
        打包成 ZIP 以 base64 编码返回（INT-1056：改用共享文件清单构建器，
        缺省全量输出与 download-selected 缺省分支字节一致）。

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

    def handle_list_case_log_files(self, report_id: int, case_id: str) -> dict:
        """处理用例日志文件列表（GET .../logs/files，INT-1056）。

        与下载共用同一「文件清单构建器」；filename = 下载 zip 内 arcname，
        保证 list 与 download-selected 命名空间一致。

        Args:
            report_id: 报告 ID
            case_id: 用例 ID

        Returns:
            成功：{files: [{filename, size_bytes, updated_at}]}（空态 []）
            失败：{success: False, message, code}（404：报告不存在/无关联任务）
        """
        query_result = self._query_case_logs(report_id, case_id)
        if not isinstance(query_result, tuple):
            return query_result
        task_ids_to_search, test_result = query_result

        manifest = self._build_case_log_manifest(task_ids_to_search, test_result, case_id)
        return {
            'files': [{
                'filename': entry['filename'],
                'size_bytes': entry['size_bytes'],
                'updated_at': entry['updated_at'],
            } for entry in manifest],
        }

    def handle_download_selected_case_logs(self, report_id: int, case_id: str,
                                           filenames: list) -> dict:
        """处理按选打包下载用例日志（POST .../logs/download-selected，INT-1056）。

        与列表/全量下载共用同一文件清单；filenames 缺省或空数组 = 全部
        （与现 download_case_logs 完全一致）。

        Args:
            report_id: 报告 ID
            case_id: 用例 ID
            filenames: 按选文件名列表（缺省/空 = 全部）

        Returns:
            成功：{filename, content_base64, size}
            失败：{success: False, message, code}（400：未知名/未找到日志目录；
                  404：报告不存在/无关联任务）
        """
        import base64
        import io as _io
        import zipfile as _zipfile

        query_result = self._query_case_logs(report_id, case_id)
        if not isinstance(query_result, tuple):
            return query_result
        task_ids_to_search, test_result = query_result

        manifest = self._build_case_log_manifest(task_ids_to_search, test_result, case_id)

        selected = [str(fn) for fn in (filenames or []) if fn]
        if not selected:
            # 缺省全量：与现 download_case_logs 行为一致（仅虚拟文件不算有日志）
            if not self._manifest_has_logs(manifest):
                return {'success': False, 'message': '未找到用例日志目录'}
            entries = manifest
            zip_filename = f"case_{case_id}_logs.zip"
        else:
            by_name = {entry['filename']: entry for entry in manifest}
            unknown = [fn for fn in selected if fn not in by_name]
            if unknown:
                return {'success': False, 'message': '未知的文件名: ' + ', '.join(unknown)}
            # 保持请求顺序并去重；zip 内容与所选文件名一致
            entries = []
            seen = set()
            for fn in selected:
                if fn in seen:
                    continue
                seen.add(fn)
                entries.append(by_name[fn])
            zip_filename = f"case_{case_id}_logs_selected.zip"

        zip_buffer = _io.BytesIO()
        with _zipfile.ZipFile(zip_buffer, 'w', _zipfile.ZIP_DEFLATED) as zf:
            self._write_manifest_to_zip(zf, entries)
        zip_buffer.seek(0)
        zip_data = zip_buffer.getvalue()

        return {
            'filename': zip_filename,
            'content_base64': base64.b64encode(zip_data).decode('utf-8'),
            'size': len(zip_data),
        }

    # ---- 日志下载私有辅助 ----

    def _query_case_logs(self, report_id: int, case_id: str):
        """查询用例日志相关数据。

        Args:
            report_id: 报告 ID
            case_id: 用例 ID

        Returns:
            tuple(task_ids_to_search, test_result) 或错误 dict
        """
        from report_service.infrastructure.clients.grpc_clients import (
            _grpc_get_test_results_by_ids,
            _grpc_get_test_results_by_task_ids,
        )

        aggregate = self.repository.get_by_id(report_id)
        if aggregate is None:
            return {'success': False, 'message': '未找到测试报告', 'code': 404}

        task_id = aggregate.task_id
        if not task_id:
            return {'success': False, 'message': '该报告没有关联的任务ID', 'code': 404}

        # 通过 gRPC 查询 TaskMergeRelation / TaskCherryPickRelation（INT-408 接入挑选关系）：
        # cherry-pick 容器日志目录在源任务前缀下，结果按引用 result_id 精确解析
        task_ids_to_search = [task_id]
        cherry_result_ids = None
        try:
            from report_service.application.services.task_result_resolver import (
                resolve_cherry_pick_sources,
                resolve_merge_source_task_ids,
            )
            cherry = resolve_cherry_pick_sources(task_id)
            if cherry:
                task_ids_to_search = cherry['source_task_ids'] or [task_id]
                cherry_result_ids = cherry['result_ids']
            else:
                source_task_ids = resolve_merge_source_task_ids(task_id)
                if source_task_ids:
                    task_ids_to_search = source_task_ids
        except Exception:
            logger.debug("gRPC 查询任务合并关系失败 task_id=%s", task_id, exc_info=True)

        # 通过 gRPC 查询 TestResult（容器按引用 result_id 直查；其余按 task_id 批量查询）
        if cherry_result_ids:
            all_test_results = _grpc_get_test_results_by_ids(cherry_result_ids)
            if not all_test_results:
                all_test_results = _grpc_get_test_results_by_task_ids(task_ids_to_search)
        else:
            all_test_results = _grpc_get_test_results_by_task_ids(task_ids_to_search)
        test_result = find_result_by_case_id(all_test_results, case_id)

        return task_ids_to_search, test_result

    @staticmethod
    def _build_case_log_manifest(task_ids_to_search: list, test_result, case_id: str) -> list:
        """构建用例日志文件清单（list / download-selected / 全量下载三处共用）。

        三来源统一映射到 zip arcname 命名空间（审计 §四，关键契约）：
        - case 文件：单任务源 = case_result 桶相对 {task_id}/{case_id}/ 路径；
          多任务/挑选/合并（task_ids_to_search > 1）加 task_{task_id}/ 前缀
          （与现 arcname 规则一致，字节级对齐）；
        - 业务日志：business_logs/{rel}（load_file_bytes 相对 task 目录路径）；
        - 虚拟文件：adjusted_reference_params.json（full_data 判定，即时算 size）。

        Returns:
            list[dict]：{filename, size_bytes, updated_at, source,
                         storage_key|abs_path|content}
        """
        from shared.infrastructure.storage import storage
        from shared.logging import BusinessLogReader
        from shared.utils.result_data_store import load_full_result_data

        manifest = []
        # INT-81：业务日志按结果的被测设备收敛范围（结果无设备信息时取任务全量）
        device_id = None
        if test_result:
            device_id = (test_result.get('device_id') if isinstance(test_result, dict)
                         else getattr(test_result, 'device_id', None))

        # 1) case 文件（case_result 桶 {task_id}/{case_id}/）
        for search_task_id in task_ids_to_search:
            oss_prefix = f'{search_task_id}/{case_id}/'
            try:
                objects = storage.list_objects_with_meta('case_result', prefix=oss_prefix)
            except Exception:
                objects = []
            for obj in objects or []:
                oss_key = obj.get('key')
                if not oss_key:
                    continue
                arcname = oss_key[len(oss_prefix):]  # 去掉前缀
                if len(task_ids_to_search) > 1:
                    arcname = _os_path_join(f"task_{search_task_id}", arcname)
                manifest.append({
                    'filename': arcname,
                    'size_bytes': obj.get('sizeBytes', 0),
                    'updated_at': ReportStatsQueryMixin._format_iso_utc(obj.get('lastModified')),
                    'source': 'case',
                    'storage_key': f'case_result/{oss_key}',
                })

        # 2) 业务日志（business/{task}/...，按被测设备收敛）
        reader = BusinessLogReader()
        for task_id in task_ids_to_search:
            try:
                files = reader.list_log_files(task_id=task_id, device_id=device_id)
            except Exception:
                logger.debug("收集业务日志文件失败 task_id=%s", task_id, exc_info=True)
                continue
            task_dir = os.path.join(reader._root_dir, reader._path_builder.build_task_dir(task_id))
            for abs_path in files:
                try:
                    st = os.stat(abs_path)
                except OSError:
                    continue
                rel = os.path.relpath(abs_path, task_dir).replace(os.sep, '/')
                manifest.append({
                    'filename': f"business_logs/{rel}",
                    'size_bytes': st.st_size,
                    'updated_at': ReportStatsQueryMixin._format_iso_utc(
                        datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)),
                    'source': 'business',
                    'abs_path': abs_path,
                })

        # 3) 虚拟文件 adjusted_reference_params.json（full_data 判定保证字节级一致）
        full_data = {}
        if test_result:
            tr_result_data = (test_result.get('result_data') if isinstance(test_result, dict)
                              else getattr(test_result, 'result_data', None))
            tr_result_data_path = (test_result.get('result_data_path') if isinstance(test_result, dict)
                                   else getattr(test_result, 'result_data_path', None))
            full_data = load_full_result_data(tr_result_data, tr_result_data_path)
        if test_result and full_data and 'adjusted_reference_params' in full_data:
            adjusted_params = full_data['adjusted_reference_params']
            if adjusted_params:
                params_json = json.dumps(adjusted_params, ensure_ascii=False, indent=2)
                manifest.append({
                    'filename': 'adjusted_reference_params.json',
                    'size_bytes': len(params_json.encode('utf-8')),
                    'updated_at': None,
                    'source': 'virtual',
                    'content': params_json,
                })

        return manifest

    @staticmethod
    def _manifest_has_logs(manifest: list) -> bool:
        """判定是否「有日志」：与现 download_case_logs found_any 语义一致
        （仅 case 文件或业务日志；虚拟文件单独存在不算）。"""
        return any(entry.get('source') in ('case', 'business') for entry in manifest)

    @staticmethod
    def _write_manifest_to_zip(zf, manifest: list) -> None:
        """按清单顺序把文件写入 ZIP（case → business → virtual）。

        读取失败的文件跳过（与现 download_case_logs 逐文件跳过语义一致）。
        """
        for entry in manifest:
            content = ReportStatsQueryMixin._load_log_file_bytes(entry)
            if content is None:
                continue
            zf.writestr(entry['filename'], content)

    @staticmethod
    def _load_log_file_bytes(entry: dict) -> Optional[bytes]:
        """按清单条目 source 取字节内容；读取失败返回 None。"""
        source = entry.get('source')
        if source == 'case':
            from shared.infrastructure.storage import storage
            try:
                return storage.load_bytes(entry['storage_key'])
            except Exception:
                return None
        if source == 'business':
            try:
                with open(entry['abs_path'], 'rb') as handle:
                    return handle.read()
            except OSError:
                return None
        if source == 'virtual':
            return entry['content'].encode('utf-8')
        return None

    @staticmethod
    def _format_logs_download(task_ids_to_search: list, test_result, report_id: int, case_id: str) -> dict:
        """根据查询到的日志数据构建 ZIP 并以 base64 编码返回。

        INT-1056：改用共享文件清单构建器；缺省全量输出与
        download-selected 缺省分支（空 filenames）字节一致。

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
        import zipfile as _zipfile

        manifest = ReportStatsQueryMixin._build_case_log_manifest(
            task_ids_to_search, test_result, case_id)

        if not ReportStatsQueryMixin._manifest_has_logs(manifest):
            return {'success': False, 'message': '未找到用例日志目录'}

        zip_filename = f"case_{case_id}_logs.zip"
        zip_buffer = _io.BytesIO()
        with _zipfile.ZipFile(zip_buffer, 'w', _zipfile.ZIP_DEFLATED) as zf:
            ReportStatsQueryMixin._write_manifest_to_zip(zf, manifest)
        zip_buffer.seek(0)
        zip_data = zip_buffer.getvalue()

        return {
            'filename': zip_filename,
            'content_base64': base64.b64encode(zip_data).decode('utf-8'),
            'size': len(zip_data),
        }

    @staticmethod
    def _format_iso_utc(value) -> Optional[str]:
        """datetime → ISO8601 UTC（'Z' 后缀；对齐 log_query_service._to_iso_utc）。

        虚拟文件无时间 → None 原样返回；naive datetime 按 UTC 处理。
        """
        if value is None or isinstance(value, str):
            return value
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)
        return value.isoformat().replace('+00:00', 'Z')

    # ---- 平均值统计私有辅助 ----

    def _query_cases_for_averages(self, task_id: int, category, categories, tags, include_untagged):
        """查询用例和结果（含任务解析、合并/挑选关系处理）。

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

        # 差异#2 收尾：合并容器任务由 TaskMergeRelation(merged_task_id) 存在性判定（task.type 已废弃）
        # INT-408：cherry-pick 容器任务 TaskCase 取自容器自身（下单已继承），
        # 结果按引用关系直查 result_id（容器自身无 test_results 行）
        task_id_filter = task_id
        result_task_filter = task_id
        cherry_result_ids = None
        try:
            from report_service.application.services.task_result_resolver import (
                resolve_cherry_pick_sources,
                resolve_merge_source_task_ids,
            )
            cherry = resolve_cherry_pick_sources(task_id)
            if cherry:
                cherry_result_ids = cherry['result_ids']
            else:
                source_task_ids = resolve_merge_source_task_ids(task_id)
                if source_task_ids:
                    task_id_filter = source_task_ids
                    result_task_filter = source_task_ids
        except Exception:
            logger.debug("gRPC 查询任务合并关系失败 task_id=%s", task_id, exc_info=True)

        filtered_case_ids, test_results = self._query_test_cases_and_results(
            task_id_filter, result_task_filter,
            category, categories, tags, include_untagged,
            cherry_result_ids=cherry_result_ids,
        )
        return task, filtered_case_ids, test_results

    def _query_test_cases_and_results(self, task_id_filter, result_task_filter,
                                      category, categories, tags, include_untagged,
                                      cherry_result_ids=None):
        """查询测试用例和结果，返回 (filtered_case_ids, test_results)。

        Args:
            task_id_filter: 任务 ID 过滤（int 或 list）
            result_task_filter: 结果任务过滤（int 或 list）
            category: 单个分类
            categories: 分类列表
            tags: 标签列表
            include_untagged: 是否包含未标记用例
            cherry_result_ids: cherry-pick 容器引用的源结果 id 列表
                （INT-408；非空时结果按 result_id 直查，忽略 result_task_filter）

        Returns:
            tuple(filtered_case_ids, test_results)
        """
        from report_service.application.services.report_query_builder import (
            _grpc_get_task_case_ids,
        )
        from report_service.infrastructure.clients.grpc_clients import (
            _grpc_list_testcases_by_ids,
            _grpc_get_test_results_by_ids,
            _grpc_get_test_results_by_task_ids,
        )

        # 通过 gRPC 查询 TaskCase（获取 task 关联的 test_case_id 列表）
        # 注意：TaskCase 载荷为 dict（含 test_case_id 等字段），须提取 id 再查
        # TestCase（对齐 pre-DDD 版本 [tc.test_case_id for tc in task_cases]
        # 与 report_data_builder_resource_mixin 同款口径；迁移回归曾直接透传 dict）
        def _tc_ids(tc_rows):
            out = []
            for tc in tc_rows or []:
                cid = tc.get('test_case_id') if isinstance(tc, dict) else getattr(tc, 'test_case_id', None)
                if cid is not None:
                    out.append(cid)
            return out

        if isinstance(task_id_filter, list):
            all_tc_ids = set()
            for tid in task_id_filter:
                all_tc_ids.update(_tc_ids(_grpc_get_task_case_ids(tid)))
            test_case_ids = list(all_tc_ids)
        else:
            test_case_ids = _tc_ids(_grpc_get_task_case_ids(task_id_filter))

        # 通过 gRPC 批量查询 TestCase
        test_cases = _grpc_list_testcases_by_ids(test_case_ids) if test_case_ids else {}

        # 客户端按 category / categories / tags 过滤
        filtered_cases = filter_test_cases(test_cases, category, categories, tags, include_untagged)
        filtered_case_ids = extract_case_ids(filtered_cases)

        # 通过 gRPC 查询 TestResult 并按 test_case_id 过滤
        if cherry_result_ids:
            all_test_results = _grpc_get_test_results_by_ids(cherry_result_ids)
        else:
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
