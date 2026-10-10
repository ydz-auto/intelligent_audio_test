# -*- coding: utf-8 -*-
"""
api_test_service gRPC servicer 实现。

将 gRPC RPC 方法委托给 application 层：
- 测试任务方法（CreateAPITest/StartAPITest/StopAPITest/GetAPITestStatus）
  -> application 层 CQRS handler（create_api_test_handler / stop_api_test_handler / get_api_test_status_handler）
- API 配置 CRUD 方法
  -> application 层 api_crud_service（含完整序列化与连接测试逻辑）

约定：
- 复杂参数通过 JSON string 传递，方法内 json.loads 解析
- 返回结果通过 JSON string 封装到 data 字段
- 所有方法用 try/except 包裹，异常返回 success=False
"""

from shared.proto import api_test_service_pb2 as api_pb
from shared.proto import api_test_service_pb2_grpc as api_grpc
from shared.utils.grpc_json import loads as _loads, dumps as _dumps

from api_test_service.application.commands.api_test_commands import (
    CreateAPITestCommand,
    StartAPITestCommand,
    StopAPITestCommand,
)
from api_test_service.application.queries.api_test_queries import GetAPITestStatusQuery


class APITestServiceServicer(api_grpc.APITestServiceServicer):
    """API 测试服务 gRPC servicer，委托给 application 层"""

    def __init__(self):
        self._create_handler = None
        self._stop_handler = None
        self._start_handler = None
        self._status_handler = None
        self._crud_service = None

    @staticmethod
    def _bind_worker_context(context):
        """从入站 metadata 绑定 worker_instance_id（UC-1001 执行链路贯通）。

        本线程内（含亲和转发出站调用）可读；线程池执行路径由
        APITestService.start_task 以 copy_context 按用例传播。
        """
        from shared.infrastructure.worker_context import (
            set_worker_instance_id, worker_instance_id_from_context,
        )
        set_worker_instance_id(worker_instance_id_from_context(context))

    @property
    def create_handler(self):
        """application 层 — 创建/启动 API 测试命令处理器"""
        if self._create_handler is None:
            from api_test_service.application.handlers import create_api_test_handler
            self._create_handler = create_api_test_handler
        return self._create_handler

    @property
    def stop_handler(self):
        """application 层 — 停止 API 测试命令处理器"""
        if self._stop_handler is None:
            from api_test_service.application.handlers import stop_api_test_handler
            self._stop_handler = stop_api_test_handler
        return self._stop_handler

    @property
    def start_handler(self):
        """application 层 — 按路由决策启动 API 测试命令处理器（INT-71）"""
        if self._start_handler is None:
            from api_test_service.application.handlers import start_api_test_handler
            self._start_handler = start_api_test_handler
        return self._start_handler

    @property
    def status_handler(self):
        """application 层 — 查询 API 测试状态处理器"""
        if self._status_handler is None:
            from api_test_service.application.handlers import get_api_test_status_handler
            self._status_handler = get_api_test_status_handler
        return self._status_handler

    @property
    def crud_service(self):
        """application 层 — API 配置 CRUD 服务（含完整序列化与健康检查逻辑）

        注：此处使用 api_crud_service 而非 CQRS handler，因为 CRUD 接口需要
        返回完整 PO 字段（endpoints/vendor/meta 等），CQRS handler 仅返回聚合根
        精简字段，改用 handler 会破坏现有数据契约。
        """
        if self._crud_service is None:
            from api_test_service.application.api_crud_service import api_crud_service
            self._crud_service = api_crud_service
        return self._crud_service

    def CreateAPITest(self, request, context=None):
        """创建 API 测试任务（同时触发启动）"""
        try:
            self._bind_worker_context(context)
            task_id = request.task_id
            test_config = _loads(request.test_config, {})
            command = CreateAPITestCommand(
                task_id=task_id,
                case_ids=test_config.get('case_ids', []),
                api_ids=test_config.get('api_ids', []),
            )
            result = self.create_handler.handle(command)
            return api_pb.CreateAPITestResponse(
                success=result.get('success', True),
                message=result.get('message', 'ok'),
                data=_dumps(result),
            )
        except Exception as e:
            return api_pb.CreateAPITestResponse(success=False, message=str(e), data="")

    def StartAPITest(self, request, context=None):
        """启动 API 测试（执行域 P0 分发通道，INT-71）

        task_service 逐用例领取后经此 RPC 下发执行：case_ids 为精确
        TaskCase.id 集合；device_type/device_id 为调度侧路由决策，随命令
        传入执行链（按 device_type 路由 executor）。case_ids 为空时由
        api_test_service 自行从数据库按 pending/queued 状态读取。
        """
        try:
            self._bind_worker_context(context)
            command = StartAPITestCommand(
                task_id=request.task_id,
                case_ids=list(request.case_ids),
                device_type=request.device_type or '',
                device_id=request.device_id or '',
            )
            result = self.start_handler.handle(command)
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
            command = StopAPITestCommand(task_id=task_id)
            result = self.stop_handler.handle(command)
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
            query = GetAPITestStatusQuery(task_id=task_id)
            result = self.status_handler.handle(query)
            return api_pb.APITestStatusResponse(
                success=result.get('success', True),
                message=result.get('message', 'ok'),
                data=_dumps(result),
            )
        except Exception as e:
            return api_pb.APITestStatusResponse(success=False, message=str(e), data="")

    # ==================== API 配置 CRUD ====================

    def CreateAPIConfig(self, request, context=None):
        """创建 API 配置"""
        try:
            data = _loads(request.data, {})
            result = self.crud_service.create(data)
            return api_pb.CreateAPIConfigResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return api_pb.CreateAPIConfigResponse(success=False, message=str(e), data="")

    def UpdateAPIConfig(self, request, context=None):
        """更新 API 配置"""
        try:
            api_id = request.api_id
            data = _loads(request.data, {})
            result = self.crud_service.update(api_id, data)
            return api_pb.UpdateAPIConfigResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return api_pb.UpdateAPIConfigResponse(success=False, message=str(e), data="")

    def DeleteAPIConfig(self, request, context=None):
        """删除 API 配置（软删除）"""
        try:
            api_id = request.api_id
            result = self.crud_service.delete(api_id)
            return api_pb.DeleteAPIConfigResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return api_pb.DeleteAPIConfigResponse(success=False, message=str(e), data="")

    def ListAPIConfigs(self, request, context=None):
        """分页查询 API 列表"""
        try:
            result = self.crud_service.get_all(
                page=request.page or 1,
                per_page=request.per_page or 10,
                keyword=request.keyword or None,
                status=request.status or None,
                algorithm_type=request.algorithm_type or None,
            )
            return api_pb.ListAPIConfigsResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return api_pb.ListAPIConfigsResponse(success=False, message=str(e), data="")

    def GetAPIConfig(self, request, context=None):
        """查询单个 API 详情"""
        try:
            api_id = request.api_id
            result = self.crud_service.get_one(api_id)
            return api_pb.GetAPIConfigResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return api_pb.GetAPIConfigResponse(success=False, message=str(e), data="")

    def TestAPIConnection(self, request, context=None):
        """测试 API 连接（含 WebSocket/HTTP 健康检查）"""
        try:
            api_id = request.api_id
            result = self.crud_service.test_connection(api_id)
            return api_pb.TestAPIConnectionResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return api_pb.TestAPIConnectionResponse(success=False, message=str(e), data="")

    def StopAPITestConfig(self, request, context=None):
        """停止 API 测试连接"""
        try:
            api_id = request.api_id
            result = self.crud_service.stop_test(api_id)
            return api_pb.StopAPITestConfigResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return api_pb.StopAPITestConfigResponse(success=False, message=str(e), data="")


class ApiRmsSplConfigServiceServicer(api_grpc.ApiRmsSplConfigServiceServicer):
    """API RMS→SPL 映射配置 gRPC servicer（UC-0902），委托给 application 层"""

    def __init__(self):
        self._config_service = None

    @property
    def config_service(self):
        """application 层 — RMS→SPL 映射配置服务（写侧发事件 / 校准分布式锁互斥）"""
        if self._config_service is None:
            from api_test_service.application.api_rms_spl_config_service import (
                api_rms_spl_config_service,
            )
            self._config_service = api_rms_spl_config_service
        return self._config_service

    def CreateRmsSplMapping(self, request, context=None):
        try:
            data = _loads(request.data, {})
            result = self.config_service.create(data)
            return api_pb.CreateRmsSplMappingResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
                code=int(result.get('code') or 0),
            )
        except Exception as e:
            return api_pb.CreateRmsSplMappingResponse(success=False, message=str(e), data="")

    def UpdateRmsSplMapping(self, request, context=None):
        try:
            data = _loads(request.data, {})
            result = self.config_service.update(request.mapping_id, data)
            return api_pb.UpdateRmsSplMappingResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
                code=int(result.get('code') or 0),
            )
        except Exception as e:
            return api_pb.UpdateRmsSplMappingResponse(success=False, message=str(e), data="")

    def DeleteRmsSplMapping(self, request, context=None):
        try:
            result = self.config_service.delete(request.mapping_id)
            return api_pb.DeleteRmsSplMappingResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
                code=int(result.get('code') or 0),
            )
        except Exception as e:
            return api_pb.DeleteRmsSplMappingResponse(success=False, message=str(e), data="")

    def ListRmsSplMappings(self, request, context=None):
        try:
            result = self.config_service.get_all(
                page=request.page or 1,
                per_page=request.per_page or 10,
                api_id=request.api_id or None,
                calibration_status=request.calibration_status or None,
            )
            return api_pb.ListRmsSplMappingsResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
                code=int(result.get('code') or 0),
            )
        except Exception as e:
            return api_pb.ListRmsSplMappingsResponse(success=False, message=str(e), data="")

    def GetRmsSplMapping(self, request, context=None):
        try:
            result = self.config_service.get_one(request.mapping_id)
            return api_pb.GetRmsSplMappingResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
                code=int(result.get('code') or 0),
            )
        except Exception as e:
            return api_pb.GetRmsSplMappingResponse(success=False, message=str(e), data="")

    def GetRmsSplMappingsByApi(self, request, context=None):
        try:
            result = self.config_service.get_by_api(request.api_id)
            return api_pb.GetRmsSplMappingsByApiResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
                code=int(result.get('code') or 0),
            )
        except Exception as e:
            return api_pb.GetRmsSplMappingsByApiResponse(success=False, message=str(e), data="")

    def CalibrateRmsSplMapping(self, request, context=None):
        try:
            calibration_data = _loads(request.calibration_data, {})
            result = self.config_service.calibrate(request.mapping_id, calibration_data)
            return api_pb.CalibrateRmsSplMappingResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
                code=int(result.get('code') or 0),
            )
        except Exception as e:
            return api_pb.CalibrateRmsSplMappingResponse(success=False, message=str(e), data="")

    def SetDefaultRmsSplMapping(self, request, context=None):
        try:
            result = self.config_service.set_default(
                request.api_id,
                request.mapping_id or None,
            )
            return api_pb.SetDefaultRmsSplMappingResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
                code=int(result.get('code') or 0),
            )
        except Exception as e:
            return api_pb.SetDefaultRmsSplMappingResponse(success=False, message=str(e), data="")
