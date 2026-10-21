# -*- coding: utf-8 -*-
"""报告查询处理器 Mixin — 平均值统计 / 用例日志下载 / 报告统计分析
（从 report_handlers.py 拆分，P4-5）。

handle_get_case_averages / handle_download_case_logs 及其私有查询辅助；
INT-791 新增 handle_get_statistics / handle_get_statistics_trend /
handle_generate_statistics_report（委托 StatisticsService）。
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

        支持 task_id（任务筛选）与 report_id（对比/二次对比报告筛选，INT-1059 对齐
        0c6b2028a：从对比矩阵/摘要解析源任务集合，与 taskId 走同一聚合工具）。

        Args:
            params_dict: 参数字典，含 task_id/report_id/category/tags/categories/include_untagged

        Returns:
            dict: 平均值统计响应
        """
        from report_service.application.services.report_utils import ReportUtils

        task_id = params_dict.get('task_id')
        report_id = params_dict.get('report_id')
        category = params_dict.get('category')
        tags = params_dict.get('tags') or []
        categories = params_dict.get('categories') or []
        include_untagged = params_dict.get('include_untagged') or False

        if not task_id and not report_id:
            return {'success': False, 'message': '缺少必要参数: task_id 或 report_id'}

        query_result = self._query_cases_for_averages(
            task_id, category, categories, tags, include_untagged, report_id
        )
        if not isinstance(query_result, tuple):
            return query_result
        task, task_id_filter, filtered_case_ids, test_results, tasks_map, use_time_prefix = query_result

        stats = self._calculate_averages(
            task, filtered_case_ids, test_results, task_id_filter,
            tasks_map=tasks_map, use_time_prefix=use_time_prefix,
        )

        return {
            "total_cases": len(stats['filtered_case_ids']),
            "total_results": len(stats['test_results']),
            "overall_averages": stats['overall_averages'],
            "overall_averages_map": stats['averages_map'],
            "metric_data": ReportUtils.flatten_metric_data(stats['metric_data'], {}, stats['metric_name_to_id']),
            "tag_metric_data": ReportUtils.flatten_tag_metric_data(stats['tag_metric_data'], {}, stats['metric_name_to_id']),
            "raw_data": ReportUtils.flatten_raw_data(stats['raw_data']),
            "normal_distribution": stats['normal_distribution_data'],
            "resources": stats['resources'],
            "resource_headers": stats['resource_headers'],
            "filters": {
                "category": category,
                "tags": tags
            }
        }

    def handle_download_case_logs(self, report_id: int, case_id: str, files=None) -> dict:
        """处理下载用例日志。

        查询报告关联任务的合并关系、TestResult，从存储列出 case 日志文件，
        打包成 ZIP 以 base64 编码返回。

        Args:
            report_id: 报告 ID
            case_id: 用例 ID
            files: 可选，逻辑文件名筛选（INT-1062，与列表端点 name / ZIP arcname
                同一套逻辑名）；None 或缺省 = 整包（向后兼容）

        Returns:
            dict: {filename, content_base64, size} 或 {success: False, message}
        """
        query_result = self._query_case_logs(report_id, case_id)
        if not isinstance(query_result, tuple):
            return query_result
        task_ids_to_search, test_result = query_result

        return self._format_logs_download(
            task_ids_to_search, test_result, report_id, case_id, files)

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
            return {'success': False, 'message': '未找到测试报告'}

        task_id = aggregate.task_id
        if not task_id:
            return {'success': False, 'message': '该报告没有关联的任务ID'}

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
    def _format_logs_download(task_ids_to_search: list, test_result, report_id: int,
                              case_id: str, files=None) -> dict:
        """根据查询到的日志数据构建 ZIP 并上抛 OSS 临时桶，返回预签名 URL。

        INT-1062：files 为逻辑文件名筛选（同一套逻辑名 = 列表 name = ZIP arcname）；
        缺省整包；按选时 ZIP 仅含所选文件，任一所选文件未命中 → 404。

        INT-1116（传输层改造）：ZIP 不再整包 base64 过 gRPC——先写本地临时文件，
        再上抛 OSS temp 类别（对象生命周期由 OSS 策略 ~1h 自动清理），返回预签名
        URL（3600s）；OSS 不可用 / get_url 返回 None 时降级回退 base64 字节流
        （与 INT-1062 现状一致，属本地降级模式，受 gRPC 4MB 消息上限约束）。

        Args:
            task_ids_to_search: 需搜索的任务 ID 列表
            test_result: 测试结果对象
            report_id: 报告 ID
            case_id: 用例 ID
            files: 可选，逻辑文件名列表（None = 整包）

        Returns:
            dict: {filename, download_url, size, mime_type, mode: 'presigned'}
                或 {filename, content_base64, size, mime_type, mode: 'fallback'}
                或 {success: False, message}
        """
        import base64
        import json as _json
        import os as _os
        import tempfile as _tempfile
        import uuid as _uuid
        import zipfile as _zipfile
        from shared.infrastructure.storage import storage
        from shared.utils.result_data_store import load_full_result_data

        zip_filename = f"case_{case_id}_logs.zip"
        selected = set(files) if files else None
        written = set()

        # INT-81：用例日志下载含业务日志文件（logs/business/{task}/{device}/...），
        # 按结果的被测设备收敛范围（结果无设备信息时取任务全量）
        device_id = None
        if test_result:
            device_id = (test_result.get('device_id') if isinstance(test_result, dict)
                         else getattr(test_result, 'device_id', None))

        tmp_path = None
        try:
            tmp_fd, tmp_path = _tempfile.mkstemp(suffix='.zip', prefix='case_logs_')
            _os.close(tmp_fd)
            found_any = False
            with _zipfile.ZipFile(tmp_path, 'w', _zipfile.ZIP_DEFLATED) as zf:
                found_any = ReportStatsQueryMixin._write_case_log_files(
                    zf, task_ids_to_search, case_id, found_any, selected, written)

                if ReportStatsQueryMixin._write_business_log_files(
                        zf, task_ids_to_search, device_id, selected, written):
                    found_any = True

                full_data = {}
                if test_result:
                    tr_result_data = test_result.get('result_data') if isinstance(test_result, dict) else getattr(test_result, 'result_data', None)
                    tr_result_data_path = test_result.get('result_data_path') if isinstance(test_result, dict) else getattr(test_result, 'result_data_path', None)
                    full_data = load_full_result_data(tr_result_data, tr_result_data_path)
                if test_result and full_data and 'adjusted_reference_params' in full_data:
                    adjusted_params = full_data['adjusted_reference_params']
                    if adjusted_params:
                        params_json = _json.dumps(adjusted_params, ensure_ascii=False, indent=2)
                        if selected is None or 'adjusted_reference_params.json' in selected:
                            zf.writestr("adjusted_reference_params.json", params_json)
                            written.add("adjusted_reference_params.json")
                            found_any = True

            # INT-1062：按选打包时，任一所选文件未命中 → 404（清单不可用语义）
            if selected is not None:
                missing = sorted(selected - written)
                if missing:
                    return {'success': False,
                            'message': f'以下日志文件不存在: {", ".join(missing)}',
                            'code': 404}

            if not found_any:
                return {'success': False, 'message': '未找到用例日志目录'}

            total_size = _os.path.getsize(tmp_path)

            # INT-1116：上抛 OSS 临时桶（temp 类别，TTL 由 OSS 生命周期策略清理）
            key = f"report_logs/{report_id}/{case_id}/{_uuid.uuid4().hex}.zip"
            uploaded_path = storage.save_file(tmp_path, 'temp', key)
            url = storage.get_url(uploaded_path, expires=3600)
            if url:
                return {
                    'filename': zip_filename,
                    'download_url': url,
                    'size': total_size,
                    'mime_type': 'application/zip',
                    'mode': 'presigned',
                }

            # 本地降级：读取临时文件回退 base64 字节流（网关字节流回退链路）
            with open(tmp_path, 'rb') as fh:
                zip_data = fh.read()
            return {
                'filename': zip_filename,
                'content_base64': base64.b64encode(zip_data).decode('utf-8'),
                'size': total_size,
                'mime_type': 'application/zip',
                'mode': 'fallback',
            }
        finally:
            if tmp_path and _os.path.exists(tmp_path):
                try:
                    _os.remove(tmp_path)
                except OSError:
                    logger.debug("清理日志 ZIP 临时文件失败: %s", tmp_path, exc_info=True)

    @staticmethod
    def _write_business_log_files(zf, task_ids_to_search: list, device_id,
                                  files=None, written=None) -> bool:
        """将任务的业务日志文件（INT-81 路径体系）写入 ZIP，返回是否写入文件。

        INT-1062：files 为逻辑文件名筛选（business_logs/{rel}），缺省整包；
        written 非空时记录实际写入的逻辑名（供按选打包缺文件 404 判定）。
        """
        from shared.logging import BusinessLogReader

        selected = set(files) if files else None
        reader = BusinessLogReader()
        wrote_any = False
        for task_id in task_ids_to_search:
            try:
                files_ = reader.load_file_bytes(task_id=task_id, device_id=device_id)
            except Exception:
                logger.debug("收集业务日志文件失败 task_id=%s", task_id, exc_info=True)
                continue
            for rel_path, content in files_:
                arcname = f"business_logs/{rel_path}"
                if selected is not None and arcname not in selected:
                    continue
                zf.writestr(arcname, content)
                if written is not None:
                    written.add(arcname)
                wrote_any = True
        return wrote_any

    @staticmethod
    def _write_case_log_files(zf, task_ids_to_search: list, case_id: str,
                              found_any: bool, files=None, written=None) -> bool:
        """遍历各任务从存储收集 case 日志文件写入 ZIP。返回是否有文件被写入。

        INT-1062：files 为逻辑文件名筛选（{task_id}/{case_id}/ 相对路径，
        multi-source 带 task_{id}/ 前缀，与列表端点同一套逻辑名），缺省整包；
        written 非空时记录实际写入的逻辑名。
        """
        from shared.infrastructure.storage import storage

        selected = set(files) if files else None
        for src in ReportStatsQueryMixin._iter_case_log_sources(task_ids_to_search, case_id):
            if selected is not None and src['arcname'] not in selected:
                continue
            # 下载文件内容
            try:
                file_data = storage.load_bytes(f'case_result/{src["oss_key"]}')
            except Exception:
                continue
            zf.writestr(src['arcname'], file_data)
            if written is not None:
                written.add(src['arcname'])
            found_any = True
        return found_any

    @staticmethod
    def _iter_case_log_sources(task_ids_to_search: list, case_id: str):
        """枚举 case 日志存储条目（INT-1062：列表/打包共用同一套逻辑名）。

        yield {arcname, oss_key, size, last_modified}：
            arcname（ZIP 内逻辑名）= {task_id}/{case_id}/ 下相对路径；
            multi-source（task_ids_to_search > 1）时带 task_{id}/ 前缀
            （对齐 _write_case_log_files 既有口径）。
        """
        from shared.infrastructure.storage import storage

        multi = len(task_ids_to_search) > 1
        for search_task_id in task_ids_to_search:
            # OSS: 列出 case-result bucket 下 {task_id}/{case_id}/ 的所有文件
            oss_prefix = f'{search_task_id}/{case_id}/'
            try:
                metas = storage.list_objects_with_meta('case_result', prefix=oss_prefix)
            except Exception:
                continue
            for meta in metas:
                oss_key = meta.get('key', '')
                if not oss_key.startswith(oss_prefix):
                    continue
                arcname = oss_key[len(oss_prefix):]  # 去掉前缀
                if multi:
                    arcname = _os_path_join(f"task_{search_task_id}", arcname)
                yield {
                    'arcname': arcname,
                    'oss_key': oss_key,
                    'size': int(meta.get('sizeBytes', 0) or 0),
                    'last_modified': meta.get('lastModified'),
                }

    # ---- 日志文件列表（INT-1062）----

    def handle_list_case_logs(self, report_id: int, case_id: str) -> dict:
        """查询用例日志文件列表（INT-1062，GET /reports/{id}/cases/{cid}/logs）。

        与下载打包共用同一套逻辑名（列表 name = ZIP arcname = files= 匹配值），
        枚举 case 日志 / business 日志 / 根级 adjusted_reference_params.json。

        Args:
            report_id: 报告 ID
            case_id: 用例 ID

        Returns:
            {items: [{name, size, updated_at?}]} 或 {success: False, message}
        """
        query_result = self._query_case_logs(report_id, case_id)
        if not isinstance(query_result, tuple):
            return query_result
        task_ids_to_search, test_result = query_result

        items = ReportStatsQueryMixin._enumerate_log_entries(
            task_ids_to_search, test_result, report_id, case_id)
        return {'items': items}

    @staticmethod
    def _enumerate_log_entries(task_ids_to_search: list, test_result,
                               report_id: int, case_id: str) -> list:
        """枚举用例日志逻辑文件列表（INT-1062）。

        逻辑名与 ZIP arcname 同一套：case 日志（{task_id}/{case_id}/ 相对路径，
        multi-source 带 task_{id}/ 前缀）、business 日志（business_logs/{rel}）、
        根级 adjusted_reference_params.json。business 日志无 mtime 时省略
        updated_at（字段可选，不为无 mtime 数据补造时间）。

        Returns:
            [{'name': str, 'size': int, 'updated_at': str|None, 'download_url': str|None}]
            download_url（INT-1116）仅对 OSS 内 case 文件给出预签名直链（3600s）；
            business 日志 / 虚拟文件 / 本地降级不给直链（网关回退下载 URL）。
        """
        import json as _json
        from datetime import datetime
        from shared.infrastructure.storage import storage
        from shared.logging import BusinessLogReader
        from shared.utils.result_data_store import load_full_result_data

        items = []

        # 1. case 日志（OSS case_result bucket）
        for src in ReportStatsQueryMixin._iter_case_log_sources(task_ids_to_search, case_id):
            item = {'name': src['arcname'], 'size': int(src.get('size', 0) or 0)}
            last_mod = src.get('last_modified')
            if last_mod is not None:
                item['updated_at'] = (last_mod.isoformat() if isinstance(last_mod, datetime)
                                      else str(last_mod))
            # INT-1116：OSS 内 case 文件给预签名直链；get_url=None（本地降级）由
            # 网关补回退下载 URL，此处不落 download_url
            url = storage.get_url(storage.build_path('case_result', src['oss_key']),
                                  expires=3600)
            if url:
                item['download_url'] = url
            items.append(item)

        # 2. business 日志（business_logs/{rel}）
        reader = BusinessLogReader()
        device_id = None
        if test_result:
            device_id = (test_result.get('device_id') if isinstance(test_result, dict)
                         else getattr(test_result, 'device_id', None))
        for task_id in task_ids_to_search:
            try:
                log_metas = reader.list_log_files_with_meta(
                    task_id=task_id, device_id=device_id)
            except Exception:
                logger.debug("枚举业务日志文件失败 task_id=%s", task_id, exc_info=True)
                continue
            for meta in log_metas:
                item = {'name': f"business_logs/{meta['rel']}", 'size': int(meta['size'] or 0)}
                mtime = meta.get('mtime')
                if mtime is not None:
                    item['updated_at'] = mtime.isoformat()
                items.append(item)

        # 3. 根级 adjusted_reference_params.json
        if test_result:
            tr_result_data = (test_result.get('result_data') if isinstance(test_result, dict)
                              else getattr(test_result, 'result_data', None))
            tr_result_data_path = (test_result.get('result_data_path') if isinstance(test_result, dict)
                                   else getattr(test_result, 'result_data_path', None))
            full_data = load_full_result_data(tr_result_data, tr_result_data_path)
            if full_data and full_data.get('adjusted_reference_params'):
                params_json = _json.dumps(full_data['adjusted_reference_params'],
                                          ensure_ascii=False, indent=2)
                items.append({
                    'name': 'adjusted_reference_params.json',
                    'size': len(params_json.encode('utf-8')),
                })

        return items

    # ---- 平均值统计私有辅助 ----

    def _query_cases_for_averages(self, task_id, category, categories, tags, include_untagged, report_id=None):
        """查询用例和结果（含任务解析、合并/挑选关系处理）。

        Args:
            task_id: 任务 ID（int；reportId 场景传 None）
            category: 单个分类
            categories: 分类列表
            tags: 标签列表
            include_untagged: 是否包含未标记用例
            report_id: 对比/二次对比报告 ID（INT-1059 对齐 0c6b2028a：经对比矩阵/摘要
                解析源任务集合，无 task_id 时与 taskId 走同一聚合工具）

        Returns:
            tuple(task, task_id_filter, filtered_case_ids, test_results,
                  tasks_map, use_time_prefix) 或错误 dict
            - tasks_map: {task_id: task}（对比报告为源任务集合，用于按源任务聚合资源 key）
            - use_time_prefix: 对比/二次对比报告为 True（资源 key 带 t{task}-{time} 前缀，
              与对比报告摘要列一致）；任务报告为 False（无前缀，与任务报告摘要列一致）
        """
        from report_service.infrastructure.clients.grpc_clients import _grpc_get_tasks_by_ids

        # 对比/二次对比报告：report_id 解析源任务集合，源任务结果直接参与聚合
        if report_id and not task_id:
            _aggregate = self.repository.get_by_id(report_id)
            if _aggregate is None:
                return {'success': False, 'message': '未找到指定报告'}
            # 报告主表含 task_id → 普通任务报告（reportId 等价于 taskId 路径，资源 key 无前缀）；
            # 无 task_id → 对比/二次对比报告（按源任务聚合，资源 key 带 t{task}-{time} 前缀）
            is_task_report = bool(getattr(_aggregate, 'task_id', None))
            source_task_ids = self._resolve_report_source_task_ids(report_id)
            if source_task_ids is None:
                return {'success': False, 'message': '未找到指定报告'}
            if not source_task_ids:
                return {'success': False, 'message': '对比报告未关联任何任务'}
            _tasks = _grpc_get_tasks_by_ids(source_task_ids)
            task = _tasks[0] if _tasks else None
            if not task:
                return {'success': False, 'message': '未找到指定任务'}
            task_id_filter = source_task_ids
            result_task_filter = source_task_ids
            cherry_result_ids = None
            tasks_map = {}
            for _t in _tasks:
                _t_id = _t.get('id') if isinstance(_t, dict) else getattr(_t, 'id', None)
                if _t_id is not None:
                    tasks_map[_t_id] = _t
            use_time_prefix = not is_task_report
        else:
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

            # 任务报告：资源 key 无时间前缀（与任务报告摘要列一致，b47cae340 口径）
            tasks_map = {}
            use_time_prefix = False

        filtered_case_ids, test_results = self._query_test_cases_and_results(
            task_id_filter, result_task_filter,
            category, categories, tags, include_untagged,
            cherry_result_ids=cherry_result_ids,
        )
        return task, task_id_filter, filtered_case_ids, test_results, tasks_map, use_time_prefix

    def _resolve_report_source_task_ids(self, report_id: int):
        """解析对比/二次对比报告的源任务 ID 集合（reportId 筛选）。

        优先级：报告主表 task_id（普通任务报告）→ comparison matrix.task_ids
        → summary metadata.task_ids（兜底）。

        Returns:
            list[int] 源任务 ID；None 表示报告不存在/不可见；[] 表示报告未关联任务。
        """
        aggregate = self.repository.get_by_id(report_id)
        if aggregate is None:
            return None
        if getattr(aggregate, 'task_id', None):
            return [aggregate.task_id]
        try:
            comparison = self.repository.load_comparison(report_id)
            if comparison is not None:
                comparison_data = getattr(comparison, 'comparison_data', None) or {}
                if isinstance(comparison_data, dict):
                    task_ids = comparison_data.get('task_ids')
                    if task_ids:
                        return list(task_ids)
        except Exception:
            logger.debug("加载对比矩阵失败 report_id=%s", report_id, exc_info=True)
        try:
            summaries = self.repository.load_summaries(report_id)
            for s in summaries:
                metadata = getattr(s, 'metadata', None) or {}
                if isinstance(metadata, dict) and metadata.get('task_ids'):
                    return list(metadata['task_ids'])
        except Exception:
            logger.debug("加载摘要 task_ids 失败 report_id=%s", report_id, exc_info=True)
        return []

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

    def _calculate_averages(self, task, filtered_case_ids: list, test_results: list, task_id: int,
                            tasks_map: dict = None, use_time_prefix: bool = False) -> dict:
        """计算平均值、正态分布、资源列表等统计信息（委托服务层）。

        Args:
            task: 任务对象
            filtered_case_ids: 过滤后的用例 ID 列表
            test_results: 测试结果列表
            task_id: 任务 ID
            tasks_map: {task_id: task}（对比报告为源任务集合，INT-1059 返工：按源任务聚合资源 key）
            use_time_prefix: 对比/二次对比报告为 True（资源 key 带 t{task}-{time} 前缀）

        Returns:
            dict: 统计信息字典
        """
        from report_service.application.services.report_aggregation_service import ReportAggregationService
        return ReportAggregationService.calculate_averages(
            task, filtered_case_ids, test_results, task_id,
            tasks_map=tasks_map, use_time_prefix=use_time_prefix,
        )


def _os_path_join(*parts) -> str:
    """模块级路径拼接代理（保持 _format_logs_download 结构清晰）。

    INT-1062：统一返回 '/' 分隔的逻辑名——ZIP 内 arcname 经 zipfile 归一为 '/'
    （Windows os.path.join 产出 '\\' 会使列表 name 与 ZIP namelist 不一致），
    列表 name = ZIP arcname = files= 匹配值三处必须同一套逻辑名。
    """
    return '/'.join(str(p).replace('\\', '/').strip('/') for p in parts if p)
