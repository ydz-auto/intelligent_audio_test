"""SPL 配置 CRUD 代理：_SPLConfigProxy 及模块级单例 spl_config_service。

把方法调用转发到 gRPC SPLConfigService。
替代原 SPLCommandService/SPLQueryService 直接操作 DB 的方式，
网关侧不再 import SPLMapping 模型和 get_db_session()，统一走 gRPC。
"""
import json

from shared.clients.grpc_clients import get_spl_config_service_stub

from ._common import _grpc_call


class _SPLConfigProxy:
    """SPL 配置 CRUD 代理：把方法调用转发到 gRPC SPLConfigService"""

    def create(self, data):
        """创建 SPL 映射

        Args:
            data: SPL 映射配置参数字典

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_spl_config_service_stub()
            resp = stub.CreateSPLMapping(device_pb.CreateSPLMappingRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'创建SPL映射失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='创建SPL映射失败',
        )

    def update(self, mapping_id, data):
        """更新 SPL 映射

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_spl_config_service_stub()
            resp = stub.UpdateSPLMapping(device_pb.UpdateSPLMappingRequest(
                mapping_id=int(mapping_id),
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'更新SPL映射失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='更新SPL映射失败',
        )

    def delete(self, mapping_id):
        """删除 SPL 映射（软删除）

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_spl_config_service_stub()
            resp = stub.DeleteSPLMapping(device_pb.DeleteSPLMappingRequest(
                mapping_id=int(mapping_id),
            ))
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'删除SPL映射失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='删除SPL映射失败',
        )

    def get_all(self, page=1, per_page=10, keyword=None,
                calibration_status=None, device_id=None):
        """分页查询 SPL 映射列表

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_spl_config_service_stub()
            resp = stub.ListSPLMappings(device_pb.ListSPLMappingsRequest(
                page=int(page or 1),
                per_page=int(per_page or 10),
                keyword=keyword or '',
                calibration_status=calibration_status or '',
                device_id=int(device_id) if device_id else 0,
            ))
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'查询SPL映射列表失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='查询SPL映射列表失败',
        )

    def get_one(self, mapping_id):
        """查询单个 SPL 映射详情

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_spl_config_service_stub()
            resp = stub.GetSPLMapping(device_pb.GetSPLMappingRequest(
                mapping_id=int(mapping_id),
            ))
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'查询SPL映射详情失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='查询SPL映射详情失败',
        )

    def get_history(self, mapping_id):
        """获取校准历史

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_spl_config_service_stub()
            resp = stub.GetSPLHistory(device_pb.GetSPLHistoryRequest(
                mapping_id=int(mapping_id),
            ))
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取校准历史失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='获取校准历史失败',
        )

    def get_calibration_data(self, mapping_id):
        """获取详细校准数据（最新）

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_spl_config_service_stub()
            resp = stub.GetSPLCalibrationData(device_pb.GetSPLCalibrationDataRequest(
                mapping_id=int(mapping_id),
            ))
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取校准数据失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='获取校准数据失败',
        )

    def get_stats(self):
        """获取 SPL 统计信息

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_spl_config_service_stub()
            resp = stub.GetSPLStats(device_pb.GetSPLStatsRequest())
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取SPL统计失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='获取SPL统计失败',
        )

    def get_by_device(self, device_id):
        """按设备 ID 获取 SPL 映射列表

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_spl_config_service_stub()
            resp = stub.GetSPLByDevice(device_pb.GetSPLByDeviceRequest(
                device_id=int(device_id),
            ))
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'按设备查询SPL失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='按设备查询SPL失败',
        )

    def calibrate(self, mapping_id):
        """执行 SPL 校准流程

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_spl_config_service_stub()
            resp = stub.CalibrateSPL(device_pb.CalibrateSPLRequest(
                mapping_id=int(mapping_id),
            ))
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'SPL校准失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='SPL校准失败',
        )

    def play_test_tone(self, data=None):
        """播放测试音

        Args:
            data: 测试音参数字典（gain_value, gain_offset, target_spl, unique_id, mapping_id）

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_spl_config_service_stub()
            resp = stub.PlayTestTone(device_pb.PlayTestToneRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'播放测试音失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='播放测试音失败',
        )

    def stop_test_tone(self, data=None):
        """停止测试音

        Args:
            data: 参数字典（unique_id）

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_spl_config_service_stub()
            resp = stub.StopTestTone(device_pb.StopTestToneRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'停止测试音失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='停止测试音失败',
        )


# SPL 配置 CRUD 模块级单例
spl_config_service = _SPLConfigProxy()
