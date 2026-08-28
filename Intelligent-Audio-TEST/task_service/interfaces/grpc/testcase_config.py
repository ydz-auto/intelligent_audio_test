# -*- coding: utf-8 -*-
from shared.proto import task_service_pb2 as task_pb
from shared.proto import task_service_pb2_grpc as task_grpc
from shared.utils.grpc_json import loads as _loads, dumps as _dumps


class TestCaseConfigServiceServicer(task_grpc.TestCaseConfigServiceServicer):
    """测试用例配置 CRUD servicer，委托给 TaskCommandHandler / TaskQueryHandler。

    写操作（create/update/delete/copy/batch_action/update_ref_params）通过
    CQRS Command 委托 task_command_handler；读操作通过 CQRS Query 委托
    task_query_handler。handler 内部过渡期仍委托 testcase_crud_service。
    """

    def __init__(self):
        self._cmd = None
        self._qry = None

    @property
    def cmd(self):
        """延迟加载命令处理器（CQRS 写侧入口）。"""
        if self._cmd is None:
            from task_service.application.handlers import task_command_handler
            self._cmd = task_command_handler
        return self._cmd

    @property
    def qry(self):
        """延迟加载查询处理器（CQRS 读侧入口）。"""
        if self._qry is None:
            from task_service.application.handlers import task_query_handler
            self._qry = task_query_handler
        return self._qry

    @staticmethod
    def _resp(result):
        """统一包装返回结果为 TestCaseConfigResponse"""
        return task_pb.TestCaseConfigResponse(
            success=result.get('success', False),
            message=result.get('message', ''),
            data=_dumps(result.get('data')) if result.get('data') is not None else "",
        )

    # ---- 写操作 ----

    def CreateTestCaseConfig(self, request, context=None):
        try:
            data = _loads(request.data, {})
            from task_service.application.commands.task_commands import CreateTestCaseCommand
            return self._resp(self.cmd.handle_create_testcase(CreateTestCaseCommand(data=data)))
        except Exception as e:
            return task_pb.TestCaseConfigResponse(success=False, message=str(e), data="")

    def UpdateTestCaseConfig(self, request, context=None):
        try:
            data = _loads(request.data, {})
            from task_service.application.commands.task_commands import UpdateTestCaseCommand
            return self._resp(self.cmd.handle_update_testcase(
                UpdateTestCaseCommand(tc_id=request.tc_id, data=data)
            ))
        except Exception as e:
            return task_pb.TestCaseConfigResponse(success=False, message=str(e), data="")

    def DeleteTestCaseConfig(self, request, context=None):
        try:
            from task_service.application.commands.task_commands import DeleteTestCaseCommand
            return self._resp(self.cmd.handle_delete_testcase(DeleteTestCaseCommand(tc_id=request.tc_id)))
        except Exception as e:
            return task_pb.TestCaseConfigResponse(success=False, message=str(e), data="")

    def CopyTestCaseConfig(self, request, context=None):
        try:
            from task_service.application.commands.task_commands import CopyTestCaseCommand
            return self._resp(self.cmd.handle_copy_testcase(CopyTestCaseCommand(tc_id=request.tc_id)))
        except Exception as e:
            return task_pb.TestCaseConfigResponse(success=False, message=str(e), data="")

    def BatchActionTestCases(self, request, context=None):
        try:
            data = _loads(request.data, {})
            from task_service.application.commands.task_commands import BatchActionTestCaseCommand
            return self._resp(self.cmd.handle_batch_action_testcase(BatchActionTestCaseCommand(data=data)))
        except Exception as e:
            return task_pb.TestCaseConfigResponse(success=False, message=str(e), data="")

    def UpdateTestCaseRefParams(self, request, context=None):
        try:
            data = _loads(request.data, {})
            from task_service.application.commands.task_commands import UpdateTestCaseRefParamsCommand
            return self._resp(self.cmd.handle_update_testcase_ref_params(
                UpdateTestCaseRefParamsCommand(tc_id=request.tc_id, round_number=request.round_number, data=data)
            ))
        except Exception as e:
            return task_pb.TestCaseConfigResponse(success=False, message=str(e), data="")

    # ---- 读操作 ----

    def ListTestCases(self, request, context=None):
        try:
            from task_service.application.queries.task_queries import ListTestCasesQuery
            query = ListTestCasesQuery(
                page=request.page,
                per_page=request.per_page,
                keyword=request.keyword or None,
                tag=request.tag or None,
                group_id=request.group_id or None,
                test_type=request.type or None,
                algorithm_type=request.algorithm_type or None,
                view=request.view or None,
                include_deleted=request.include_deleted,
            )
            return self._resp(self.qry.handle_list_testcases(query))
        except Exception as e:
            return task_pb.TestCaseConfigResponse(success=False, message=str(e), data="")

    def GetTestCaseDetail(self, request, context=None):
        try:
            from task_service.application.queries.task_queries import GetTestCaseDetailQuery
            return self._resp(self.qry.handle_get_testcase_detail(GetTestCaseDetailQuery(tc_id=request.tc_id)))
        except Exception as e:
            return task_pb.TestCaseConfigResponse(success=False, message=str(e), data="")

    def GetTestCaseStats(self, request, context=None):
        try:
            from task_service.application.queries.task_queries import GetTestCaseStatsQuery
            return self._resp(self.qry.handle_get_testcase_stats(GetTestCaseStatsQuery()))
        except Exception as e:
            return task_pb.TestCaseConfigResponse(success=False, message=str(e), data="")

    def GetTestCaseTags(self, request, context=None):
        try:
            from task_service.application.queries.task_queries import GetTestCaseTagsQuery
            return self._resp(self.qry.handle_get_testcase_tags(GetTestCaseTagsQuery()))
        except Exception as e:
            return task_pb.TestCaseConfigResponse(success=False, message=str(e), data="")

    def GetTestCaseRefParams(self, request, context=None):
        try:
            from task_service.application.queries.task_queries import GetTestCaseRefParamsQuery
            return self._resp(self.qry.handle_get_testcase_ref_params(
                GetTestCaseRefParamsQuery(tc_id=request.tc_id, round_number=request.round_number)
            ))
        except Exception as e:
            return task_pb.TestCaseConfigResponse(success=False, message=str(e), data="")

    def FetchCaseIds(self, request, context=None):
        try:
            data = _loads(request.data, {})
            from task_service.application.queries.task_queries import FetchCaseIdsQuery
            return self._resp(self.qry.handle_fetch_case_ids(FetchCaseIdsQuery(data=data)))
        except Exception as e:
            return task_pb.TestCaseConfigResponse(success=False, message=str(e), data="")
