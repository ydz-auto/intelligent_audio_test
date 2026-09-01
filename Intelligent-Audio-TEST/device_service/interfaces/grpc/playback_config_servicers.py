# -*- coding: utf-8 -*-
"""播放设备配置 gRPC servicer（从 servicers.py 拆分，P4-4）。

PlaybackConfigServiceServicer：委托给 PlaybackCommandService（写）/ PlaybackQueryService（读）
"""
from shared.proto import device_service_pb2 as e2e_pb
from shared.proto import device_service_pb2_grpc as e2e_grpc
from shared.utils.grpc_json import loads as _loads, dumps as _dumps


class PlaybackConfigServiceServicer(e2e_grpc.PlaybackConfigServiceServicer):
    """播放设备 gRPC servicer，委托给 PlaybackCommandService（写）/ PlaybackQueryService（读）"""

    def __init__(self):
        self._command = None
        self._query = None

    @property
    def command(self):
        if self._command is None:
            from device_service.application.commands.playback_command_service import playback_command_service
            self._command = playback_command_service
        return self._command

    @property
    def query(self):
        if self._query is None:
            from device_service.application.queries.playback_query_service import playback_query_service
            self._query = playback_query_service
        return self._query

    def CreatePlaybackDevice(self, request, context=None):
        try:
            data = _loads(request.data, {})
            result = self.command.create(data)
            return e2e_pb.CreatePlaybackDeviceResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.CreatePlaybackDeviceResponse(success=False, message=str(e), data="")

    def UpdatePlaybackDevice(self, request, context=None):
        try:
            data = _loads(request.data, {})
            result = self.command.update(request.device_id, data)
            return e2e_pb.UpdatePlaybackDeviceResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.UpdatePlaybackDeviceResponse(success=False, message=str(e), data="")

    def DeletePlaybackDevice(self, request, context=None):
        try:
            result = self.command.delete(request.device_id)
            return e2e_pb.DeletePlaybackDeviceResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.DeletePlaybackDeviceResponse(success=False, message=str(e), data="")

    def ListPlaybackDevices(self, request, context=None):
        try:
            result = self.query.get_all(
                page=request.page or 1,
                per_page=request.per_page or 10,
                keyword=request.keyword or None,
                device_type=request.device_type or None,
            )
            return e2e_pb.ListPlaybackDevicesResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.ListPlaybackDevicesResponse(success=False, message=str(e), data="")

    def GetPlaybackDevice(self, request, context=None):
        try:
            result = self.query.get_one(request.device_id)
            return e2e_pb.GetPlaybackDeviceResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.GetPlaybackDeviceResponse(success=False, message=str(e), data="")

    def ScanPlaybackDevices(self, request, context=None):
        try:
            result = self.query.scan()
            return e2e_pb.ScanPlaybackDevicesResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.ScanPlaybackDevicesResponse(success=False, message=str(e), data="")

    def CheckPlaybackStatus(self, request, context=None):
        try:
            result = self.command.check_status()
            return e2e_pb.CheckPlaybackStatusResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.CheckPlaybackStatusResponse(success=False, message=str(e), data="")

    def AssociateSPL(self, request, context=None):
        try:
            data = _loads(request.data, {})
            result = self.command.associate_spl(request.device_id, data)
            return e2e_pb.AssociateSPLResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.AssociateSPLResponse(success=False, message=str(e), data="")

    def TestPlaybackDevice(self, request, context=None):
        try:
            data = _loads(request.data, {})
            result = self.command.test(request.device_id, data)
            return e2e_pb.TestPlaybackDeviceResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.TestPlaybackDeviceResponse(success=False, message=str(e), data="")

    def StopPlaybackTest(self, request, context=None):
        try:
            result = self.command.stop_test(request.device_id)
            return e2e_pb.StopPlaybackTestResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.StopPlaybackTestResponse(success=False, message=str(e), data="")
