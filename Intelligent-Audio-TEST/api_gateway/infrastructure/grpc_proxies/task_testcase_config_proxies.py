# -*- coding: utf-8 -*-
"""Task / TestCase 配置 CRUD 代理（从 task_config_proxies.py 拆分，P4-4）。

Task/TestCase 的 gRPC 代理类及模块级单例，作为 api_gateway 的 ACL 层，
避免 application 层直接 import shared.clients.grpc_clients。
"""
import json

from shared.clients.grpc_clients import (
    get_task_config_service_stub,
    get_testcase_config_service_stub,
)

from ._common import _grpc_call

from shared.proto import task_service_pb2 as task_pb


# ==================== Task 配置 CRUD 代理 ====================

class _TaskConfigProxy:
    """Task 配置 CRUD 代理：把方法调用转发到 gRPC TaskConfigService

    替代原 TaskCommandService/TaskQueryService/TaskLifecycleService 直接操作 DB 的方式，
    网关侧不再 import Task 模型和 get_db_session()，统一走 gRPC。
    所有方法返回 dict: {success, message, data, code}
    """

    def _resp(self, resp):
        """统一解析 TaskConfigResponse 为 dict"""
        data = json.loads(resp.data) if resp.data else None
        result = {'success': resp.success, 'message': resp.message, 'data': data}
        # 失败响应的业务码经 data JSON 透传（proto 仅 success/message/data 三字段），
        # 提升到顶层供 BFF/路由映射 HTTP 状态码（INT-141 F2）
        if not resp.success and isinstance(data, dict) and isinstance(data.get('code'), int):
            result['code'] = data['code']
        return result

    @property
    def stub(self):
        """获取 TaskConfigService stub（供需要直接调 RPC 的场景使用）"""
        return get_task_config_service_stub()

    # ---- 写操作 ----

    def create(self, data):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_task_config_service_stub()
            resp = stub.CreateTaskConfig(task_pb.CreateTaskConfigRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'创建任务失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='创建任务失败',
        )

    def update(self, task_id, data):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_task_config_service_stub()
            resp = stub.UpdateTaskConfig(task_pb.UpdateTaskConfigRequest(
                task_id=int(task_id),
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'更新任务失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='更新任务失败',
        )

    def delete(self, task_id):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_task_config_service_stub()
            resp = stub.DeleteTaskConfig(task_pb.DeleteTaskConfigRequest(
                task_id=int(task_id),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'删除任务失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='删除任务失败',
        )

    def update_cases(self, task_id, data):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_task_config_service_stub()
            resp = stub.UpdateTaskCases(task_pb.UpdateTaskCasesRequest(
                task_id=int(task_id),
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'更新用例失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='更新用例失败',
        )

    def batch_action(self, data):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_task_config_service_stub()
            resp = stub.BatchActionTasks(task_pb.BatchActionTasksRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'批量操作失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='批量操作失败',
        )

    def merge(self, data):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_task_config_service_stub()
            resp = stub.MergeTasks(task_pb.MergeTasksRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'合并任务失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='合并任务失败',
        )

    # ---- 读操作 ----

    def list_tasks(self, page=1, per_page=10, status=None, device_type=None,
                   algorithm_type=None, search=None, start_date=None, end_date=None,
                   favorite=False, deleted=False, evaluation_status=None, merged=False):
        """任务列表（device_type 经 proto type 字段承载：按用例级被测设备类型过滤）

        favorite/deleted（INT-141）：收藏/回收站过滤；操作人 user_id 经
        x-user-id metadata 自动透传（ClientUserContextInterceptor）。
        evaluation_status（INT-301）：按任务级评估状态过滤（与执行状态并列）。
        merged（INT-298）：仅合并容器任务（对齐 V9.7.10 合并页签数据源）。
        """
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_task_config_service_stub()
            resp = stub.ListTasks(task_pb.ListTasksRequest(
                page=int(page),
                per_page=int(per_page),
                status=status or '',
                type=device_type or '',
                algorithm_type=algorithm_type or '',
                search=search or '',
                start_date=start_date or '',
                end_date=end_date or '',
                favorite=bool(favorite),
                deleted=bool(deleted),
                evaluation_status=evaluation_status or '',
                merged=bool(merged),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'查询任务列表失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='查询任务列表失败',
        )

    # ---- 收藏 / 回收站（INT-141）----

    def favorite(self, entity_type, entity_id):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_task_config_service_stub()
            resp = stub.FavoriteTask(task_pb.FavoriteEntityRequest(
                entity_type=str(entity_type),
                entity_id=str(entity_id),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'收藏失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='收藏失败',
        )

    def unfavorite(self, entity_type, entity_id):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_task_config_service_stub()
            resp = stub.UnfavoriteTask(task_pb.FavoriteEntityRequest(
                entity_type=str(entity_type),
                entity_id=str(entity_id),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'取消收藏失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='取消收藏失败',
        )

    def list_favorite_ids(self, entity_type=None):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_task_config_service_stub()
            resp = stub.ListFavoriteIds(task_pb.ListFavoriteIdsRequest(
                entity_type=entity_type or '',
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'查询收藏列表失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='查询收藏列表失败',
        )

    def list_deleted_tasks(self, page=1, per_page=20, search=None):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_task_config_service_stub()
            resp = stub.ListDeletedTasks(task_pb.ListDeletedTasksRequest(
                page=int(page), per_page=int(per_page), search=search or '',
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'查询任务回收站失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='查询任务回收站失败',
        )

    def restore_tasks(self, task_ids):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_task_config_service_stub()
            resp = stub.RestoreTasks(task_pb.RestoreTasksRequest(
                task_ids=[int(i) for i in (task_ids or [])],
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'恢复任务失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='恢复任务失败',
        )

    def purge_tasks(self, task_ids):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_task_config_service_stub()
            resp = stub.PurgeTasks(task_pb.PurgeTasksRequest(
                task_ids=[int(i) for i in (task_ids or [])],
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'彻底删除任务失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='彻底删除任务失败',
        )

    def get_task_detail(self, task_id):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_task_config_service_stub()
            resp = stub.GetTaskDetail(task_pb.GetTaskDetailRequest(
                task_id=int(task_id),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取任务详情失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取任务详情失败',
        )

    def get_task_progress(self, task_id):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_task_config_service_stub()
            resp = stub.GetTaskProgress(task_pb.GetTaskProgressRequest(
                task_id=int(task_id),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取任务进度失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取任务进度失败',
        )

    def get_task_stats(self, task_id):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_task_config_service_stub()
            resp = stub.GetTaskStats(task_pb.GetTaskStatsRequest(
                task_id=int(task_id),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取任务统计失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取任务统计失败',
        )

    def get_case_detail(self, task_id, case_id):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_task_config_service_stub()
            resp = stub.GetCaseDetail(task_pb.GetCaseDetailRequest(
                task_id=int(task_id),
                case_id=str(case_id),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取用例详情失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取用例详情失败',
        )

    def get_case_results(self, task_id, case_id):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_task_config_service_stub()
            resp = stub.GetCaseResults(task_pb.GetCaseResultsRequest(
                task_id=int(task_id),
                case_id=str(case_id),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取用例结果失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取用例结果失败',
        )

    # ---- 生命周期操作 ----

    def start(self, task_id):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_task_config_service_stub()
            resp = stub.StartTaskLifecycle(task_pb.StartTaskLifecycleRequest(
                task_id=int(task_id),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'启动任务失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='启动任务失败',
        )

    def retry(self, task_id, data=None):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_task_config_service_stub()
            resp = stub.RetryTaskLifecycle(task_pb.RetryTaskLifecycleRequest(
                task_id=int(task_id),
                # INT-302：data JSON 承载按用例选择（case_ids/mode），缺省空串整任务语义
                data=json.dumps(data or {}, ensure_ascii=False, default=str) if data else '',
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'重试任务失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='重试任务失败',
        )

    def control(self, task_id, data):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_task_config_service_stub()
            resp = stub.ControlTaskLifecycle(task_pb.ControlTaskLifecycleRequest(
                task_id=int(task_id),
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'控制任务失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='控制任务失败',
        )

    def stop(self, task_id):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_task_config_service_stub()
            resp = stub.StopTaskLifecycle(task_pb.StopTaskLifecycleRequest(
                task_id=int(task_id),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'停止任务失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='停止任务失败',
        )

    def reextract(self, task_id, data):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_task_config_service_stub()
            resp = stub.RextractTaskLifecycle(task_pb.RextractTaskLifecycleRequest(
                task_id=int(task_id),
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'重新提取失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='重新提取失败',
        )


# Task 配置 CRUD 模块级单例
task_config_service = _TaskConfigProxy()


# ==================== TestCase 配置 CRUD 代理 ====================

class _TestCaseConfigProxy:
    """TestCase 配置 CRUD 代理：把方法调用转发到 gRPC TestCaseConfigService

    替代原 TestCaseCommandService/TestCaseQueryService 直接操作 DB 的方式，
    网关侧不再 import TestCase 模型和 get_db_session()，统一走 gRPC。
    所有方法返回 dict: {success, message, data, code}
    """

    def _resp(self, resp):
        """统一解析 TestCaseConfigResponse 为 dict"""
        data = json.loads(resp.data) if resp.data else None
        result = {'success': resp.success, 'message': resp.message, 'data': data}
        # 失败响应的业务码经 data JSON 透传，提升到顶层（同 Task 侧，INT-141 F2）
        if not resp.success and isinstance(data, dict) and isinstance(data.get('code'), int):
            result['code'] = data['code']
        return result

    @property
    def stub(self):
        """获取 TestCaseConfigService stub（供需要直接调 RPC 的场景使用）"""
        return get_testcase_config_service_stub()

    # ---- 写操作 ----

    def create(self, data):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_testcase_config_service_stub()
            resp = stub.CreateTestCaseConfig(task_pb.CreateTestCaseConfigRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'创建测试用例失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='创建测试用例失败',
        )

    def update(self, tc_id, data):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_testcase_config_service_stub()
            resp = stub.UpdateTestCaseConfig(task_pb.UpdateTestCaseConfigRequest(
                tc_id=str(tc_id),
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'更新测试用例失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='更新测试用例失败',
        )

    def delete(self, tc_id):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_testcase_config_service_stub()
            resp = stub.DeleteTestCaseConfig(task_pb.DeleteTestCaseConfigRequest(
                tc_id=str(tc_id),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'删除测试用例失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='删除测试用例失败',
        )

    def copy(self, tc_id):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_testcase_config_service_stub()
            resp = stub.CopyTestCaseConfig(task_pb.CopyTestCaseConfigRequest(
                tc_id=str(tc_id),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'复制测试用例失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='复制测试用例失败',
        )

    def batch_action(self, data):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_testcase_config_service_stub()
            resp = stub.BatchActionTestCases(task_pb.BatchActionTestCasesRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'批量操作失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='批量操作失败',
        )

    def update_ref_params(self, tc_id, round_number, data):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_testcase_config_service_stub()
            resp = stub.UpdateTestCaseRefParams(task_pb.UpdateTestCaseRefParamsRequest(
                tc_id=str(tc_id),
                round_number=int(round_number),
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'更新参考参数失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='更新参考参数失败',
        )

    # ---- 读操作 ----

    def list_testcases(self, page=1, per_page=10, keyword=None, tag=None,
                       group_id=None, algorithm_type=None, test_type=None,
                       view=None, include_deleted=False, dimension_id=None,
                       favorite=False, only_deleted=False):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_testcase_config_service_stub()
            resp = stub.ListTestCases(task_pb.ListTestCasesRequest(
                page=int(page),
                per_page=int(per_page),
                keyword=keyword or '',
                tag=tag or '',
                group_id=group_id or '',
                # INT-193：type/dimension_id proto 字段此前未接线（extra="ignore"
                # 在网关 schema 层静默丢弃），现贯通下推 task_service 过滤
                type=test_type or '',
                algorithm_type=algorithm_type or '',
                view=view or '',
                include_deleted=bool(include_deleted),
                dimension_id=int(dimension_id) if dimension_id else 0,
                favorite=bool(favorite),
                only_deleted=bool(only_deleted),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'查询测试用例列表失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='查询测试用例列表失败',
        )

    # ---- 收藏 / 回收站（INT-141）----

    def favorite(self, entity_type, entity_id):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_testcase_config_service_stub()
            resp = stub.FavoriteTestCase(task_pb.FavoriteEntityRequest(
                entity_type=str(entity_type),
                entity_id=str(entity_id),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'收藏失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='收藏失败',
        )

    def unfavorite(self, entity_type, entity_id):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_testcase_config_service_stub()
            resp = stub.UnfavoriteTestCase(task_pb.FavoriteEntityRequest(
                entity_type=str(entity_type),
                entity_id=str(entity_id),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'取消收藏失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='取消收藏失败',
        )

    def list_deleted_testcases(self, page=1, per_page=20, keyword=None):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_testcase_config_service_stub()
            resp = stub.ListDeletedTestCases(task_pb.ListDeletedTestCasesRequest(
                page=int(page), per_page=int(per_page), keyword=keyword or '',
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'查询用例回收站失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='查询用例回收站失败',
        )

    def restore_testcases(self, case_ids):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_testcase_config_service_stub()
            resp = stub.RestoreTestCases(task_pb.RestoreTestCasesRequest(
                case_ids=[str(i) for i in (case_ids or [])],
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'恢复用例失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='恢复用例失败',
        )

    def purge_testcases(self, case_ids):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_testcase_config_service_stub()
            resp = stub.PurgeTestCases(task_pb.PurgeTestCasesRequest(
                case_ids=[str(i) for i in (case_ids or [])],
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'彻底删除用例失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='彻底删除用例失败',
        )

    def get_testcase_detail(self, tc_id):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_testcase_config_service_stub()
            resp = stub.GetTestCaseDetail(task_pb.GetTestCaseDetailRequest(
                tc_id=str(tc_id),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取测试用例详情失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取测试用例详情失败',
        )

    def get_testcase_stats(self):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_testcase_config_service_stub()
            resp = stub.GetTestCaseStats(task_pb.GetTestCaseStatsRequest())
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取测试用例统计失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取测试用例统计失败',
        )

    def get_testcase_tags(self):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_testcase_config_service_stub()
            resp = stub.GetTestCaseTags(task_pb.GetTestCaseTagsRequest())
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取标签列表失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取标签列表失败',
        )

    def get_testcase_ref_params(self, tc_id, round_number):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_testcase_config_service_stub()
            resp = stub.GetTestCaseRefParams(task_pb.GetTestCaseRefParamsRequest(
                tc_id=str(tc_id),
                round_number=int(round_number),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取参考参数失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取参考参数失败',
        )

    def fetch_case_ids(self, data):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_testcase_config_service_stub()
            resp = stub.FetchCaseIds(task_pb.FetchCaseIdsRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'查询用例ID失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='查询用例ID失败',
        )


# TestCase 配置 CRUD 模块级单例
testcase_config_service = _TestCaseConfigProxy()
