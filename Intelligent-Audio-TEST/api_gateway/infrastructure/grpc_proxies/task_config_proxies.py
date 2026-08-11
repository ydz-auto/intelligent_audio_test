"""任务/用例/标签/算法配置代理：_TaskConfigProxy、_TestCaseConfigProxy、_TagConfigProxy、_AlgorithmConfigProxy 及相关单例。"""
import json

from shared.clients.grpc_clients import (
    get_task_config_service_stub,
    get_testcase_config_service_stub,
    get_tag_config_service_stub,
    get_algorithm_config_service_stub,
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
        return {
            'success': resp.success,
            'message': resp.message,
            'data': json.loads(resp.data) if resp.data else None,
        }

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

    def list_tasks(self, page=1, per_page=10, status=None, task_type=None,
                   algorithm_type=None, search=None, start_date=None, end_date=None):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_task_config_service_stub()
            resp = stub.ListTasks(task_pb.ListTasksRequest(
                page=int(page),
                per_page=int(per_page),
                status=status or '',
                type=task_type or '',
                algorithm_type=algorithm_type or '',
                search=search or '',
                start_date=start_date or '',
                end_date=end_date or '',
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'查询任务列表失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='查询任务列表失败',
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
                case_id=int(case_id),
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
                case_id=int(case_id),
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

    def retry(self, task_id):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_task_config_service_stub()
            resp = stub.RetryTaskLifecycle(task_pb.RetryTaskLifecycleRequest(
                task_id=int(task_id),
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
        return {
            'success': resp.success,
            'message': resp.message,
            'data': json.loads(resp.data) if resp.data else None,
        }

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
                       group_id=None, test_type=None, algorithm_type=None,
                       view=None, include_deleted=False):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_testcase_config_service_stub()
            resp = stub.ListTestCases(task_pb.ListTestCasesRequest(
                page=int(page),
                per_page=int(per_page),
                keyword=keyword or '',
                tag=tag or '',
                group_id=group_id or '',
                type=test_type or '',
                algorithm_type=algorithm_type or '',
                view=view or '',
                include_deleted=bool(include_deleted),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'查询测试用例列表失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='查询测试用例列表失败',
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


# TestCase 配置 CRUD 模块级单例
testcase_config_service = _TestCaseConfigProxy()


class _TagConfigProxy:
    """标签及标签分类 CRUD 代理：把方法调用转发到 gRPC TagConfigService

    所有方法返回 dict: {success, message, data, code}
    """

    def _resp(self, resp):
        """统一解析 TagConfigResponse 为 dict"""
        return {
            'success': resp.success,
            'message': resp.message,
            'data': json.loads(resp.data) if resp.data else None,
        }

    # ---- TagCategory 写操作 ----

    def create_category(self, data):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_tag_config_service_stub()
            resp = stub.CreateTagCategory(task_pb.CreateTagCategoryRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'创建标签分类失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='创建标签分类失败',
        )

    def update_category(self, category_id, data):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_tag_config_service_stub()
            resp = stub.UpdateTagCategory(task_pb.UpdateTagCategoryRequest(
                category_id=int(category_id),
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'更新标签分类失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='更新标签分类失败',
        )

    def delete_category(self, category_id):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_tag_config_service_stub()
            resp = stub.DeleteTagCategory(task_pb.DeleteTagCategoryRequest(
                category_id=int(category_id),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'删除标签分类失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='删除标签分类失败',
        )

    # ---- Tag 写操作 ----

    def create_tag(self, data):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_tag_config_service_stub()
            resp = stub.CreateTag(task_pb.CreateTagRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'创建标签失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='创建标签失败',
        )

    def update_tag(self, tag_id, data):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_tag_config_service_stub()
            resp = stub.UpdateTag(task_pb.UpdateTagRequest(
                tag_id=int(tag_id),
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'更新标签失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='更新标签失败',
        )

    def delete_tag(self, tag_id):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_tag_config_service_stub()
            resp = stub.DeleteTag(task_pb.DeleteTagRequest(
                tag_id=int(tag_id),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'删除标签失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='删除标签失败',
        )

    def batch_update_category(self, data):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_tag_config_service_stub()
            resp = stub.BatchUpdateTagCategory(task_pb.BatchUpdateTagCategoryRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'批量更新标签分类失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='批量更新标签分类失败',
        )

    # ---- 读操作 ----

    def list_categories(self, page=1, per_page=20, keyword=None):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_tag_config_service_stub()
            resp = stub.ListTagCategories(task_pb.ListTagCategoriesRequest(
                page=int(page),
                per_page=int(per_page),
                keyword=keyword or '',
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'查询标签分类列表失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='查询标签分类列表失败',
        )

    def get_category(self, category_id):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_tag_config_service_stub()
            resp = stub.GetTagCategory(task_pb.GetTagCategoryRequest(
                category_id=int(category_id),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取标签分类失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取标签分类失败',
        )

    def list_tags(self, page=1, per_page=20, category_id=None, keyword=None):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_tag_config_service_stub()
            resp = stub.ListTags(task_pb.ListTagsRequest(
                page=int(page),
                per_page=int(per_page),
                category_id=int(category_id) if category_id else 0,
                keyword=keyword or '',
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'查询标签列表失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='查询标签列表失败',
        )

    def list_tag_names(self, page=1, per_page=100, keyword=None):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_tag_config_service_stub()
            resp = stub.ListTagNames(task_pb.ListTagNamesRequest(
                page=int(page),
                per_page=int(per_page),
                keyword=keyword or '',
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'查询标签名称列表失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='查询标签名称列表失败',
        )

    def get_tag(self, tag_id):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_tag_config_service_stub()
            resp = stub.GetTag(task_pb.GetTagRequest(
                tag_id=int(tag_id),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取标签失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取标签失败',
        )

    def get_tags_by_category(self):
        from shared.proto import task_service_pb2 as task_pb

        def _call():
            stub = get_tag_config_service_stub()
            resp = stub.GetTagsByCategory(task_pb.GetTagsByCategoryRequest())
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取按分类分组的标签失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取按分类分组的标签失败',
        )


# 标签配置 CRUD 模块级单例
tag_config_service = _TagConfigProxy()


class _AlgorithmConfigProxy:
    """算法定义及关联配置 CRUD 代理"""

    def _resp(self, resp):
        return {
            'success': resp.success,
            'message': resp.message,
            'data': json.loads(resp.data) if resp.data else None,
        }

    # ---- 算法定义 写操作 ----

    def create_algorithm(self, data):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.CreateAlgorithm(task_pb.CreateAlgorithmRequest(data=json.dumps(data, ensure_ascii=False, default=str))))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'创建算法定义失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='创建算法定义失败',
        )

    def update_algorithm(self, algo_type, data):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.UpdateAlgorithm(task_pb.UpdateAlgorithmRequest(algo_type=algo_type, data=json.dumps(data, ensure_ascii=False, default=str))))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'更新算法定义失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='更新算法定义失败',
        )

    def delete_algorithm(self, algo_type):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.DeleteAlgorithm(task_pb.DeleteAlgorithmRequest(algo_type=algo_type)))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'删除算法定义失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='删除算法定义失败',
        )

    # ---- 算法分组 写操作 ----

    def create_group(self, data):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.CreateAlgorithmGroup(task_pb.CreateAlgorithmGroupRequest(data=json.dumps(data, ensure_ascii=False, default=str))))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'创建算法分组失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='创建算法分组失败',
        )

    def update_group(self, group_id, data):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.UpdateAlgorithmGroup(task_pb.UpdateAlgorithmGroupRequest(group_id=group_id, data=json.dumps(data, ensure_ascii=False, default=str))))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'更新算法分组失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='更新算法分组失败',
        )

    def delete_group(self, group_id):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.DeleteAlgorithmGroup(task_pb.DeleteAlgorithmGroupRequest(group_id=group_id)))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'删除算法分组失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='删除算法分组失败',
        )

    # ---- 参数(device/api) 写操作 ----

    def create_param(self, data):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.CreateParam(task_pb.CreateParamRequest(data=json.dumps(data, ensure_ascii=False, default=str))))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'创建参数失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='创建参数失败',
        )

    def update_param(self, param_id, data):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.UpdateParam(task_pb.UpdateParamRequest(param_id=param_id, data=json.dumps(data, ensure_ascii=False, default=str))))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'更新参数失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='更新参数失败',
        )

    def delete_param(self, param_id):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.DeleteParam(task_pb.DeleteParamRequest(param_id=param_id)))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'删除参数失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='删除参数失败',
        )

    # ---- 用例专属参数 写操作 ----

    def create_case_param(self, data):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.CreateCaseParam(task_pb.CreateCaseParamRequest(data=json.dumps(data, ensure_ascii=False, default=str))))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'创建用例参数失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='创建用例参数失败',
        )

    def update_case_param(self, param_id, data):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.UpdateCaseParam(task_pb.UpdateCaseParamRequest(param_id=param_id, data=json.dumps(data, ensure_ascii=False, default=str))))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'更新用例参数失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='更新用例参数失败',
        )

    def delete_case_param(self, param_id):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.DeleteCaseParam(task_pb.DeleteCaseParamRequest(param_id=param_id)))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'删除用例参数失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='删除用例参数失败',
        )

    # ---- 参考参数 写操作 ----

    def create_reference_param(self, data):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.CreateReferenceParam(task_pb.CreateReferenceParamRequest(data=json.dumps(data, ensure_ascii=False, default=str))))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'创建参考参数失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='创建参考参数失败',
        )

    def update_reference_param(self, param_id, data):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.UpdateReferenceParam(task_pb.UpdateReferenceParamRequest(param_id=param_id, data=json.dumps(data, ensure_ascii=False, default=str))))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'更新参考参数失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='更新参考参数失败',
        )

    def delete_reference_param(self, param_id):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.DeleteReferenceParam(task_pb.DeleteReferenceParamRequest(param_id=param_id)))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'删除参考参数失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='删除参考参数失败',
        )

    # ---- 参数映射 写操作 ----

    def create_mapping(self, data):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.CreateMapping(task_pb.CreateMappingRequest(data=json.dumps(data, ensure_ascii=False, default=str))))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'创建映射失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='创建映射失败',
        )

    def update_mapping(self, mapping_id, data):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.UpdateMapping(task_pb.UpdateMappingRequest(mapping_id=mapping_id, data=json.dumps(data, ensure_ascii=False, default=str))))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'更新映射失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='更新映射失败',
        )

    def delete_mapping(self, mapping_id):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.DeleteMapping(task_pb.DeleteMappingRequest(mapping_id=mapping_id)))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'删除映射失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='删除映射失败',
        )

    # ---- 维度关联 写操作 ----

    def associate_dimensions(self, algo_type, data):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.AssociateDimensions(task_pb.AssociateDimensionsRequest(algo_type=algo_type, data=json.dumps(data, ensure_ascii=False, default=str))))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'关联维度失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='关联维度失败',
        )

    def create_dimension_relation(self, data):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.CreateDimensionRelation(task_pb.CreateDimensionRelationRequest(data=json.dumps(data, ensure_ascii=False, default=str))))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'创建维度关联失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='创建维度关联失败',
        )

    def update_dimension_relation(self, relation_id, data):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.UpdateDimensionRelation(task_pb.UpdateDimensionRelationRequest(relation_id=relation_id, data=json.dumps(data, ensure_ascii=False, default=str))))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'更新维度关联失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='更新维度关联失败',
        )

    def delete_dimension_relation(self, relation_id):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.DeleteDimensionRelation(task_pb.DeleteDimensionRelationRequest(relation_id=relation_id)))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'删除维度关联失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='删除维度关联失败',
        )

    # ---- 批量操作 ----

    def import_algorithms(self, data):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.ImportAlgorithms(task_pb.ImportAlgorithmsRequest(data=json.dumps(data, ensure_ascii=False, default=str))))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'导入算法失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='导入算法失败',
        )

    def bulk_delete(self, data):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.BulkDeleteAlgorithms(task_pb.BulkDeleteAlgorithmsRequest(data=json.dumps(data, ensure_ascii=False, default=str))))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'批量删除算法失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='批量删除算法失败',
        )

    def extract_params(self, data):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.ExtractParams(task_pb.ExtractParamsRequest(data=json.dumps(data, ensure_ascii=False, default=str))))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'提取参数失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='提取参数失败',
        )

    def reload_config(self):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.ReloadAlgorithmConfig(task_pb.ReloadAlgorithmConfigRequest()))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'重载配置失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='重载配置失败',
        )

    # ---- 读操作 ----

    def list_algorithms(self, status=None, group_id=None):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.ListAlgorithms(task_pb.ListAlgorithmsRequest(status=status or '', group_id=group_id or 0)))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取算法列表失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取算法列表失败',
        )

    def get_algorithm(self, algo_type):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.GetAlgorithm(task_pb.GetAlgorithmRequest(algo_type=algo_type)))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取算法详情失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取算法详情失败',
        )

    def get_algorithm_options(self):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.GetAlgorithmOptions(task_pb.GetAlgorithmOptionsRequest()))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取算法选项失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取算法选项失败',
        )

    def list_groups(self):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.ListAlgorithmGroups(task_pb.ListAlgorithmGroupsRequest()))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取算法分组列表失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取算法分组列表失败',
        )

    def get_group(self, group_id):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.GetAlgorithmGroup(task_pb.GetAlgorithmGroupRequest(group_id=group_id)))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取算法分组详情失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取算法分组详情失败',
        )

    def list_params(self, algorithm_type=None, param_type=None):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.ListParams(task_pb.ListParamsRequest(algorithm_type=algorithm_type or '', param_type=param_type or '')))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取参数列表失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取参数列表失败',
        )

    def get_param(self, param_id):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.GetParam(task_pb.GetParamRequest(param_id=param_id)))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取参数详情失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取参数详情失败',
        )

    def list_case_params(self, algorithm_type=None, scope=None):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.ListCaseParams(task_pb.ListCaseParamsRequest(algorithm_type=algorithm_type or '', scope=scope or '')))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取用例参数列表失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取用例参数列表失败',
        )

    def get_case_param(self, param_id):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.GetCaseParam(task_pb.GetCaseParamRequest(param_id=param_id)))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取用例参数详情失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取用例参数详情失败',
        )

    def list_reference_params(self, algorithm_type=None):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.ListReferenceParams(task_pb.ListReferenceParamsRequest(algorithm_type=algorithm_type or '')))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取参考参数列表失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取参考参数列表失败',
        )

    def list_mappings(self, algorithm_type=None, source_type=None, dimension_id=None):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.ListMappings(task_pb.ListMappingsRequest(algorithm_type=algorithm_type or '', source_type=source_type or '', dimension_id=dimension_id or 0)))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取映射列表失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取映射列表失败',
        )

    def get_form_schema(self, algo_type):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.GetFormSchema(task_pb.GetFormSchemaRequest(algo_type=algo_type)))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取表单Schema失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取表单Schema失败',
        )

    def get_algorithm_dimensions(self, algo_type):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.GetAlgorithmDimensions(task_pb.GetAlgorithmDimensionsRequest(algo_type=algo_type)))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取算法维度失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取算法维度失败',
        )

    def get_dimension_params(self, dimension_id):
        def _call():
            stub = get_algorithm_config_service_stub()
            return self._resp(stub.GetDimensionParams(task_pb.GetDimensionParamsRequest(dimension_id=dimension_id)))
        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取维度参数失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取维度参数失败',
        )


# 算法配置 CRUD 模块级单例
algorithm_config_service = _AlgorithmConfigProxy()
