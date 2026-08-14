# -*- coding: utf-8 -*-
"""device_service gRPC servicer 实现（interfaces 层）。

将 gRPC RPC 方法委托给 application / infrastructure 层：
- DeviceServiceServicer       -> device_driver_factory
- DeviceResultServiceServicer -> device_result_collector
- EnvDeviceServiceServicer    -> EnvDeviceFactory
- DeviceConfigServiceServicer -> device_command_service / device_query_service
- PlaybackConfigServiceServicer -> playback_command_service / playback_query_service
- SPLConfigServiceServicer    -> spl_command_service / spl_query_service

约定：
- 复杂参数通过 JSON string 传递，方法内 _loads 解析
- 返回结果通过 JSON string 封装到 data 字段
- 所有方法用 try/except 包裹，异常返回 success=False

说明：proto 已拆分为 device_service_pb2。
"""

import threading

from shared.proto import device_service_pb2 as e2e_pb
from shared.proto import device_service_pb2_grpc as e2e_grpc
from shared.utils.grpc_json import loads as _loads, dumps as _dumps
from shared.utils.status_constants import ExecutionStatus


# ==================== DeviceServiceServicer ====================

class DeviceServiceServicer(e2e_grpc.DeviceServiceServicer):
    """设备驱动服务 gRPC servicer，委托给 device_driver_factory"""

    def __init__(self):
        self._factory = None

    @property
    def factory(self):
        if self._factory is None:
            from device_service.infrastructure.drivers.device_driver import device_driver_factory
            self._factory = device_driver_factory
        return self._factory

    def CreateDriver(self, request, context=None):
        """创建设备驱动 / 分发设备操作

        根据 device_config 的 action 字段分发：
        - 无 action 或 action='initialize': 创建/初始化 driver
        - action='pre_process': 预处理
        - action='post_process': 后处理
        - action='get_results': 采集结果
        - action='teardown': 销毁 driver
        - action='extract_results_from_archive': 从存档提取结果
        """
        try:
            device_config = _loads(request.device_config, {})
            task_id = request.task_id

            # 兼容调用方直接传 list 格式: [{action, device_sn, ...}, ...]
            device_info_list_raw = None
            if isinstance(device_config, list):
                device_info_list_raw = device_config
                # 从第一个元素提取 action 及其他字段（默认 initialize，保持向后兼容）
                first_item = device_info_list_raw[0] if device_info_list_raw else {}
                if not isinstance(first_item, dict):
                    first_item = {}
                device_config = {
                    'action': first_item.get('action', 'initialize'),
                    'device_info_list': device_info_list_raw,
                    'device_sn': first_item.get('device_sn'),
                    'test_case_id': first_item.get('test_case_id'),
                    'kwargs': first_item.get('kwargs', {}),
                    'system': first_item.get('system'),
                    'keywords': first_item.get('keywords'),
                }

            action = device_config.get('action', 'initialize')
            device_sn = device_config.get('device_sn')
            test_case_id = device_config.get('test_case_id')
            kwargs = device_config.get('kwargs', {})

            # action=initialize 时可能传入 device_info_list（列表）
            if action == 'initialize':
                system = device_config.get('system')
                keywords = device_config.get('keywords')
                if not device_info_list_raw:
                    device_info_list_raw = device_config.get('device_info_list', [])

                # 注册任务设备
                if device_info_list_raw:
                    self.factory.register_task_devices(task_id, device_info_list_raw)

                # 如果没有显式传 device_sn,从 device_info_list 取第一个
                if not device_sn and device_info_list_raw:
                    device_sn = device_info_list_raw[0].get('device_sn')

                driver = self.factory.get_driver(system, keywords=keywords, device_sn=device_sn)
                if driver and hasattr(driver, 'initialize'):
                    driver.initialize(device_sn, task_id=task_id, test_case_id=test_case_id, **kwargs)
                driver_info = {
                    "system": system,
                    "keywords": keywords,
                    "device_sn": device_sn,
                    "driver_found": driver is not None,
                    "driver_name": driver.__class__.__name__ if driver else None,
                }
                return e2e_pb.CreateDriverResponse(success=True, message="ok", data=_dumps(driver_info))

            # 根据设备 SN 查找已注册的 driver
            driver = self.factory.get_driver_by_sn(device_sn, task_id)

            if action == 'pre_process':
                if driver and hasattr(driver, 'pre_process'):
                    driver.pre_process(device_sn, task_id=task_id, test_case_id=test_case_id, **kwargs)
                return e2e_pb.CreateDriverResponse(success=True, message="ok",
                    data=_dumps({"device_sn": device_sn, "action": "pre_process", "executed": driver is not None}))

            if action == 'post_process':
                if driver and hasattr(driver, 'post_process'):
                    driver.post_process(device_sn, task_id=task_id, test_case_id=test_case_id, **kwargs)
                return e2e_pb.CreateDriverResponse(success=True, message="ok",
                    data=_dumps({"device_sn": device_sn, "action": "post_process", "executed": driver is not None}))

            if action == 'get_results':
                if driver and hasattr(driver, 'get_results'):
                    results = driver.get_results(device_sn, task_id=task_id, test_case_id=test_case_id, **kwargs)
                    return e2e_pb.CreateDriverResponse(success=True, message="ok",
                        data=_dumps({"device_sn": device_sn, "results": results}))
                return e2e_pb.CreateDriverResponse(success=True, message="ok",
                    data=_dumps({"device_sn": device_sn, "results": {}}))

            if action == 'extract_results_from_archive':
                system = device_config.get('system')
                keywords = device_config.get('keywords')
                if not driver:
                    driver = self.factory.get_driver(system, keywords=keywords)
                if driver and hasattr(driver, 'extract_results_from_archive'):
                    archive_results = driver.extract_results_from_archive(
                        device_sn, task_id=task_id, test_case_id=test_case_id, **kwargs)
                    return e2e_pb.CreateDriverResponse(success=True, message="ok",
                        data=_dumps({"device_sn": device_sn, "results": archive_results}))
                return e2e_pb.CreateDriverResponse(success=False,
                    message=f"驱动不支持存档提取: system={system}", data="")

            if action == 'get_final_results':
                if driver and hasattr(driver, 'get_final_results'):
                    results = driver.get_final_results(
                        device_sn, task_id=task_id, test_case_id=test_case_id, **kwargs)
                    return e2e_pb.CreateDriverResponse(success=True, message="ok",
                        data=_dumps({"device_sn": device_sn, "results": results}))
                return e2e_pb.CreateDriverResponse(success=True, message="ok",
                    data=_dumps({"device_sn": device_sn, "results": []}))

            if action == 'teardown':
                if driver and hasattr(driver, 'teardown'):
                    driver.teardown(device_sn, task_id=task_id, test_case_id=test_case_id, **kwargs)
                return e2e_pb.CreateDriverResponse(success=True, message="ok",
                    data=_dumps({"device_sn": device_sn, "action": "teardown", "executed": driver is not None}))

            # 未知 action，返回基本信息
            return e2e_pb.CreateDriverResponse(success=True, message="ok",
                data=_dumps({"device_sn": device_sn, "action": action, "executed": False}))
        except Exception as e:
            return e2e_pb.CreateDriverResponse(success=False, message=str(e), data="")

    def DestroyDriver(self, request, context=None):
        """销毁设备驱动"""
        try:
            task_id = request.task_id
            self.factory.cleanup_devices(task_id)
            return e2e_pb.DestroyDriverResponse(
                success=True, message="ok", data=_dumps({"task_id": str(task_id), "cleaned": True})
            )
        except Exception as e:
            return e2e_pb.DestroyDriverResponse(success=False, message=str(e), data="")

    def RegisterTaskEvents(self, request, context=None):
        """注册任务事件回调"""
        try:
            from device_service.infrastructure.drivers.utils import register_task_events, get_task_events
            callback_config = _loads(request.callback_config, {})
            task_id = request.task_id

            existing = get_task_events(task_id)
            if existing:
                stop_event = existing['stop_event']
                pause_event = existing['pause_event']
                if callback_config.get('stop_event_set', False):
                    stop_event.set()
                else:
                    stop_event.clear()
                if callback_config.get('pause_event_set', True):
                    pause_event.set()
                else:
                    pause_event.clear()
                action = 'updated'
            else:
                stop_event = threading.Event()
                pause_event = threading.Event()
                pause_event.set()
                if callback_config.get('stop_event_set', False):
                    stop_event.set()
                if not callback_config.get('pause_event_set', True):
                    pause_event.clear()
                register_task_events(task_id, stop_event, pause_event)
                action = 'registered'

            return e2e_pb.RegisterTaskEventsResponse(
                success=True, message="ok",
                data=_dumps({"task_id": str(task_id), action: True}),
            )
        except Exception as e:
            return e2e_pb.RegisterTaskEventsResponse(success=False, message=str(e), data="")

    def UnregisterTaskEvents(self, request, context=None):
        """注销任务事件回调"""
        try:
            from device_service.infrastructure.drivers.utils import unregister_task_events
            task_id = request.task_id
            unregister_task_events(task_id)
            return e2e_pb.UnregisterTaskEventsResponse(
                success=True, message="ok",
                data=_dumps({"task_id": str(task_id), "unregistered": True}),
            )
        except Exception as e:
            return e2e_pb.UnregisterTaskEventsResponse(success=False, message=str(e), data="")

    def GetTaskEvents(self, request, context=None):
        """获取任务事件"""
        try:
            from device_service.infrastructure.drivers.utils import get_task_events
            task_id = request.task_id
            events = get_task_events(task_id)
            events_info = {"exists": events is not None}
            if events:
                events_info["has_stop_event"] = events.get('stop_event') is not None
                events_info["has_pause_event"] = events.get('pause_event') is not None
            return e2e_pb.GetTaskEventsResponse(
                success=True, message="ok", data=_dumps({"task_id": str(task_id), "events": events_info})
            )
        except Exception as e:
            return e2e_pb.GetTaskEventsResponse(success=False, message=str(e), data="")

    def DriverScan(self, request, context=None):
        """扫描设备"""
        try:
            system = request.system
            keywords = request.keywords or None
            if system:
                driver = self.factory.get_driver(system, keywords=keywords)
                result = driver.scan() if driver else []
            else:
                # system 为空时扫描所有已注册驱动
                result = self.factory.scan_devices()
            return e2e_pb.DriverScanResponse(success=True, message="ok", data=_dumps(result))
        except Exception as e:
            return e2e_pb.DriverScanResponse(success=False, message=str(e), data="")

    def DriverUnlock(self, request, context=None):
        """解锁设备"""
        try:
            system = request.system
            keywords = request.keywords or None
            serial_or_ip = request.serial_or_ip
            driver = self.factory.get_driver(system, keywords=keywords) if system else None
            if driver:
                driver.unlock(serial_or_ip)
            return e2e_pb.DriverUnlockResponse(success=True, message="ok", data=_dumps({"unlocked": True}))
        except Exception as e:
            return e2e_pb.DriverUnlockResponse(success=False, message=str(e), data="")

    def GetMockMode(self, request, context=None):
        """获取 mock 模式"""
        try:
            mock_mode = self.factory.get_mock_mode()
            return e2e_pb.GetMockModeResponse(success=True, message="ok", data=_dumps({"mock_mode": mock_mode}))
        except Exception as e:
            return e2e_pb.GetMockModeResponse(success=False, message=str(e), data="")

    def SetMockMode(self, request, context=None):
        """设置 mock 模式"""
        try:
            self.factory.set_mock_mode(request.mock_mode)
            return e2e_pb.SetMockModeResponse(success=True, message="ok", data=_dumps({"mock_mode": request.mock_mode}))
        except Exception as e:
            return e2e_pb.SetMockModeResponse(success=False, message=str(e), data="")

    def GetDriverNameByKeywords(self, request, context=None):
        """按关键词获取驱动名"""
        try:
            name = self.factory.get_driver_name_by_keywords(request.system, request.keywords or None)
            return e2e_pb.GetDriverNameByKeywordsResponse(success=True, message="ok", data=_dumps({"driver_name": name}))
        except Exception as e:
            return e2e_pb.GetDriverNameByKeywordsResponse(success=False, message=str(e), data="")

    def GetRegisteredKeywords(self, request, context=None):
        """获取已注册关键词"""
        try:
            keywords_list = self.factory.get_registered_keywords()
            return e2e_pb.GetRegisteredKeywordsResponse(success=True, message="ok", data=_dumps(keywords_list))
        except Exception as e:
            return e2e_pb.GetRegisteredKeywordsResponse(success=False, message=str(e), data="")


# ==================== DeviceResultServiceServicer ====================

class DeviceResultServiceServicer(e2e_grpc.DeviceResultServiceServicer):
    """设备结果采集服务 gRPC servicer，委托给 device_result_collector"""

    def __init__(self):
        self._collector = None

    @property
    def collector(self):
        if self._collector is None:
            from device_service.domain.services.device_result_collector import get_device_result_collector
            from device_service.infrastructure.acl.algorithm_query_acl_repository import algorithm_query_acl_repository
            self._collector = get_device_result_collector(field_query_service=algorithm_query_acl_repository)
        return self._collector

    def CollectResult(self, request, context=None):
        """采集设备结果"""
        try:
            collect_config = _loads(request.collect_config, {})
            task_id = request.task_id
            test_case_id = collect_config.get('test_case_id')
            device_info_list = collect_config.get('device_info_list', [])
            extra_params = collect_config.get('extra_params', {})
            mode = collect_config.get('mode', 'raw')

            if mode == 'convert':
                tagged_results = collect_config.get('tagged_results', [])
                algorithm_type = collect_config.get('algorithm_type', '')
                result = self.collector.convert_results(tagged_results, algorithm_type)
            elif mode == 'round':
                round_idx = collect_config.get('round_idx', 0)
                round_config = collect_config.get('round_config', {})
                round_start_time = collect_config.get('round_start_time')
                # 注入 driver（gRPC 传输无法序列化 driver 对象）
                self._inject_drivers(device_info_list, task_id)
                result = self.collector.collect_round_results(
                    task_id, test_case_id, device_info_list,
                    round_idx, round_config, round_start_time,
                )
            else:
                # 注入 driver（gRPC 传输无法序列化 driver 对象）
                self._inject_drivers(device_info_list, task_id)
                result = self.collector.collect_raw_results(
                    task_id, test_case_id, device_info_list, extra_params,
                )
            return e2e_pb.CollectResultResponse(
                success=True, message="ok", data=_dumps({"results": result, "count": len(result) if result else 0})
            )
        except Exception as e:
            return e2e_pb.CollectResultResponse(success=False, message=str(e), data="")

    @staticmethod
    def _inject_drivers(device_info_list, task_id):
        """将已注册的 driver 实例注入到 device_info_list 中

        gRPC 传输无法序列化 driver 对象，因此 e2e_test_service 发来的
        device_info_list 不含 driver 字段。此方法从 device_driver_factory
        查找并注入，使 collect_raw_results 能正常调用 driver.get_results()。
        """
        from device_service.infrastructure.drivers.device_driver import device_driver_factory
        for info in device_info_list:
            if isinstance(info, dict) and 'driver' not in info:
                device_sn = info.get('device_sn')
                if device_sn:
                    driver = device_driver_factory.get_driver_by_sn(device_sn, task_id)
                    if driver:
                        info['driver'] = driver

    def ReextractResult(self, request, context=None):
        """重新提取设备结果"""
        try:
            from device_service.application.device_result_reextractor_service import get_device_result_reextractor
            reextract_config = _loads(request.reextract_config, {})
            task_id = request.task_id
            execution_status = reextract_config.get('execution_status', ExecutionStatus.COMPLETED)
            evaluation_status = reextract_config.get('evaluation_status')

            reextractor = get_device_result_reextractor()
            result = reextractor.reextract_for_task(
                task_id, execution_status=execution_status, evaluation_status=evaluation_status,
            )
            return e2e_pb.ReextractResultResponse(
                success=True, message="ok", data=_dumps(result)
            )
        except Exception as e:
            return e2e_pb.ReextractResultResponse(success=False, message=str(e), data="")


# ==================== EnvDeviceServiceServicer ====================

class EnvDeviceServiceServicer(e2e_grpc.EnvDeviceServiceServicer):
    """环境设备服务 gRPC servicer，委托给 EnvDeviceFactory"""

    def __init__(self):
        self._factory_cls = None

    @property
    def factory_cls(self):
        if self._factory_cls is None:
            from device_service.infrastructure.env_devices.factory import EnvDeviceFactory
            self._factory_cls = EnvDeviceFactory
        return self._factory_cls

    def ControlEnvDevice(self, request, context=None):
        """控制环境设备（导轨旋转等）"""
        try:
            device_action = _loads(request.device_action, {})
            task_id = request.task_id
            action = device_action.get('action', 'setup')
            device_type = device_action.get('device_type')
            config = device_action.get('config')
            settings = device_action.get('settings', {})
            device_configs = device_action.get('device_configs', [])

            result = {"task_id": str(task_id), "action": action, "devices": []}

            if device_configs:
                devices = self.factory_cls.create_from_config(device_configs)
            elif device_type:
                devices = [self.factory_cls.create(device_type, config)]
            else:
                devices = []

            for dev in devices:
                dev_info = {
                    "name": getattr(dev, 'name', None),
                    "device_type": getattr(dev, 'device_type', None),
                    "available": dev.is_available() if hasattr(dev, 'is_available') else False,
                }
                try:
                    if action == 'setup':
                        dev.connect()
                        state = dev.setup(settings)
                        dev_info["state"] = state
                        dev_info["connected"] = True
                    elif action == 'teardown':
                        state = device_action.get('state', {})
                        dev.teardown(state)
                        dev_info["torn_down"] = True
                    elif action == 'connect':
                        dev.connect()
                        dev_info["connected"] = True
                    elif action == 'disconnect':
                        dev.disconnect()
                        dev_info["disconnected"] = True
                except Exception as dev_e:
                    dev_info["error"] = str(dev_e)
                result["devices"].append(dev_info)

            return e2e_pb.ControlEnvDeviceResponse(
                success=True, message="ok", data=_dumps(result)
            )
        except Exception as e:
            return e2e_pb.ControlEnvDeviceResponse(success=False, message=str(e), data="")


# ==================== DeviceConfigServiceServicer ====================

class DeviceConfigServiceServicer(e2e_grpc.DeviceConfigServiceServicer):
    """设备配置 CRUD 服务 gRPC servicer，委托给 DeviceCommandService / DeviceQueryService

    按 CQRS 拆分：
    - 写操作（create/update/delete/scan/test/stop_test/health_check）-> DeviceCommandService
    - 读操作（get_all/get_one/get_statuses/get_driver_keywords/get_available_serials）-> DeviceQueryService
    """

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


# ==================== PlaybackConfigServiceServicer ====================

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


# ==================== SPLConfigServiceServicer ====================

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


__all__ = [
    "DeviceServiceServicer",
    "DeviceResultServiceServicer",
    "EnvDeviceServiceServicer",
    "DeviceConfigServiceServicer",
    "PlaybackConfigServiceServicer",
    "SPLConfigServiceServicer",
]
