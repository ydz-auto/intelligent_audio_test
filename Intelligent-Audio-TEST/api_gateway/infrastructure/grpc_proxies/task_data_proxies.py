# -*- coding: utf-8 -*-
"""TaskDataService 便捷封装代理（从 task_config_proxies.py 拆分，P4-4）。

封装 task_service.TaskDataService 的聚合统计 / 分组管理 / 日志查询写操作，
作为 api_gateway ACL 层，避免 application 层直接 import shared.clients.grpc_clients。
"""
import json

from shared.clients.grpc_clients import get_task_data_service_stub

from ._common import _grpc_call

from shared.proto import task_service_pb2 as task_pb


class _TaskDataProxy:
    """TaskDataService 便捷封装代理

    封装 task_service.TaskDataService 的聚合统计（Task/TestCase）、
    TestCaseGroup 查询/创建、日志查询/写入/标记/清除/归档等便捷 RPC，
    供 api_gateway application 层调用，替代直接 import shared.clients.grpc_clients。
    """

    @property
    def stub(self):
        """获取 TaskDataService stub（供需要直接调 RPC 的场景使用）"""
        return get_task_data_service_stub()

    # ---- 聚合统计 ----

    def get_task_stats(self, status=None, algorithm_type=None, group_by=None):
        """通过 gRPC 聚合统计 Task（group_by 可选 status/algorithm_type/type）"""
        def _call():
            stub = get_task_data_service_stub()
            resp = stub.GetTaskStats(task_pb.TaskAggStatsRequest(
                status=status or '',
                algorithm_type=algorithm_type or '',
                group_by=group_by or '',
            ))
            if not resp.success:
                raise RuntimeError(f"GetTaskStats gRPC 失败: {resp.message}")
            return json.loads(resp.data) if resp.data else {}
        return _grpc_call(_call, default_return={}, error_msg_prefix='GetTaskStats gRPC 失败')

    def get_testcase_stats(self, algorithm_type=None, group_id=None, group_by=None):
        """通过 gRPC 聚合统计 TestCase（group_by 可选 algorithm_type/group_id）"""
        def _call():
            stub = get_task_data_service_stub()
            resp = stub.GetTestCaseStats(task_pb.TestCaseAggStatsRequest(
                algorithm_type=algorithm_type or '',
                group_id=int(group_id) if group_id else 0,
                group_by=group_by or '',
            ))
            if not resp.success:
                raise RuntimeError(f"GetTestCaseStats gRPC 失败: {resp.message}")
            return json.loads(resp.data) if resp.data else {}
        return _grpc_call(_call, default_return={}, error_msg_prefix='GetTestCaseStats gRPC 失败')

    # ---- TestCaseGroup 查询/创建 ----

    def list_testcase_groups(self, algorithm_type=None, search=None):
        """通过 gRPC 查询 TestCaseGroup 列表"""
        def _call():
            stub = get_task_data_service_stub()
            resp = stub.ListTestCaseGroups(task_pb.ListTestCaseGroupsRequest(
                algorithm_type=algorithm_type or '',
                search=search or '',
            ))
            if not resp.success:
                raise RuntimeError(f"ListTestCaseGroups gRPC 失败: {resp.message}")
            return json.loads(resp.data) if resp.data else {}
        return _grpc_call(_call, default_return={}, error_msg_prefix='ListTestCaseGroups gRPC 失败')

    def get_testcase_groups_by_ids(self, group_ids):
        """通过 gRPC 按 ID 列表批量查询 TestCaseGroup"""
        def _call():
            stub = get_task_data_service_stub()
            resp = stub.GetTestCaseGroupsByIds(task_pb.GetTestCaseGroupsByIdsRequest(
                group_ids=[str(g) for g in group_ids],
            ))
            if not resp.success:
                raise RuntimeError(f"GetTestCaseGroupsByIds gRPC 失败: {resp.message}")
            return json.loads(resp.data) if resp.data else {}
        return _grpc_call(_call, default_return={}, error_msg_prefix='GetTestCaseGroupsByIds gRPC 失败')

    def get_testcase_groups_by_names(self, group_names):
        """通过 gRPC 按名称列表批量查询 TestCaseGroup"""
        def _call():
            stub = get_task_data_service_stub()
            resp = stub.GetTestCaseGroupsByNames(task_pb.GetTestCaseGroupsByNamesRequest(
                group_names=list(group_names),
            ))
            if not resp.success:
                raise RuntimeError(f"GetTestCaseGroupsByNames gRPC 失败: {resp.message}")
            return json.loads(resp.data) if resp.data else {}
        return _grpc_call(_call, default_return={}, error_msg_prefix='GetTestCaseGroupsByNames gRPC 失败')

    def get_testcase_group_by_id(self, group_id):
        """通过 gRPC 按 ID 查询单个 TestCaseGroup"""
        def _call():
            stub = get_task_data_service_stub()
            resp = stub.GetTestCaseGroupById(task_pb.GetTestCaseGroupByIdRequest(
                group_id=str(group_id),
            ))
            if not resp.success:
                raise RuntimeError(f"GetTestCaseGroupById gRPC 失败: {resp.message}")
            return json.loads(resp.data) if resp.data else None
        return _grpc_call(_call, default_return=None, error_msg_prefix='GetTestCaseGroupById gRPC 失败')

    def get_testcase_group_by_name(self, group_name):
        """通过 gRPC 按名称查询单个 TestCaseGroup"""
        def _call():
            stub = get_task_data_service_stub()
            resp = stub.GetTestCaseGroupByName(task_pb.GetTestCaseGroupByNameRequest(
                group_name=group_name,
            ))
            if not resp.success:
                raise RuntimeError(f"GetTestCaseGroupByName gRPC 失败: {resp.message}")
            return json.loads(resp.data) if resp.data else None
        return _grpc_call(_call, default_return=None, error_msg_prefix='GetTestCaseGroupByName gRPC 失败')

    def create_testcase_group(self, name, description='', algorithm_type='', group_id=None):
        """通过 gRPC 创建 TestCaseGroup"""
        def _call():
            stub = get_task_data_service_stub()
            resp = stub.CreateTestCaseGroup(task_pb.CreateTestCaseGroupRequest(
                name=name,
                description=description or '',
                algorithm_type=algorithm_type or '',
                group_id=group_id or '',
            ))
            if not resp.success:
                raise RuntimeError(f"CreateTestCaseGroup gRPC 失败: {resp.message}")
            return json.loads(resp.data) if resp.data else {}
        return _grpc_call(_call, default_return={}, error_msg_prefix='CreateTestCaseGroup gRPC 失败')

    def update_testcase_group(self, group_id, name='', description='', algorithm_type=''):
        """通过 gRPC 更新 TestCaseGroup"""
        def _call():
            stub = get_task_data_service_stub()
            resp = stub.UpdateTestCaseGroup(task_pb.UpdateTestCaseGroupRequest(
                group_id=str(group_id),
                name=name or '',
                description=description or '',
                algorithm_type=algorithm_type or '',
            ))
            if not resp.success:
                raise RuntimeError(f"UpdateTestCaseGroup gRPC 失败: {resp.message}")
            return json.loads(resp.data) if resp.data else {}
        return _grpc_call(_call, default_return={}, error_msg_prefix='UpdateTestCaseGroup gRPC 失败')

    def delete_testcase_group(self, group_id, cascade=False):
        """通过 gRPC 软删除 TestCaseGroup"""
        def _call():
            stub = get_task_data_service_stub()
            resp = stub.DeleteTestCaseGroup(task_pb.DeleteTestCaseGroupRequest(
                group_id=str(group_id),
                cascade=bool(cascade),
            ))
            if not resp.success:
                raise RuntimeError(f"DeleteTestCaseGroup gRPC 失败: {resp.message}")
            return json.loads(resp.data) if resp.data else {}
        return _grpc_call(_call, default_return={}, error_msg_prefix='DeleteTestCaseGroup gRPC 失败')

    # ---- 日志查询 ----

    def list_logs(self, task_id=None, level=None, page=1, per_page=20, start_date=None, end_date=None):
        """通过 gRPC 查询 Log 列表（分页 + 过滤）"""
        def _call():
            stub = get_task_data_service_stub()
            resp = stub.ListLogs(task_pb.ListLogsRequest(
                task_id=int(task_id) if task_id else 0,
                level=level or '',
                page=page,
                per_page=per_page,
                start_date=start_date or '',
                end_date=end_date or '',
            ))
            if not resp.success:
                raise RuntimeError(f"ListLogs gRPC 失败: {resp.message}")
            return json.loads(resp.data) if resp.data else {}
        return _grpc_call(_call, default_return={}, error_msg_prefix='ListLogs gRPC 失败')

    def get_log_stats(self, level=None, module=None, category=None, mark=None,
                      device_id=None, task_id=None, keyword=None,
                      content_include=None, content_exclude=None,
                      start_time=None, end_time=None, algorithm_type=None):
        """通过 gRPC 查询日志统计（group_by level + count）"""
        def _call():
            stub = get_task_data_service_stub()
            resp = stub.GetLogStats(task_pb.GetLogStatsRequest(
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
            ))
            if not resp.success:
                raise RuntimeError(f"GetLogStats gRPC 失败: {resp.message}")
            return json.loads(resp.data) if resp.data else {}
        return _grpc_call(_call, default_return={}, error_msg_prefix='GetLogStats gRPC 失败')

    def list_logs_after_id(self, last_id, limit=100):
        """通过 gRPC 增量查询日志（id > last_id）"""
        def _call():
            stub = get_task_data_service_stub()
            resp = stub.ListLogsAfterId(task_pb.ListLogsAfterIdRequest(
                last_id=last_id, limit=limit,
            ))
            if not resp.success:
                raise RuntimeError(f"ListLogsAfterId gRPC 失败: {resp.message}")
            return json.loads(resp.data) if resp.data else {}
        return _grpc_call(_call, default_return={}, error_msg_prefix='ListLogsAfterId gRPC 失败')

    def get_logs_for_export(self, log_ids=None, level=None, module=None):
        """通过 gRPC 按条件查询日志（导出用）"""
        def _call():
            stub = get_task_data_service_stub()
            resp = stub.GetLogsForExport(task_pb.GetLogsForExportRequest(
                log_ids=list(log_ids) if log_ids else [],
                level=level or '',
                module=module or '',
            ))
            if not resp.success:
                raise RuntimeError(f"GetLogsForExport gRPC 失败: {resp.message}")
            return json.loads(resp.data) if resp.data else {}
        return _grpc_call(_call, default_return={}, error_msg_prefix='GetLogsForExport gRPC 失败')

    def get_log_count(self, start_date=None):
        """通过 gRPC 查询日志总数（含按日期范围 hot 日志计数）"""
        def _call():
            stub = get_task_data_service_stub()
            resp = stub.GetLogCount(task_pb.GetLogCountRequest(
                start_date=start_date or '',
            ))
            if not resp.success:
                raise RuntimeError(f"GetLogCount gRPC 失败: {resp.message}")
            return json.loads(resp.data) if resp.data else {}
        return _grpc_call(_call, default_return={}, error_msg_prefix='GetLogCount gRPC 失败')

    # ---- 日志写操作 ----

    def update_logs_mark(self, log_ids, mark):
        """通过 gRPC 批量更新日志标记"""
        def _call():
            stub = get_task_data_service_stub()
            resp = stub.UpdateLogsMark(task_pb.UpdateLogsMarkRequest(
                log_ids=list(log_ids),
                mark=mark or '',
            ))
            if not resp.success:
                raise RuntimeError(f"UpdateLogsMark gRPC 失败: {resp.message}")
            return json.loads(resp.data) if resp.data else {}
        return _grpc_call(_call, default_return={}, error_msg_prefix='UpdateLogsMark gRPC 失败')

    def clear_logs(self, before_datetime=None, keep_marked=False):
        """通过 gRPC 批量清除日志"""
        def _call():
            stub = get_task_data_service_stub()
            resp = stub.ClearLogs(task_pb.ClearLogsRequest(
                before_datetime=before_datetime or '',
                keep_marked=keep_marked,
            ))
            if not resp.success:
                raise RuntimeError(f"ClearLogs gRPC 失败: {resp.message}")
            return json.loads(resp.data) if resp.data else {}
        return _grpc_call(_call, default_return={}, error_msg_prefix='ClearLogs gRPC 失败')

    def archive_logs(self, days=30, dry_run=False):
        """通过 gRPC 归档日志（按天数）"""
        def _call():
            stub = get_task_data_service_stub()
            resp = stub.ArchiveLogs(task_pb.ArchiveLogsRequest(
                days=days, dry_run=dry_run,
            ))
            if not resp.success:
                raise RuntimeError(f"ArchiveLogs gRPC 失败: {resp.message}")
            return json.loads(resp.data) if resp.data else {}
        return _grpc_call(_call, default_return={}, error_msg_prefix='ArchiveLogs gRPC 失败')


# TaskData 便捷封装模块级单例
task_data_service = _TaskDataProxy()
