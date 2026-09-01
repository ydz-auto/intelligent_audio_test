# -*- coding: utf-8 -*-
"""SPL 映射配置 gRPC servicer（从 servicers.py 拆分，P4-4）。

SPLConfigServiceServicer：委托给 SPLCommandService（写）/ SPLQueryService（读）
"""
from shared.proto import device_service_pb2 as e2e_pb
from shared.proto import device_service_pb2_grpc as e2e_grpc
from shared.utils.grpc_json import loads as _loads, dumps as _dumps


class SPLConfigServiceServicer(e2e_grpc.SPLConfigServiceServicer):
    """SPL 映射 CRUD 服务 gRPC servicer，委托给 SPLCommandService / SPLQueryService"""

    def __init__(self):
        self._command = None
        self._query = None

    @property
    def command(self):
        if self._command is None:
            from device_service.application.commands.spl_command_service import spl_command_service
            self._command = spl_command_service
        return self._command

    @property
    def query(self):
        if self._query is None:
            from device_service.application.queries.spl_query_service import spl_query_service
            self._query = spl_query_service
        return self._query

    def CreateSPLMapping(self, request, context=None):
        try:
            data = _loads(request.data, {})
            result = self.command.create(data)
            return e2e_pb.CreateSPLMappingResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.CreateSPLMappingResponse(success=False, message=str(e), data="")

    def UpdateSPLMapping(self, request, context=None):
        try:
            data = _loads(request.data, {})
            result = self.command.update(request.mapping_id, data)
            return e2e_pb.UpdateSPLMappingResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.UpdateSPLMappingResponse(success=False, message=str(e), data="")

    def DeleteSPLMapping(self, request, context=None):
        try:
            result = self.command.delete(request.mapping_id)
            return e2e_pb.DeleteSPLMappingResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.DeleteSPLMappingResponse(success=False, message=str(e), data="")

    def ListSPLMappings(self, request, context=None):
        try:
            result = self.query.get_all(
                page=request.page or 1,
                per_page=request.per_page or 10,
                keyword=request.keyword or None,
                calibration_status=request.calibration_status or None,
                device_id=request.device_id or None,
            )
            return e2e_pb.ListSPLMappingsResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.ListSPLMappingsResponse(success=False, message=str(e), data="")

    def GetSPLMapping(self, request, context=None):
        try:
            result = self.query.get_one(request.mapping_id)
            return e2e_pb.GetSPLMappingResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.GetSPLMappingResponse(success=False, message=str(e), data="")

    def GetSPLHistory(self, request, context=None):
        try:
            result = self.query.get_history(request.mapping_id)
            return e2e_pb.GetSPLHistoryResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.GetSPLHistoryResponse(success=False, message=str(e), data="")

    def GetSPLCalibrationData(self, request, context=None):
        try:
            result = self.query.get_calibration_data(request.mapping_id)
            return e2e_pb.GetSPLCalibrationDataResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.GetSPLCalibrationDataResponse(success=False, message=str(e), data="")

    def GetSPLStats(self, request, context=None):
        try:
            result = self.query.get_stats()
            return e2e_pb.GetSPLStatsResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.GetSPLStatsResponse(success=False, message=str(e), data="")

    def GetSPLByDevice(self, request, context=None):
        try:
            result = self.query.get_by_device(request.device_id)
            return e2e_pb.GetSPLByDeviceResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.GetSPLByDeviceResponse(success=False, message=str(e), data="")

    def CalibrateSPL(self, request, context=None):
        try:
            result = self.command.calibrate(request.mapping_id)
            return e2e_pb.CalibrateSPLResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.CalibrateSPLResponse(success=False, message=str(e), data="")

    def PlayTestTone(self, request, context=None):
        try:
            data = _loads(request.data, {})
            result = self.command.play_test_tone(data)
            return e2e_pb.PlayTestToneResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.PlayTestToneResponse(success=False, message=str(e), data="")

    def StopTestTone(self, request, context=None):
        try:
            data = _loads(request.data, {})
            result = self.command.stop_test_tone(data)
            return e2e_pb.StopTestToneResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.StopTestToneResponse(success=False, message=str(e), data="")
