# -*- coding: utf-8 -*-
"""实验室 CRUD gRPC servicer（INT-655）。

LaboratoryConfigServiceServicer：委托给 LaboratoryCommandService / LaboratoryQueryService

按 CQRS 拆分：
- 写操作（create/update/delete）-> LaboratoryCommandService
- 读操作（get_all/get_one/get_summary）-> LaboratoryQueryService
"""
from shared.proto import device_service_pb2 as pb
from shared.proto import device_service_pb2_grpc as grpc
from shared.utils.grpc_json import loads as _loads, dumps as _dumps


class LaboratoryConfigServiceServicer(grpc.LaboratoryConfigServiceServicer):
    """实验室配置 CRUD 服务 gRPC servicer，委托给 Command/Query 应用服务"""

    def __init__(self):
        self._command = None
        self._query = None

    @property
    def command(self):
        if self._command is None:
            from device_service.application.commands.laboratory_command_service import laboratory_command_service
            self._command = laboratory_command_service
        return self._command

    @property
    def query(self):
        if self._query is None:
            from device_service.application.queries.laboratory_query_service import laboratory_query_service
            self._query = laboratory_query_service
        return self._query

    def CreateLaboratory(self, request, context=None):
        try:
            data = _loads(request.data, {})
            result = self.command.create(data)
            return pb.CreateLaboratoryResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
                code=int(result.get('code', 400)),
            )
        except Exception as e:
            return pb.CreateLaboratoryResponse(success=False, message=str(e), data="", code=400)

    def UpdateLaboratory(self, request, context=None):
        try:
            data = _loads(request.data, {})
            result = self.command.update(request.lab_id, data)
            return pb.UpdateLaboratoryResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
                code=int(result.get('code', 400)),
            )
        except Exception as e:
            return pb.UpdateLaboratoryResponse(success=False, message=str(e), data="", code=400)

    def DeleteLaboratory(self, request, context=None):
        try:
            result = self.command.delete(request.lab_id)
            return pb.DeleteLaboratoryResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
                code=int(result.get('code', 400)),
            )
        except Exception as e:
            return pb.DeleteLaboratoryResponse(success=False, message=str(e), data="", code=400)

    def ListLaboratories(self, request, context=None):
        try:
            result = self.query.get_all(
                page=request.page or 1,
                per_page=request.per_page or 10,
                keyword=request.keyword or None,
                status=request.status or None,
            )
            return pb.ListLaboratoriesResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
                code=int(result.get('code', 400)),
            )
        except Exception as e:
            return pb.ListLaboratoriesResponse(success=False, message=str(e), data="", code=400)

    def GetLaboratory(self, request, context=None):
        try:
            result = self.query.get_one(request.lab_id)
            return pb.GetLaboratoryResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
                code=int(result.get('code', 400)),
            )
        except Exception as e:
            return pb.GetLaboratoryResponse(success=False, message=str(e), data="", code=400)

    def GetLaboratorySummary(self, request, context=None):
        try:
            result = self.query.get_summary(request.lab_id)
            return pb.GetLaboratorySummaryResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
                code=int(result.get('code', 400)),
            )
        except Exception as e:
            return pb.GetLaboratorySummaryResponse(success=False, message=str(e), data="", code=400)


# 模块级实例（供单测/进程内直接调用）
laboratory_config_service_servicer = LaboratoryConfigServiceServicer()
