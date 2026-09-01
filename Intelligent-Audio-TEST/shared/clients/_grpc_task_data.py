# -*- coding: utf-8 -*-
"""task_service / evaluation_service gRPC 便捷封装（从 grpc_clients.py 拆分，P4-4）。

封装跨服务提交评估、写入结果、更新 TaskCase 状态、任务/日志/分组查询等便捷函数，
替代各服务直连 DB。
"""
from shared.clients._grpc_stubs import (
    get_evaluation_service_stub,
    get_task_data_service_stub,
    get_task_config_service_stub,
    get_execution_service_stub,
)


def submit_evaluate_case(task_id, result_id, test_case_id, algorithm_result, eval_params):
    """通过 gRPC 调用 evaluation_service 的 EvaluationService.EvaluateCase

    供 api_test_service / e2e_test_service 等执行器跨服务提交评估请求。
    已从 task_service.ExecutionService 迁移至 evaluation_service.EvaluationService。

    Args:
        task_id: 任务ID
        result_id: 测试结果ID
        test_case_id: 测试用例ID
        algorithm_result: 算法结果字典
        eval_params: 评估参数字典 (algorithm_type, test_type, round_number, ...)
    """
    import json as _json
    from shared.proto import evaluation_service_pb2 as eval_pb
    stub = get_evaluation_service_stub()
    req = eval_pb.EvaluateCaseRequest(
        task_id=str(task_id),
        result_id=str(result_id),
        test_case_id=str(test_case_id),
        algorithm_result=_json.dumps(algorithm_result or {}, ensure_ascii=False, default=str),
        eval_params=_json.dumps(eval_params or {}, ensure_ascii=False, default=str),
    )
    resp = stub.EvaluateCase(req)
    if not resp.success:
        raise RuntimeError(f"EvaluateCase gRPC 调用失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else {}


def submit_reevaluate(task_id, reextract_device_output=True, reevaluate_type='all'):
    """通过 gRPC 调用 evaluation_service 的 EvaluationService.Reevaluate

    供 task_service 提交任务级重新评估（已从 task_service.core.reevaluation_executor 迁移至
    evaluation_service.application.handlers.reevaluation_executor）。

    Args:
        task_id: 任务ID
        reextract_device_output: 是否重新提取设备输出
        reevaluate_type: 重新评估类型 ('all' / 'failed')

    Returns:
        dict: {success, message, data}
    """
    import json as _json
    from shared.proto import evaluation_service_pb2 as eval_pb
    stub = get_evaluation_service_stub()
    req = eval_pb.ReevaluateRequest(
        task_id=str(task_id),
        reextract_device_output=reextract_device_output,
        reevaluate_type=reevaluate_type or 'all',
    )
    resp = stub.Reevaluate(req)
    return {
        'success': resp.success,
        'message': resp.message,
        'data': _json.loads(resp.data) if resp.data else {},
    }


def submit_result(task_id, result_data):
    """通过 gRPC 调用 task_service.TaskDataService.SubmitResult 写入 TestResult

    供 api_test_service / e2e_test_service 执行完成后跨服务写入测试结果，
    替代直连 DB 的 INSERT INTO test_results。

    Args:
        task_id: 任务ID
        result_data: TestResult 字段字典，包含 test_case_id / device_id / api_id /
                      algorithm_type / execution_status / response_time /
                      algorithm_result / execution_steps / result_data /
                      result_data_path / error_message

    Returns:
        int: 新建 TestResult 的 result_id
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.SubmitResultRequest(
        task_id=int(task_id),
        result_data=_json.dumps(result_data or {}, ensure_ascii=False, default=str),
    )
    resp = stub.SubmitResult(req)
    if not resp.success:
        raise RuntimeError(f"SubmitResult gRPC 调用失败: {resp.message}")
    data = _json.loads(resp.data) if resp.data else {}
    return data.get('result_id')


def update_task_case_status(task_id, case_id, status=None, execution_status=None,
                            evaluation_status=None, error_message=None):
    """通过 gRPC 调用 task_service.TaskDataService.UpdateTaskCaseStatus 更新 TaskCase 状态

    供 api_test_service / e2e_test_service 执行完成后更新 TaskCase 执行状态，
    替代直连 DB 的 db.session.query(TaskCase).update(...)。

    Args:
        task_id: 任务ID
        case_id: 测试用例ID
        status: 可选，TaskCase.status (pending/completed/failed/skipped)
        execution_status: 可选，执行状态 (pending/running/completed/stopped/failed)
        evaluation_status: 可选，评估状态
        error_message: 可选，错误信息

    Returns:
        bool: 是否有字段被更新
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.UpdateTaskCaseStatusRequest(
        task_id=int(task_id),
        case_id=str(case_id),
        status=status or '',
        execution_status=execution_status or '',
        evaluation_status=evaluation_status or '',
        error_message=error_message or '',
    )
    resp = stub.UpdateTaskCaseStatus(req)
    if not resp.success:
        raise RuntimeError(f"UpdateTaskCaseStatus gRPC 调用失败: {resp.message}")
    data = _json.loads(resp.data) if resp.data else {}
    return data.get('updated', False)


def notify_task_progress(task_id, force=False):
    """通过 gRPC 调用 task_service.ExecutionService.NotifyProgress

    供 evaluation_service 评估完成后通知 task_service 发送进度更新。

    Args:
        task_id: 任务ID
        force: 是否强制更新，跳过节流逻辑
    """
    from shared.proto import task_service_pb2 as task_pb
    stub = get_execution_service_stub()
    req = task_pb.NotifyProgressRequest(task_id=str(task_id), force=force)
    resp = stub.NotifyProgress(req)
    if not resp.success:
        import logging
        logging.getLogger(__name__).warning(f"NotifyProgress gRPC 调用失败: {resp.message}")


def notify_case_completed(task_id):
    """通过 gRPC 调用 task_service.ExecutionService.NotifyCaseCompleted

    供 evaluation_service 评估完成后通知 task_service 唤醒等待线程。

    Args:
        task_id: 任务ID
    """
    from shared.proto import task_service_pb2 as task_pb
    stub = get_execution_service_stub()
    req = task_pb.NotifyCaseCompletedRequest(task_id=str(task_id))
    resp = stub.NotifyCaseCompleted(req)
    if not resp.success:
        import logging
        logging.getLogger(__name__).warning(f"NotifyCaseCompleted gRPC 调用失败: {resp.message}")


def get_task_by_id(task_id):
    """通过 gRPC 按 ID 查询 Task

    返回 dict 或 None: {id, name, type, status, total_cases, ...}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.GetTaskByIdRequest(task_id=int(task_id))
    resp = stub.GetTaskById(req)
    if not resp.success:
        raise RuntimeError(f"GetTaskById gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else None


def get_task_devices(task_id):
    """通过 gRPC 查询 Task 关联的设备列表

    返回 dict: {'items': [{id, name, ...}, ...]}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.GetTaskDevicesRequest(task_id=int(task_id))
    resp = stub.GetTaskDevices(req)
    if not resp.success:
        raise RuntimeError(f"GetTaskDevices gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else {}


def get_task_apis(task_id):
    """通过 gRPC 查询 Task 关联的 API 列表

    返回 dict: {'items': [{id, name, ...}, ...]}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.GetTaskApisRequest(task_id=int(task_id))
    resp = stub.GetTaskApis(req)
    if not resp.success:
        raise RuntimeError(f"GetTaskApis gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else {}


def get_task_cases_by_ids(task_id, case_ids=None):
    """通过 gRPC 按 task_id + case_ids 查询 TaskCase 列表

    返回 dict: {'items': [{test_case_id, execution_status, ...}, ...]}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.GetTaskCaseByIdsRequest(
        task_id=int(task_id),
        case_ids=[str(c) for c in case_ids] if case_ids else [],
    )
    resp = stub.GetTaskCaseByIds(req)
    if not resp.success:
        raise RuntimeError(f"GetTaskCaseByIds gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else {}


def list_tasks_config(page=1, per_page=20, status=None, type=None,
                     algorithm_type=None, search=None, start_date=None, end_date=None):
    """通过 gRPC 调用 TaskConfigService.ListTasks 查询任务列表

    返回 dict: {'items': [...], 'total': N, 'page': P, 'per_page': PP}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_config_service_stub()
    req = task_pb.ListTasksRequest(
        page=page,
        per_page=per_page,
        status=status or '',
        type=type or '',
        algorithm_type=algorithm_type or '',
        search=search or '',
        start_date=start_date or '',
        end_date=end_date or '',
    )
    resp = stub.ListTasks(req)
    if not resp.success:
        raise RuntimeError(f"ListTasks gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else {}


def get_task_merge_relations(task_id):
    """通过 gRPC 查询 TaskMergeRelation（按 task_id）

    供 api_gateway 报告对比等场景跨服务查询合并关系，替代直连 DB。
    返回 dict：{'items': [{id, merged_task_id, source_task_id, source_result_count}, ...]}

    Args:
        task_id: 任务ID（同时匹配 merged_task_id 与 source_task_id）

    Returns:
        dict: {'items': [...]}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.GetTaskMergeRelationsRequest(task_id=int(task_id))
    resp = stub.GetTaskMergeRelations(req)
    if not resp.success:
        raise RuntimeError(f"GetTaskMergeRelations gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else {}


def list_logs(task_id=None, level=None, page=1, per_page=20, start_date=None, end_date=None):
    """通过 gRPC 查询 Log 列表（分页 + 过滤）

    供 api_gateway 日志查询跨服务读取 task_service 的 Log，替代直连 DB。
    返回 dict：{'items': [...], 'total': N, 'page': P, 'per_page': PP}

    Args:
        task_id: 可选，按任务ID过滤
        level: 可选，按日志级别过滤
        page: 页码，默认 1
        per_page: 每页条数，默认 20
        start_date: 可选，开始日期（ISO 字符串）
        end_date: 可选，结束日期（ISO 字符串）

    Returns:
        dict: {'items': [...], 'total': N, 'page': P, 'per_page': PP}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.ListLogsRequest(
        task_id=int(task_id) if task_id else 0,
        level=level or '',
        page=page,
        per_page=per_page,
        start_date=start_date or '',
        end_date=end_date or '',
    )
    resp = stub.ListLogs(req)
    if not resp.success:
        raise RuntimeError(f"ListLogs gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else {}


def batch_create_logs(logs_list):
    """通过 gRPC 批量写入日志（替代 shared/utils/log_handler 直连 DB）

    供 log_handler 后台 worker 调用。返回写入后的 id 列表。

    Args:
        logs_list: 日志 dict 列表 [{time, level, category, module, source, content, ...}, ...]

    Returns:
        list[int]: 写入后的 id 列表
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.BatchCreateLogsRequest(
        logs_json=_json.dumps(logs_list, default=str),
    )
    resp = stub.BatchCreateLogs(req)
    if not resp.success:
        raise RuntimeError(f"BatchCreateLogs gRPC 失败: {resp.message}")
    data = _json.loads(resp.data) if resp.data else {}
    return data.get('ids', [])


def get_log_stats(level=None, module=None, category=None, mark=None,
                  device_id=None, task_id=None, keyword=None,
                  content_include=None, content_exclude=None,
                  start_time=None, end_time=None, algorithm_type=None):
    """通过 gRPC 查询日志统计（group_by level + count）

    供 api_gateway log_query_service.get_stats 调用，替代直连 DB。
    返回 dict：{'total': N, 'debug': N, 'info': N, 'warning': N, 'error': N, 'critical': N}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.GetLogStatsRequest(
        level=level or '',
        module=module or '',
        category=category or '',
        mark=mark or '',
        device_id=int(device_id) if device_id else 0,
        task_id=int(task_id) if task_id else 0,
        keyword=keyword or '',
        content_include=content_include or '',
        content_exclude=content_exclude or '',
        start_time=start_time or '',
        end_time=end_time or '',
        algorithm_type=algorithm_type or '',
    )
    resp = stub.GetLogStats(req)
    if not resp.success:
        raise RuntimeError(f"GetLogStats gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else {}


def list_logs_after_id(last_id, limit=100):
    """通过 gRPC 增量查询日志（id > last_id）

    供 api_gateway log_query_service.refresh_logs 调用，替代直连 DB。
    返回 dict：{'items': [...], 'max_id': N}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.ListLogsAfterIdRequest(last_id=last_id, limit=limit)
    resp = stub.ListLogsAfterId(req)
    if not resp.success:
        raise RuntimeError(f"ListLogsAfterId gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else {}


def get_logs_for_export(log_ids=None, level=None, module=None):
    """通过 gRPC 按条件查询日志（导出用）

    供 api_gateway log_query_service.export_logs 调用，替代直连 DB。
    返回 dict：{'items': [{id, time, level, module, content, mark}, ...]}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.GetLogsForExportRequest(
        log_ids=list(log_ids) if log_ids else [],
        level=level or '',
        module=module or '',
    )
    resp = stub.GetLogsForExport(req)
    if not resp.success:
        raise RuntimeError(f"GetLogsForExport gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else {}


def get_log_count(start_date=None):
    """通过 gRPC 查询日志总数（含按日期范围 hot 日志计数）

    供 api_gateway log_query_service.get_archive_status 调用，替代直连 DB。
    返回 dict：{'total': N, 'hot': N, 'cold': N}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.GetLogCountRequest(start_date=start_date or '')
    resp = stub.GetLogCount(req)
    if not resp.success:
        raise RuntimeError(f"GetLogCount gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else {}


def update_logs_mark(log_ids, mark):
    """通过 gRPC 批量更新日志标记

    供 api_gateway log_command_service.mark_logs 调用，替代直连 DB。
    返回 dict：{'updated': N}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.UpdateLogsMarkRequest(
        log_ids=list(log_ids),
        mark=mark or '',
    )
    resp = stub.UpdateLogsMark(req)
    if not resp.success:
        raise RuntimeError(f"UpdateLogsMark gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else {}


def clear_logs(before_datetime=None, keep_marked=False):
    """通过 gRPC 批量清除日志

    供 api_gateway log_command_service.clear_logs 调用，替代直连 DB。
    返回 dict：{'deleted': N}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.ClearLogsRequest(
        before_datetime=before_datetime or '',
        keep_marked=keep_marked,
    )
    resp = stub.ClearLogs(req)
    if not resp.success:
        raise RuntimeError(f"ClearLogs gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else {}


def archive_logs(days=30, dry_run=False):
    """通过 gRPC 归档日志（按天数）

    供 api_gateway log_command_service.archive_logs 调用，替代直连 DB。
    返回 dict：{'archived_count': N, 'deleted_count': N, 'remaining_count': N, 'groups': {...}}
    dry_run 时返回 {'cold_logs_count': N, 'cutoff_date': str}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.ArchiveLogsRequest(days=days, dry_run=dry_run)
    resp = stub.ArchiveLogs(req)
    if not resp.success:
        raise RuntimeError(f"ArchiveLogs gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else {}


def list_testcase_groups(algorithm_type=None, search=None):
    """通过 gRPC 查询 TestCaseGroup 列表

    供 api_gateway 分组管理跨服务读取 task_service 的 TestCaseGroup，替代直连 DB。
    返回 dict：{'items': [{id, name, description, algorithm_type}, ...]}

    Args:
        algorithm_type: 可选，按算法类型过滤
        search: 可选，按名称模糊搜索

    Returns:
        dict: {'items': [...]}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.ListTestCaseGroupsRequest(
        algorithm_type=algorithm_type or '',
        search=search or '',
    )
    resp = stub.ListTestCaseGroups(req)
    if not resp.success:
        raise RuntimeError(f"ListTestCaseGroups gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else {}


def get_testcase_groups_by_ids(group_ids):
    """通过 gRPC 按 ID 列表批量查询 TestCaseGroup

    返回 dict: {'items': [{id, name, description, algorithm_type}, ...]}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.GetTestCaseGroupsByIdsRequest(group_ids=[str(g) for g in group_ids])
    resp = stub.GetTestCaseGroupsByIds(req)
    if not resp.success:
        raise RuntimeError(f"GetTestCaseGroupsByIds gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else {}


def get_testcase_groups_by_names(group_names):
    """通过 gRPC 按名称列表批量查询 TestCaseGroup

    返回 dict: {'items': [{id, name, description, algorithm_type}, ...]}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.GetTestCaseGroupsByNamesRequest(group_names=list(group_names))
    resp = stub.GetTestCaseGroupsByNames(req)
    if not resp.success:
        raise RuntimeError(f"GetTestCaseGroupsByNames gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else {}


def get_testcase_group_by_id(group_id):
    """通过 gRPC 按 ID 查询单个 TestCaseGroup

    返回 dict 或 None: {id, name, description, algorithm_type}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.GetTestCaseGroupByIdRequest(group_id=str(group_id))
    resp = stub.GetTestCaseGroupById(req)
    if not resp.success:
        raise RuntimeError(f"GetTestCaseGroupById gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else None


def get_testcase_group_by_name(group_name):
    """通过 gRPC 按名称查询单个 TestCaseGroup

    返回 dict 或 None: {id, name, description, algorithm_type}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.GetTestCaseGroupByNameRequest(group_name=group_name)
    resp = stub.GetTestCaseGroupByName(req)
    if not resp.success:
        raise RuntimeError(f"GetTestCaseGroupByName gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else None


def create_testcase_group(name, description='', algorithm_type='', group_id=None):
    """通过 gRPC 创建 TestCaseGroup

    返回 dict: {id, name, description, algorithm_type}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.CreateTestCaseGroupRequest(
        name=name,
        description=description or '',
        algorithm_type=algorithm_type or '',
        group_id=group_id or '',
    )
    resp = stub.CreateTestCaseGroup(req)
    if not resp.success:
        raise RuntimeError(f"CreateTestCaseGroup gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else {}


def get_task_stats(status=None, algorithm_type=None, group_by=None):
    """通过 gRPC 调用 task_service.TaskDataService.GetTaskStats 聚合统计 Task

    供 stats_cache / home_service 跨服务聚合统计 task_service 的 Task，替代直连 DB
    的 `func.count(Task.id).filter(...)` 查询。

    Args:
        status: 可选，按任务状态过滤（pending/queued/running/evaluating/completed/...）
        algorithm_type: 可选，按算法类型过滤
        group_by: 可选，分组字段（status / algorithm_type / type）；为空返回 total

    Returns:
        dict: {'total': N} 或 {'items': [{'key': str, 'count': int}, ...]}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.TaskAggStatsRequest(
        status=status or '',
        algorithm_type=algorithm_type or '',
        group_by=group_by or '',
    )
    resp = stub.GetTaskStats(req)
    if not resp.success:
        raise RuntimeError(f"GetTaskStats gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else {}


def get_testcase_stats(algorithm_type=None, group_id=None, group_by=None):
    """通过 gRPC 调用 task_service.TaskDataService.GetTestCaseStats 聚合统计 TestCase

    供 stats_cache / home_service 跨服务聚合统计 task_service 的 TestCase，替代直连 DB
    的 `func.count(TestCase.id).filter(...)` 查询。

    Args:
        algorithm_type: 可选，按算法类型过滤
        group_id: 可选，按分组 ID 过滤
        group_by: 可选，分组字段（algorithm_type / group_id）；为空返回 total

    Returns:
        dict: {'total': N} 或 {'items': [{'key': str, 'count': int}, ...]}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.TestCaseAggStatsRequest(
        algorithm_type=algorithm_type or '',
        group_id=int(group_id) if group_id else 0,
        group_by=group_by or '',
    )
    resp = stub.GetTestCaseStats(req)
    if not resp.success:
        raise RuntimeError(f"GetTestCaseStats gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else {}
