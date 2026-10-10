# -*- coding: utf-8 -*-
"""PublishedTaskConfigService servicer — 已发布任务配置 CRUD（任务发布功能）

委托 task_service.application.services.published_task_service 完成业务逻辑，
本模块仅做 protocol 适配（gRPC Request → dict → service → TaskConfigResponse）。
"""
import logging

from shared.proto import task_service_pb2 as task_pb
from shared.proto import task_service_pb2_grpc as task_grpc
from shared.utils.grpc_json import loads as _loads, dumps as _dumps

from task_service.application.services.published_task_service import published_task_service

logger = logging.getLogger(__name__)


class PublishedTaskConfigServiceServicer(task_grpc.PublishedTaskConfigServiceServicer):
    """已发布任务配置 CRUD servicer。"""

    @staticmethod
    def _resp(result) -> task_pb.TaskConfigResponse:
        """统一包装应用服务返回结果为 TaskConfigResponse"""
        return task_pb.TaskConfigResponse(
            success=result.get('success', False),
            message=result.get('message', ''),
            data=_dumps(result.get('data')) if result.get('data') is not None else "",
        )

    # ---- 写操作 ----

    def PublishTask(self, request, context=None):
        try:
            data = _loads(request.data, {})
            return self._resp(published_task_service.publish(data))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    def ExecutePublishedTask(self, request, context=None):
        try:
            operator = request.operator_user_id or None
            return self._resp(published_task_service.execute(request.published_task_id, operator_user_id=operator))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    def CreatePublishedTaskVersion(self, request, context=None):
        try:
            data = _loads(request.data, {})
            return self._resp(published_task_service.create_version(request.published_task_id, data))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    def ArchivePublishedTask(self, request, context=None):
        try:
            operator = request.operator_user_id or None
            return self._resp(published_task_service.archive(request.published_task_id, operator_user_id=operator))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    def RenamePublishedTask(self, request, context=None):
        try:
            data = _loads(request.data, {})
            return self._resp(published_task_service.update_name(request.published_task_id, data))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    # ---- 读操作 ----

    def ListPublishedTasks(self, request, context=None):
        try:
            return self._resp(published_task_service.get_list(
                page=request.page or 1,
                per_page=request.per_page or 10,
                status=request.status or '',
                keyword=request.keyword or '',
                benchmark=request.benchmark or '',
                start_date=request.start_date or '',
                end_date=request.end_date or '',
            ))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    def GetPublishedTaskDetail(self, request, context=None):
        try:
            return self._resp(published_task_service.get_detail(request.published_task_id))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")
