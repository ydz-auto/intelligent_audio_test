# -*- coding: utf-8 -*-
"""TaskDataService servicer — 跨服务数据查询接口

P1.5c 新增。供 evaluation_service / api_test_service / e2e_test_service 跨服务读 task_service 数据。
替代这些服务直接 `from shared.models.models import Task, TaskCase, TestResult` 的跨域 ORM 引用。

DDD 分层：本 servicer 仅做 protocol 适配，所有 DB 访问通过 repository 完成，
不直接 import PO models 或 get_db_session。

接口清单（详见 task_service.proto 的 TaskDataService）：
- GetTestResultById    按 ID 读单个 TestResult
- GetTaskCaseByIds     批量读 TaskCase
- GetTaskById          读 Task 详情
- GetTaskDevices       读任务关联设备
- GetTaskApis          读任务关联 API
- SubmitResult         写入 TestResult
- UpdateTaskCaseStatus 更新 TaskCase 状态
- GetTaskMergeRelations 查询 TaskMergeRelation（报告对比）
- ListLogs             查询 Log 列表（日志查询）
- ListTestCaseGroups   查询 TestCaseGroup 列表（分组管理）
- GetTaskStats         聚合统计 Task（count/group_by，供 stats_cache / home_service 用）
- GetTestCaseStats     聚合统计 TestCase（count/group_by，供 stats_cache / home_service 用）
"""
import logging

from shared.proto import task_service_pb2 as task_pb
from shared.proto import task_service_pb2_grpc as task_grpc
from shared.utils.grpc_json import loads as _loads, dumps as _dumps

from task_service.infrastructure.persistence.task_repository import task_repository
from task_service.infrastructure.persistence.testcase_repository import testcase_repository
from task_service.infrastructure.persistence.log_repository import log_repository
from task_service.infrastructure.persistence.test_result_repository import test_result_repository
from task_service.infrastructure.persistence.task_merge_repository import task_merge_relation_repository

logger = logging.getLogger(__name__)


class TaskDataServiceServicer(task_grpc.TaskDataServiceServicer):
    """task_service 数据查询 servicer — 跨服务数据访问入口

    DDD 分层：仅做 protocol 适配，委托 repository 完成数据访问。
    """

    @staticmethod
    def _resp(success: bool, message: str = '', data=None) -> task_pb.TaskDataResponse:
        return task_pb.TaskDataResponse(
            success=success,
            message=message,
            data=_dumps(data) if data is not None else "",
        )

    # ========== 读操作 ==========

    def GetTestResultById(self, request, context=None):
        """按 ID 读取单个 TestResult"""
        try:
            result = test_result_repository.get_by_id(request.result_id)
            if result is None:
                return self._resp(False, f'TestResult {request.result_id} not found')
            return self._resp(True, 'ok', result)
        except Exception as e:
            logger.exception('GetTestResultById failed')
            return self._resp(False, str(e))

    def GetTaskCaseByIds(self, request, context=None):
        """按 task_id + case_ids 批量读取 TaskCase。
        case_ids 为空时返回该 task 下所有 TaskCase。"""
        try:
            case_ids = list(request.case_ids) if request.case_ids else None
            items = task_repository.get_task_case_dicts(request.task_id, case_ids)
            return self._resp(True, 'ok', items)
        except Exception as e:
            logger.exception('GetTaskCaseByIds failed')
            return self._resp(False, str(e))

    def GetTaskById(self, request, context=None):
        """按 task_id 读取 Task 详情"""
        try:
            task = task_repository.get_task_dict_by_id(request.task_id)
            if task is None:
                return self._resp(False, f'Task {request.task_id} not found')
            return self._resp(True, 'ok', task)
        except Exception as e:
            logger.exception('GetTaskById failed')
            return self._resp(False, str(e))

    def GetTaskDevices(self, request, context=None):
        """按 task_id 读取关联设备"""
        try:
            items = task_repository.get_task_device_dicts(request.task_id)
            return self._resp(True, 'ok', items)
        except Exception as e:
            logger.exception('GetTaskDevices failed')
            return self._resp(False, str(e))

    def GetTaskApis(self, request, context=None):
        """按 task_id 读取关联 API"""
        try:
            items = task_repository.get_task_api_dicts(request.task_id)
            return self._resp(True, 'ok', items)
        except Exception as e:
            logger.exception('GetTaskApis failed')
            return self._resp(False, str(e))

    # ========== 写操作 ==========

    def SubmitResult(self, request, context=None):
        """写入测试结果。
        result_data 是 JSON，包含 test_case_id / device_id / api_id / algorithm_type /
        execution_status / response_time / algorithm_result / execution_steps 等字段。
        """
        try:
            data = _loads(request.result_data, {})
            result_id = test_result_repository.submit(request.task_id, data)
            return self._resp(True, 'ok', {'result_id': result_id})
        except Exception as e:
            logger.exception('SubmitResult failed')
            return self._resp(False, str(e))

    def UpdateTaskCaseStatus(self, request, context=None):
        """更新 TaskCase 状态（evaluation_service 评估完成后调用）"""
        try:
            updated = task_repository.update_task_case_status(
                request.task_id, request.case_id,
                status=request.status,
                execution_status=request.execution_status,
                evaluation_status=request.evaluation_status,
                error_message=request.error_message,
            )
            return self._resp(True, 'ok', {'updated': updated})
        except Exception as e:
            logger.exception('UpdateTaskCaseStatus failed')
            return self._resp(False, str(e))

    def UpdateTestResultAlgorithmResult(self, request, context=None):
        """更新 TestResult 的 algorithm_result（evaluation_service 多轮聚合后调用）"""
        try:
            data = _loads(request.algorithm_result, {})
            ok = test_result_repository.update_algorithm_result(request.result_id, data)
            if not ok:
                return self._resp(False, f'TestResult {request.result_id} not found')
            return self._resp(True, 'ok', {'result_id': request.result_id})
        except Exception as e:
            logger.exception('UpdateTestResultAlgorithmResult failed')
            return self._resp(False, str(e))

    def UpdateTestResultData(self, request, context=None):
        """更新 TestResult 的 result_data 和 result_data_path（evaluation_service 预提取 algorithm_results 快照时调用）"""
        try:
            data = _loads(request.result_data, None)
            ok = test_result_repository.update_result_data(
                request.result_id, data, request.result_data_path or None
            )
            if not ok:
                return self._resp(False, f'TestResult {request.result_id} not found')
            return self._resp(True, 'ok', {'result_id': request.result_id})
        except Exception as e:
            logger.exception('UpdateTestResultData failed')
            return self._resp(False, str(e))

    def GetTestResultsByTaskAndCase(self, request, context=None):
        """按 task_id + test_case_id 批量读取 TestResult"""
        try:
            items = test_result_repository.get_by_task_and_case(
                request.task_id, request.test_case_id
            )
            return self._resp(True, 'ok', items)
        except Exception as e:
            logger.exception('GetTestResultsByTaskAndCase failed')
            return self._resp(False, str(e))

    def UpdateTestResultStatus(self, request, context=None):
        """更新 TestResult 的 execution_status"""
        try:
            ok = test_result_repository.update_status(request.result_id, request.execution_status)
            if not ok:
                return self._resp(False, f'TestResult {request.result_id} not found')
            return self._resp(True, 'ok', {
                'result_id': request.result_id,
                'execution_status': request.execution_status,
            })
        except Exception as e:
            logger.exception('UpdateTestResultStatus failed')
            return self._resp(False, str(e))

    def UpdateTaskStatus(self, request, context=None):
        """更新 Task 的 status"""
        try:
            result = task_repository.update_status(request.task_id, request.status)
            if result is None:
                return self._resp(False, f'Task {request.task_id} not found')
            return self._resp(True, 'ok', result)
        except Exception as e:
            logger.exception('UpdateTaskStatus failed')
            return self._resp(False, str(e))

    # ========== P1.5c 跨服务读：报告/日志/分组 ==========

    def GetTaskMergeRelations(self, request, context=None):
        """查询 TaskMergeRelation（按 task_id）

        task_id 同时匹配 merged_task_id 与 source_task_id，返回所有关联关系。
        """
        try:
            items = task_merge_relation_repository.get_by_task_id(request.task_id)
            return self._resp(True, '', {'items': items})
        except Exception as e:
            logger.exception('GetTaskMergeRelations failed')
            return self._resp(False, str(e))

    def ListLogs(self, request, context=None):
        """查询 Log 列表（分页 + 过滤）

        支持 task_id / level / 日期范围过滤，按 id 倒序分页。
        """
        try:
            result = log_repository.list_logs(
                task_id=request.task_id or 0,
                level=request.level or '',
                start_date=request.start_date or '',
                end_date=request.end_date or '',
                page=request.page or 1,
                per_page=request.per_page or 20,
            )
            return self._resp(True, '', result)
        except Exception as e:
            logger.exception('ListLogs failed')
            return self._resp(False, str(e))

    def ListTestCaseGroups(self, request, context=None):
        """查询 TestCaseGroup 列表

        过滤逻辑删除，支持 algorithm_type / 名称搜索过滤。
        """
        try:
            items = testcase_repository.list_groups(
                algorithm_type=request.algorithm_type or '',
                search=request.search or '',
            )
            return self._resp(True, '', {'items': items})
        except Exception as e:
            logger.exception('ListTestCaseGroups failed')
            return self._resp(False, str(e))

    def GetTestCaseGroupsByIds(self, request, context=None):
        """按 ID 列表批量查询 TestCaseGroup"""
        try:
            items = testcase_repository.get_groups_by_ids(list(request.group_ids))
            return self._resp(True, '', {'items': items})
        except Exception as e:
            logger.exception('GetTestCaseGroupsByIds failed')
            return self._resp(False, str(e))

    def GetTestCaseGroupsByNames(self, request, context=None):
        """按名称列表批量查询 TestCaseGroup"""
        try:
            items = testcase_repository.get_groups_by_names(list(request.group_names))
            return self._resp(True, '', {'items': items})
        except Exception as e:
            logger.exception('GetTestCaseGroupsByNames failed')
            return self._resp(False, str(e))

    def GetTestCaseGroupById(self, request, context=None):
        """按 ID 查询单个 TestCaseGroup"""
        try:
            item = testcase_repository.get_group_by_id_as_dict(request.group_id)
            return self._resp(True, '', item)
        except Exception as e:
            logger.exception('GetTestCaseGroupById failed')
            return self._resp(False, str(e))

    def GetTestCaseGroupByName(self, request, context=None):
        """按名称查询单个 TestCaseGroup"""
        try:
            item = testcase_repository.get_group_by_name_as_dict(request.group_name)
            return self._resp(True, '', item)
        except Exception as e:
            logger.exception('GetTestCaseGroupByName failed')
            return self._resp(False, str(e))

    def CreateTestCaseGroup(self, request, context=None):
        """创建 TestCaseGroup"""
        try:
            import uuid as _uuid
            gid = request.group_id or str(_uuid.uuid4())
            item = testcase_repository.create_group_and_commit(
                gid, request.name, request.description or '', request.algorithm_type or '',
            )
            return self._resp(True, '', item)
        except Exception as e:
            logger.exception('CreateTestCaseGroup failed')
            return self._resp(False, str(e))

    def UpdateTestCaseGroup(self, request, context=None):
        """更新 TestCaseGroup（名称/描述/算法类型）

        若 name 非空且与当前不同，会先检查名称冲突。
        """
        try:
            item = testcase_repository.update_group_and_commit(
                request.group_id, request.name or '', request.description or '',
                request.algorithm_type or '',
            )
            return self._resp(True, '', item)
        except ValueError as e:
            return self._resp(False, str(e))
        except Exception as e:
            logger.exception('UpdateTestCaseGroup failed')
            return self._resp(False, str(e))

    def DeleteTestCaseGroup(self, request, context=None):
        """软删除 TestCaseGroup（含 cascade 选项）

        cascade=True 时同时软删该分组下所有 TestCase。
        """
        try:
            item = testcase_repository.delete_group_and_commit(request.group_id, request.cascade)
            return self._resp(True, '分组已删除', item)
        except ValueError as e:
            return self._resp(False, str(e))
        except Exception as e:
            logger.exception('DeleteTestCaseGroup failed')
            return self._resp(False, str(e))

    # ========== 聚合统计（供 stats_cache / home_service 用） ==========

    def GetTaskStats(self, request, context=None):
        """聚合统计 Task — count / group_by

        支持按 status / algorithm_type 过滤，可选 group_by 字段返回分组计数。
        不指定 group_by 时返回 {'total': N}；指定 group_by 时返回
        {'items': [{key, count}, ...]}。

        用于替代 stats_cache / home_service 中 `func.count(Task.id).filter(...)`
        的直连聚合查询。
        """
        try:
            result = task_repository.get_task_stats(
                status=request.status or '',
                algorithm_type=request.algorithm_type or '',
                group_by=request.group_by or '',
            )
            if 'error' in result:
                return self._resp(False, result['error'])
            return self._resp(True, '', result)
        except Exception as e:
            logger.exception('GetTaskStats failed')
            return self._resp(False, str(e))

    def GetTestCaseStats(self, request, context=None):
        """聚合统计 TestCase — count / group_by

        支持按 algorithm_type / group_id 过滤，可选 group_by 字段返回分组计数。
        不指定 group_by 时返回 {'total': N}；指定 group_by 时返回
        {'items': [{key, count}, ...]}。
        """
        try:
            result = testcase_repository.get_testcase_stats(
                algorithm_type=request.algorithm_type or '',
                group_id=request.group_id or '',
                group_by=request.group_by or '',
            )
            if 'error' in result:
                return self._resp(False, result['error'])
            return self._resp(True, '', result)
        except Exception as e:
            logger.exception('GetTestCaseStats failed')
            return self._resp(False, str(e))

    # ========== Log CRUD（P0-3 新增，替代 api_gateway/shared/utils 直连 DB）==========

    def BatchCreateLogs(self, request, context=None):
        """批量写入日志（shared/utils/log_handler 后台 worker 调用）

        接收 JSON 日志列表，逐条构造 Log PO 并批量 commit。
        返回写入后的 id 列表，顺序与请求一致。
        """
        try:
            logs = _loads(request.logs_json, [])
            if not logs:
                return self._resp(True, '', {'ids': []})
            ids = log_repository.batch_create(logs)
            return self._resp(True, '', {'ids': ids})
        except Exception as e:
            logger.exception('BatchCreateLogs failed')
            return self._resp(False, str(e))

    def GetLogStats(self, request, context=None):
        """查询日志统计（group_by level + count，含多字段过滤）"""
        try:
            result = log_repository.get_stats(
                level=request.level or '',
                module=request.module or '',
                category=request.category or '',
                mark=request.mark or '',
                device_id=request.device_id or 0,
                task_id=request.task_id or 0,
                keyword=request.keyword or '',
                content_include=request.content_include or '',
                content_exclude=request.content_exclude or '',
                start_time=request.start_time or '',
                end_time=request.end_time or '',
                algorithm_type=request.algorithm_type or '',
            )
            return self._resp(True, '', result)
        except Exception as e:
            logger.exception('GetLogStats failed')
            return self._resp(False, str(e))

    def ListLogsAfterId(self, request, context=None):
        """增量查询日志（id > last_id，返回 max_id）"""
        try:
            result = log_repository.list_after_id(
                request.last_id, request.limit or 100,
            )
            return self._resp(True, '', result)
        except Exception as e:
            logger.exception('ListLogsAfterId failed')
            return self._resp(False, str(e))

    def GetLogsForExport(self, request, context=None):
        """按 id 列表/条件查询日志（导出用）"""
        try:
            log_ids = list(request.log_ids) if request.log_ids else None
            items = log_repository.get_for_export(
                log_ids=log_ids,
                level=request.level or '',
                module=request.module or '',
            )
            return self._resp(True, '', {'items': items})
        except Exception as e:
            logger.exception('GetLogsForExport failed')
            return self._resp(False, str(e))

    def GetLogCount(self, request, context=None):
        """查询日志总数（含按日期范围 hot 日志计数）"""
        try:
            result = log_repository.get_count(request.start_date or '')
            return self._resp(True, '', result)
        except Exception as e:
            logger.exception('GetLogCount failed')
            return self._resp(False, str(e))

    def UpdateLogsMark(self, request, context=None):
        """批量更新日志标记"""
        try:
            count = log_repository.update_marks(list(request.log_ids), request.mark)
            return self._resp(True, '', {'updated': count})
        except Exception as e:
            logger.exception('UpdateLogsMark failed')
            return self._resp(False, str(e))

    def ClearLogs(self, request, context=None):
        """批量清除日志（按日期/标记）"""
        try:
            count = log_repository.clear(
                before_datetime=request.before_datetime or '',
                keep_marked=request.keep_marked,
            )
            return self._resp(True, '', {'deleted': count})
        except Exception as e:
            logger.exception('ClearLogs failed')
            return self._resp(False, str(e))

    def ArchiveLogs(self, request, context=None):
        """归档日志（按天数，dry_run 预检）

        读取冷日志并按 (task_id, test_case_id, date) 分组返回，
        然后删除已归档的记录。调用方（api_gateway）负责将分组写入 OSS。
        """
        try:
            result = log_repository.archive(
                days=request.days or 30,
                dry_run=request.dry_run,
            )
            return self._resp(True, '', result)
        except Exception as e:
            logger.exception('ArchiveLogs failed')
            return self._resp(False, str(e))
