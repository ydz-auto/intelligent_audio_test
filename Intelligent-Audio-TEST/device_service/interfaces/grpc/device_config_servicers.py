# -*- coding: utf-8 -*-
"""设备配置 CRUD gRPC servicer（从 servicers.py 拆分，P4-4）。

DeviceConfigServiceServicer：委托给 DeviceCommandService / DeviceQueryService

按 CQRS 拆分：
- 写操作（create/update/delete/scan/test/stop_test/health_check）-> DeviceCommandService
- 读操作（get_all/get_one/get_statuses/get_driver_keywords/get_available_serials）-> DeviceQueryService
- INT-80 设备分组/操作/批量/监控告警 -> 对应 Command/Query 应用服务
"""
from shared.proto import device_service_pb2 as e2e_pb
from shared.proto import device_service_pb2_grpc as e2e_grpc
from shared.utils.grpc_json import loads as _loads, dumps as _dumps


class DeviceConfigServiceServicer(e2e_grpc.DeviceConfigServiceServicer):
    """设备配置 CRUD 服务 gRPC servicer，委托给 DeviceCommandService / DeviceQueryService"""

    def __init__(self):
        self._command = None
        self._query = None
        self._group_command = None
        self._group_query = None
        self._operation = None
        self._batch = None
        self._alarm_rule = None
        self._monitor = None

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

    # ========== INT-80 依赖懒加载 ==========

    @property
    def group_command(self):
        if self._group_command is None:
            from device_service.application.commands.device_group_command_service import device_group_command_service
            self._group_command = device_group_command_service
        return self._group_command

    @property
    def group_query(self):
        if self._group_query is None:
            from device_service.application.queries.device_group_query_service import device_group_query_service
            self._group_query = device_group_query_service
        return self._group_query

    @property
    def operation(self):
        if self._operation is None:
            from device_service.application.commands.device_operation_service import device_operation_service
            self._operation = device_operation_service
        return self._operation

    @property
    def batch(self):
        if self._batch is None:
            from device_service.application.commands.device_operation_service import device_batch_service
            self._batch = device_batch_service
        return self._batch

    @property
    def alarm_rule(self):
        if self._alarm_rule is None:
            from device_service.application.commands.device_alarm_rule_service import device_alarm_rule_service
            self._alarm_rule = device_alarm_rule_service
        return self._alarm_rule

    @property
    def monitor(self):
        if self._monitor is None:
            from device_service.application.services.device_monitor_service import device_monitor_service
            self._monitor = device_monitor_service
        return self._monitor

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

    # ========== INT-80 设备分组 ==========

    def CreateDeviceGroup(self, request, context=None):
        try:
            data = _loads(request.data, {})
            result = self.group_command.create(data)
            return e2e_pb.CreateDeviceGroupResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.CreateDeviceGroupResponse(success=False, message=str(e), data="")

    def UpdateDeviceGroup(self, request, context=None):
        try:
            data = _loads(request.data, {})
            result = self.group_command.update(request.group_id, data)
            return e2e_pb.UpdateDeviceGroupResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.UpdateDeviceGroupResponse(success=False, message=str(e), data="")

    def DeleteDeviceGroup(self, request, context=None):
        try:
            result = self.group_command.delete(request.group_id, cascade=request.cascade)
            return e2e_pb.DeleteDeviceGroupResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.DeleteDeviceGroupResponse(success=False, message=str(e), data="")

    def ListDeviceGroups(self, request, context=None):
        try:
            result = self.group_query.get_all(
                page=request.page or 1,
                per_page=request.per_page or 100,
                keyword=request.keyword or None,
                group_type=request.group_type or None,
            )
            return e2e_pb.ListDeviceGroupsResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.ListDeviceGroupsResponse(success=False, message=str(e), data="")

    def GetDeviceGroup(self, request, context=None):
        try:
            result = self.group_query.get_one(request.group_id)
            return e2e_pb.GetDeviceGroupResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.GetDeviceGroupResponse(success=False, message=str(e), data="")

    def AddDevicesToGroup(self, request, context=None):
        try:
            data = _loads(request.data, {})
            result = self.group_command.add_devices(request.group_id, data.get('device_ids'))
            return e2e_pb.AddDevicesToGroupResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.AddDevicesToGroupResponse(success=False, message=str(e), data="")

    def RemoveDevicesFromGroup(self, request, context=None):
        try:
            data = _loads(request.data, {})
            result = self.group_command.remove_devices(request.group_id, data.get('device_ids'))
            return e2e_pb.RemoveDevicesFromGroupResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.RemoveDevicesFromGroupResponse(success=False, message=str(e), data="")

    # ========== INT-80 设备操作/批量 ==========

    def ControlDevice(self, request, context=None):
        try:
            data = _loads(request.data, {})
            result = self.operation.execute(request.device_id, data.get('operation'),
                                            data.get('params'))
            return e2e_pb.ControlDeviceResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.ControlDeviceResponse(success=False, message=str(e), data="")

    def BatchDeviceAction(self, request, context=None):
        try:
            data = _loads(request.data, {})
            result = self.batch.batch_action(data)
            return e2e_pb.BatchDeviceActionResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.BatchDeviceActionResponse(success=False, message=str(e), data="")

    # ========== INT-80 状态历史/告警 ==========

    def GetDeviceStatusHistory(self, request, context=None):
        try:
            data = _loads(request.data, {})
            result = self.monitor.list_status_history(
                device_ids=data.get('device_ids'),
                event_type=data.get('event_type') or None,
                start_time=data.get('start_time') or None,
                end_time=data.get('end_time') or None,
                page=data.get('page') or 1,
                per_page=data.get('per_page') or 50,
            )
            return e2e_pb.GetDeviceStatusHistoryResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.GetDeviceStatusHistoryResponse(success=False, message=str(e), data="")

    def CreateAlarmRule(self, request, context=None):
        try:
            data = _loads(request.data, {})
            result = self.alarm_rule.create(data)
            return e2e_pb.CreateAlarmRuleResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.CreateAlarmRuleResponse(success=False, message=str(e), data="")

    def UpdateAlarmRule(self, request, context=None):
        try:
            data = _loads(request.data, {})
            result = self.alarm_rule.update(request.rule_id, data)
            return e2e_pb.UpdateAlarmRuleResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.UpdateAlarmRuleResponse(success=False, message=str(e), data="")

    def DeleteAlarmRule(self, request, context=None):
        try:
            result = self.alarm_rule.delete(request.rule_id)
            return e2e_pb.DeleteAlarmRuleResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.DeleteAlarmRuleResponse(success=False, message=str(e), data="")

    def ListAlarmRules(self, request, context=None):
        try:
            enabled = None
            if request.enabled:
                enabled = str(request.enabled).lower() == 'true'
            result = self.alarm_rule.list(
                page=request.page or 1,
                per_page=request.per_page or 50,
                metric_type=request.metric_type or None,
                enabled=enabled,
            )
            return e2e_pb.ListAlarmRulesResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.ListAlarmRulesResponse(success=False, message=str(e), data="")

    def ListAlarms(self, request, context=None):
        try:
            data = _loads(request.data, {})
            result = self.monitor.list_alarms(
                status=data.get('status') or None,
                severity=data.get('severity') or None,
                device_id=data.get('device_id'),
                page=data.get('page') or 1,
                per_page=data.get('per_page') or 50,
            )
            return e2e_pb.ListAlarmsResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.ListAlarmsResponse(success=False, message=str(e), data="")

    def AcknowledgeAlarm(self, request, context=None):
        try:
            data = _loads(request.data, {})
            result = self.monitor.acknowledge_alarm(
                request.alarm_id, str(data.get('acknowledged_by') or ''))
            return e2e_pb.AcknowledgeAlarmResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.AcknowledgeAlarmResponse(success=False, message=str(e), data="")

    def GetAlarmStats(self, request, context=None):
        try:
            result = self.monitor.get_alarm_stats()
            return e2e_pb.GetAlarmStatsResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result.get('data')),
            )
        except Exception as e:
            return e2e_pb.GetAlarmStatsResponse(success=False, message=str(e), data="")
