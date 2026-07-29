# -*- coding: utf-8 -*-
"""
api_test_service gRPC servicer 实现。

将 gRPC RPC 方法委托给已有业务类：
- APITestServiceServicer -> api_test_service

约定：
- 复杂参数通过 JSON string 传递，方法内 json.loads 解析
- 返回结果通过 JSON string 封装到 data 字段
- 所有方法用 try/except 包裹，异常返回 success=False
"""

import json

from shared.proto import api_test_service_pb2 as api_pb
from shared.proto import api_test_service_pb2_grpc as api_grpc
from shared.utils.grpc_json import loads as _loads, dumps as _dumps


class APITestServiceServicer(api_grpc.APITestServiceServicer):
    """API 测试服务 gRPC servicer，委托给 api_test_service"""

    def __init__(self):
        self._service = None

    @property
    def service(self):
        if self._service is None:
            from api_test_service.core.api_test_service import api_test_service
            self._service = api_test_service
        return self._service

    def CreateAPITest(self, request, context=None):
        """创建 API 测试任务（同时触发启动）"""
        try:
            task_id = request.task_id
            test_config = _loads(request.test_config, {})
            result = self.service.start_task(
                task_id,
                test_config.get('case_ids', []),
                test_config.get('api_ids', []),
            )
            return api_pb.CreateAPITestResponse(
                success=result.get('success', True),
                message=result.get('message', 'ok'),
                data=_dumps(result),
            )
        except Exception as e:
            return api_pb.CreateAPITestResponse(success=False, message=str(e), data="")

    def StartAPITest(self, request, context=None):
        """启动 API 测试

        task_service 调用此方法将 API 用例执行下沉到 api_test_service。
        不传 case_ids 时，由 api_test_service 自行从数据库按 pending 状态读取。
        """
        try:
            task_id = request.task_id
            result = self.service.start_task(task_id, [], [])
            return api_pb.StartAPITestResponse(
                success=result.get('success', True),
                message=result.get('message', 'ok'),
                data=_dumps(result),
            )
        except Exception as e:
            return api_pb.StartAPITestResponse(success=False, message=str(e), data="")

    def StopAPITest(self, request, context=None):
        """停止 API 测试"""
        try:
            task_id = request.task_id
            result = self.service.stop_task(task_id)
            return api_pb.StopAPITestResponse(
                success=result.get('success', True),
                message=result.get('message', 'ok'),
                data=_dumps(result),
            )
        except Exception as e:
            return api_pb.StopAPITestResponse(success=False, message=str(e), data="")

    def GetAPITestStatus(self, request, context=None):
        """获取 API 测试状态"""
        try:
            task_id = request.task_id
            result = self.service.get_task_status(task_id)
            return api_pb.APITestStatusResponse(
                success=result.get('success', True),
                message=result.get('message', 'ok'),
                data=_dumps(result),
            )
        except Exception as e:
            return api_pb.APITestStatusResponse(success=False, message=str(e), data="")
