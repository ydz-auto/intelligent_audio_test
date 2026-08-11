"""设备服务代理：_DeviceDriverFactoryProxy、_DriverProxy、_DeviceResultReextractorProxy、_DeviceResultCollectorApiProxy、_DeviceConfigProxy 及相关单例/工厂函数。"""
import json

from shared.clients.grpc_clients import (
    get_device_service_stub,
    get_device_result_service_stub,
    get_device_config_service_stub,
)

from ._common import _grpc_call


class _DeviceDriverFactoryProxy:
    """device_driver_factory 代理：把方法调用转发到 gRPC DeviceService"""

    def get_driver(self, system, keywords=None, **kwargs):
        """获取 driver 代理对象"""
        return _DriverProxy(system, keywords, **kwargs)

    def get_driver_name_by_keywords(self, system, keywords):
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_device_service_stub()
            resp = stub.GetDriverNameByKeywords(device_pb.GetDriverNameByKeywordsRequest(
                system=system or '',
                keywords=keywords or '',
            ))
            if resp.success and resp.data:
                return json.loads(resp.data).get('driver_name', '')
            return ''

        return _grpc_call(_call, default_return='', error_msg_prefix="获取驱动名称失败")

    def get_registered_keywords(self):
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_device_service_stub()
            resp = stub.GetRegisteredKeywords(device_pb.GetRegisteredKeywordsRequest())
            if resp.success and resp.data:
                return json.loads(resp.data)
            return []

        return _grpc_call(_call, default_return=[], error_msg_prefix="获取已注册关键词失败")

    def get_mock_mode(self):
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_device_service_stub()
            resp = stub.GetMockMode(device_pb.GetMockModeRequest())
            if resp.success and resp.data:
                return json.loads(resp.data).get('mock_mode', False)
            return False

        return _grpc_call(_call, default_return=False, error_msg_prefix="获取 mock 模式失败")


# 模块级单例
device_driver_factory = _DeviceDriverFactoryProxy()


class _DriverProxy:
    """driver 对象代理：把 scan/unlock/_mock_mode 等操作转发到 gRPC DeviceService"""

    def __init__(self, system, keywords=None, **kwargs):
        self._system = system
        self._keywords = keywords
        self._kwargs = kwargs

    def scan(self):
        """扫描设备"""
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_device_service_stub()
            resp = stub.DriverScan(device_pb.DriverScanRequest(
                system=self._system or '',
                keywords=self._keywords or '',
            ))
            if resp.success and resp.data:
                return json.loads(resp.data)
            return []

        return _grpc_call(_call, default_return=[], error_msg_prefix="设备扫描失败")

    def unlock(self, serial_or_ip):
        """解锁设备"""
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_device_service_stub()
            resp = stub.DriverUnlock(device_pb.DriverUnlockRequest(
                system=self._system or '',
                keywords=self._keywords or '',
                serial_or_ip=serial_or_ip or '',
            ))
            return resp.success

        return _grpc_call(_call, default_return=False, error_msg_prefix="设备解锁失败")

    @property
    def _mock_mode(self):
        """获取 mock 模式状态"""
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_device_service_stub()
            resp = stub.GetMockMode(device_pb.GetMockModeRequest())
            if resp.success and resp.data:
                return json.loads(resp.data).get('mock_mode', False)
            return False

        return _grpc_call(_call, default_return=False, log_error=False)

    @_mock_mode.setter
    def _mock_mode(self, value):
        """设置 mock 模式"""
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_device_service_stub()
            stub.SetMockMode(device_pb.SetMockModeRequest(
                mock_mode=bool(value),
            ))

        _grpc_call(_call, default_return=None, log_error=False)


class _DeviceResultReextractorProxy:
    """get_device_result_reextractor 返回的对象的代理"""

    def reextract_for_task(self, task_id, evaluation_status=None):
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_device_result_service_stub()
            reextract_config = {
                'evaluation_status': evaluation_status,
            }
            resp = stub.ReextractResult(device_pb.ReextractResultRequest(
                task_id=str(task_id),
                reextract_config=json.dumps(reextract_config)
            ))
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': str(e), 'data': None},
            error_msg_prefix="重新提取设备结果失败",
        )


def get_device_result_reextractor():
    """原 get_device_result_reextractor 返回单例，此处返回代理"""
    return _DeviceResultReextractorProxy()


def get_device_result_collector():
    """原 get_device_result_collector 返回单例，此处返回代理"""
    return _DeviceResultCollectorApiProxy()


class _DeviceResultCollectorApiProxy:
    """设备结果采集器代理（api_gateway 端）"""

    def convert_results(self, all_results, algorithm_type):
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_device_result_service_stub()
            collect_config = {
                'action': 'convert_results',
                'all_results': all_results,
                'algorithm_type': algorithm_type,
            }
            resp = stub.CollectResult(device_pb.CollectResultRequest(
                task_id='',
                collect_config=json.dumps(collect_config)
            ))
            if not resp.success or not resp.data:
                return all_results
            return json.loads(resp.data)

        return _grpc_call(_call, default_return=all_results, error_msg_prefix="转换结果失败")

    def build_case_result_log(self, algorithm_type, res, ref_fields=None, **kwargs):
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_device_result_service_stub()
            collect_config = {
                'action': 'build_case_result_log',
                'algorithm_type': algorithm_type,
                'res': res,
                'ref_fields': ref_fields,
                'kwargs': kwargs,
            }
            resp = stub.CollectResult(device_pb.CollectResultRequest(
                task_id='',
                collect_config=json.dumps(collect_config)
            ))
            if resp.success and resp.data:
                return resp.data
            return ''

        return _grpc_call(_call, default_return='', error_msg_prefix="构建用例结果日志失败")


# ==================== Device 配置 CRUD 代理 ====================

class _DeviceConfigProxy:
    """Device 配置 CRUD 代理：把方法调用转发到 gRPC DeviceConfigService

    替代原 DeviceCommandService/DeviceQueryService 直接操作 DB 的方式，
    网关侧不再 import Device 模型和 get_db_session()，统一走 gRPC。
    """

    def create(self, data):
        """创建设备

        Args:
            data: 设备配置参数字典

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_device_config_service_stub()
            resp = stub.CreateDevice(device_pb.CreateDeviceRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'创建设备失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='创建设备失败',
        )

    def update(self, device_id, data):
        """更新设备

        Args:
            device_id: 设备 ID
            data: 更新字段字典

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_device_config_service_stub()
            resp = stub.UpdateDevice(device_pb.UpdateDeviceRequest(
                device_id=int(device_id),
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'更新设备失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='更新设备失败',
        )

    def delete(self, device_id):
        """删除设备（软删除）

        Args:
            device_id: 设备 ID

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_device_config_service_stub()
            resp = stub.DeleteDevice(device_pb.DeleteDeviceRequest(
                device_id=int(device_id),
            ))
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'删除设备失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='删除设备失败',
        )

    def get_all(self, page=1, per_page=10, keyword=None, status=None,
                device_type=None, algorithm_type=None):
        """分页查询设备列表

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_device_config_service_stub()
            resp = stub.ListDevices(device_pb.ListDevicesRequest(
                page=int(page or 1),
                per_page=int(per_page or 10),
                keyword=keyword or '',
                status=status or '',
                device_type=device_type or '',
                algorithm_type=algorithm_type or '',
            ))
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'查询设备列表失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='查询设备列表失败',
        )

    def get_one(self, device_id):
        """查询单个设备详情

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_device_config_service_stub()
            resp = stub.GetDevice(device_pb.GetDeviceRequest(
                device_id=int(device_id),
            ))
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'查询设备详情失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='查询设备详情失败',
        )

    def get_statuses(self, device_ids=None):
        """批量获取设备状态

        Args:
            device_ids: 设备 ID 列表，为空则查询全部

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_device_config_service_stub()
            resp = stub.GetDeviceStatuses(device_pb.GetDeviceStatusesRequest(
                data=json.dumps({'ids': device_ids or []}, ensure_ascii=False, default=str),
            ))
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取设备状态失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='获取设备状态失败',
        )

    def scan(self):
        """扫描物理设备

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_device_config_service_stub()
            resp = stub.ScanPhysicalDevices(device_pb.ScanPhysicalDevicesRequest())
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'扫描设备失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='扫描设备失败',
        )

    def test(self, device_id):
        """测试设备

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_device_config_service_stub()
            resp = stub.TestDevice(device_pb.TestDeviceRequest(
                device_id=int(device_id),
            ))
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'测试设备失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='测试设备失败',
        )

    def stop_test(self, device_id):
        """停止设备测试

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_device_config_service_stub()
            resp = stub.StopDeviceTest(device_pb.StopDeviceTestRequest(
                device_id=int(device_id),
            ))
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'停止设备测试失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='停止设备测试失败',
        )

    def get_driver_keywords(self):
        """获取所有已注册的驱动关键字

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_device_config_service_stub()
            resp = stub.GetDriverKeywords(device_pb.GetDriverKeywordsRequest())
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取驱动关键字失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='获取驱动关键字失败',
        )

    def health_check(self, device_ids=None):
        """批量健康检查

        Args:
            device_ids: 设备 ID 列表，为空则检查全部

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_device_config_service_stub()
            resp = stub.HealthCheckDevices(device_pb.HealthCheckDevicesRequest(
                data=json.dumps({'device_ids': device_ids or []}, ensure_ascii=False, default=str),
            ))
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'健康检查失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='健康检查失败',
        )

    def get_available_serials(self):
        """获取可用设备序列号列表

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_device_config_service_stub()
            resp = stub.GetAvailableSerials(device_pb.GetAvailableSerialsRequest())
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取可用序列号失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='获取可用序列号失败',
        )


# Device 配置 CRUD 模块级单例
device_config_service = _DeviceConfigProxy()
