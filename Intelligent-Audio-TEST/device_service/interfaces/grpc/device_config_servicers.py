# -*- coding: utf-8 -*-
"""设备配置 CRUD gRPC servicer（从 servicers.py 拆分，P4-4）。

DeviceConfigServiceServicer：委托给 DeviceCommandService / DeviceQueryService

按 CQRS 拆分：
- 写操作（create/update/delete/scan/test/stop_test/health_check）-> DeviceCommandService
- 读操作（get_all/get_one/get_statuses/get_driver_keywords/get_available_serials）-> DeviceQueryService
"""
from shared.proto import device_service_pb2 as e2e_pb
from shared.proto import device_service_pb2_grpc as e2e_grpc
from shared.utils.grpc_json import loads as _loads, dumps as _dumps


class DeviceConfigServiceServicer(e2e_grpc.DeviceConfigServiceServicer):
    """设备配置 CRUD 服务 gRPC servicer，委托给 DeviceCommandService / DeviceQueryService"""

    def __init__(self):
        self._command = None
        self._query = None

    @property
    def command(self):
        if self._command is None:
            from device_service.application.commands.device_command_service import device_command_service
            self._command = device_command_service
        return self._command

    @property
    def query(self):
        if self._query is None:
            from device_service.application.queries.device_query_service import device_query_service
            self._query = device_query_service
        return self._query

    def CreateDevice(self, request, context=None):
        try:
            data = _loads(request.data, {})
            result = self.command.create(data)
            return e2e_pb.CreateDeviceResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.CreateDeviceResponse(success=False, message=str(e), data="")

    def UpdateDevice(self, request, context=None):
        try:
            data = _loads(request.data, {})
            result = self.command.update(request.device_id, data)
            return e2e_pb.UpdateDeviceResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.UpdateDeviceResponse(success=False, message=str(e), data="")

    def DeleteDevice(self, request, context=None):
        try:
            result = self.command.delete(request.device_id)
            return e2e_pb.DeleteDeviceResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.DeleteDeviceResponse(success=False, message=str(e), data="")

    def ListDevices(self, request, context=None):
        try:
            result = self.query.get_all(
                page=request.page or 1,
                per_page=request.per_page or 10,
                keyword=request.keyword or None,
                status=request.status or None,
                device_type=request.device_type or None,
                algorithm_type=request.algorithm_type or None,
            )
            return e2e_pb.ListDevicesResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.ListDevicesResponse(success=False, message=str(e), data="")

    def GetDevice(self, request, context=None):
        try:
            result = self.query.get_one(request.device_id)
            return e2e_pb.GetDeviceResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.GetDeviceResponse(success=False, message=str(e), data="")

    def GetDeviceStatuses(self, request, context=None):
        try:
            data = _loads(request.data, {})
            result = self.query.get_statuses(data.get('ids'))
            return e2e_pb.GetDeviceStatusesResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.GetDeviceStatusesResponse(success=False, message=str(e), data="")

    def ScanPhysicalDevices(self, request, context=None):
        try:
            result = self.command.scan()
            return e2e_pb.ScanPhysicalDevicesResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.ScanPhysicalDevicesResponse(success=False, message=str(e), data="")

    def TestDevice(self, request, context=None):
        try:
            result = self.command.test(request.device_id)
            return e2e_pb.TestDeviceResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.TestDeviceResponse(success=False, message=str(e), data="")

    def StopDeviceTest(self, request, context=None):
        try:
            result = self.command.stop_test(request.device_id)
            return e2e_pb.StopDeviceTestResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.StopDeviceTestResponse(success=False, message=str(e), data="")

    def GetDriverKeywords(self, request, context=None):
        try:
            result = self.query.get_driver_keywords()
            return e2e_pb.GetDriverKeywordsResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.GetDriverKeywordsResponse(success=False, message=str(e), data="")

    def HealthCheckDevices(self, request, context=None):
        try:
            data = _loads(request.data, {})
            result = self.command.health_check(data.get('device_ids'))
            return e2e_pb.HealthCheckDevicesResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.HealthCheckDevicesResponse(success=False, message=str(e), data="")

    def GetAvailableSerials(self, request, context=None):
        try:
            result = self.query.get_available_serials()
            return e2e_pb.GetAvailableSerialsResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.GetAvailableSerialsResponse(success=False, message=str(e), data="")
