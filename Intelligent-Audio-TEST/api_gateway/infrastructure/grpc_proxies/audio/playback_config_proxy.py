"""Playback 配置 CRUD 代理：_PlaybackConfigProxy 及模块级单例 playback_config_service。

把方法调用转发到 gRPC PlaybackConfigService。
替代原 PlaybackCommandService/PlaybackQueryService 直接操作 DB 的方式，
网关侧不再 import PlaybackDevice 模型和 get_db_session()，统一走 gRPC。
"""
import json

from shared.clients.grpc_clients import get_playback_config_service_stub

from .._common import _grpc_call


class _PlaybackConfigProxy:
    """Playback 配置 CRUD 代理：把方法调用转发到 gRPC PlaybackConfigService"""

    @property
    def stub(self):
        """获取 PlaybackConfigService stub（供需要直接调 RPC 的场景使用）"""
        return get_playback_config_service_stub()

    def create(self, data):
        """创建播放设备

        Args:
            data: 播放设备配置参数字典

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_playback_config_service_stub()
            resp = stub.CreatePlaybackDevice(device_pb.CreatePlaybackDeviceRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'创建播放设备失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='创建播放设备失败',
        )

    def update(self, device_id, data):
        """更新播放设备

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_playback_config_service_stub()
            resp = stub.UpdatePlaybackDevice(device_pb.UpdatePlaybackDeviceRequest(
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
            default_return=lambda e: {'success': False, 'message': f'更新播放设备失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='更新播放设备失败',
        )

    def delete(self, device_id):
        """删除播放设备（软删除）

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_playback_config_service_stub()
            resp = stub.DeletePlaybackDevice(device_pb.DeletePlaybackDeviceRequest(
                device_id=int(device_id),
            ))
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'删除播放设备失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='删除播放设备失败',
        )

    def get_all(self, page=1, per_page=10, keyword=None, device_type=None, lab_id=None):
        """分页查询播放设备列表

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_playback_config_service_stub()
            resp = stub.ListPlaybackDevices(device_pb.ListPlaybackDevicesRequest(
                page=int(page or 1),
                per_page=int(per_page or 10),
                keyword=keyword or '',
                device_type=device_type or '',
                lab_id=int(lab_id) if lab_id else 0,
            ))
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'查询播放设备列表失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='查询播放设备列表失败',
        )

    def get_one(self, device_id):
        """查询单个播放设备详情

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_playback_config_service_stub()
            resp = stub.GetPlaybackDevice(device_pb.GetPlaybackDeviceRequest(
                device_id=int(device_id),
            ))
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'查询播放设备详情失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='查询播放设备详情失败',
        )

    def scan(self):
        """扫描可用的物理播放通道

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_playback_config_service_stub()
            resp = stub.ScanPlaybackDevices(device_pb.ScanPlaybackDevicesRequest())
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'扫描播放设备失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='扫描播放设备失败',
        )

    def check_status(self):
        """检查所有播放设备状态

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_playback_config_service_stub()
            resp = stub.CheckPlaybackStatus(device_pb.CheckPlaybackStatusRequest())
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'检查播放设备状态失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='检查播放设备状态失败',
        )

    def associate_spl(self, device_id, spl_mapping_id):
        """关联 SPL 映射

        Args:
            device_id: 播放设备 ID
            spl_mapping_id: SPL 映射 ID

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_playback_config_service_stub()
            resp = stub.AssociateSPL(device_pb.AssociateSPLRequest(
                device_id=int(device_id),
                data=json.dumps({'spl_mapping_id': int(spl_mapping_id)}, ensure_ascii=False, default=str),
            ))
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'关联SPL失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='关联SPL失败',
        )

    def test(self, device_id, data=None):
        """测试播放设备

        Args:
            device_id: 播放设备 ID
            data: 测试参数字典（audio_id, spl 等）

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_playback_config_service_stub()
            resp = stub.TestPlaybackDevice(device_pb.TestPlaybackDeviceRequest(
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
            default_return=lambda e: {'success': False, 'message': f'测试播放设备失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='测试播放设备失败',
        )

    def stop_test(self, device_id):
        """停止播放设备测试

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_playback_config_service_stub()
            resp = stub.StopPlaybackTest(device_pb.StopPlaybackTestRequest(
                device_id=int(device_id),
            ))
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'停止播放设备测试失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='停止播放设备测试失败',
        )

    # ---- 控制端点（INT-1579，契约 §2.1/§2.2/§2.5）----
    # 这批响应带 code 业务码（200/400/404/409），网关据此映射 HTTP 状态码

    def restart(self, device_id):
        """重启播放设备（音频通道层重开 + 重新枚举）

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_playback_config_service_stub()
            resp = stub.RestartPlaybackDevice(device_pb.RestartPlaybackDeviceRequest(
                device_id=int(device_id),
            ))
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
                'code': resp.code or (200 if resp.success else 400),
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'重新连接音频通道失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='重新连接音频通道失败',
        )

    def reset_config(self, device_id):
        """重置播放设备配置（按硬件重新探测采样率与通道索引）

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_playback_config_service_stub()
            resp = stub.ResetPlaybackDeviceConfig(device_pb.ResetPlaybackDeviceConfigRequest(
                device_id=int(device_id),
            ))
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
                'code': resp.code or (200 if resp.success else 400),
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'重置播放设备配置失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='重置播放设备配置失败',
        )

    def diagnosis(self, device_id):
        """播放设备诊断（只读）

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_playback_config_service_stub()
            resp = stub.GetPlaybackDeviceDiagnosis(device_pb.GetPlaybackDeviceDiagnosisRequest(
                device_id=int(device_id),
            ))
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
                'code': resp.code or (200 if resp.success else 400),
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'播放设备诊断失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='播放设备诊断失败',
        )

    def repair(self, device_id, actions):
        """修复播放设备（仅 re-enumerate / reopen-channel 两个安全动作）

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import device_service_pb2 as device_pb

        def _call():
            stub = get_playback_config_service_stub()
            resp = stub.RepairPlaybackDevice(device_pb.RepairPlaybackDeviceRequest(
                device_id=int(device_id),
                data=json.dumps({'actions': list(actions or [])}, ensure_ascii=False, default=str),
            ))
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
                'code': resp.code or (200 if resp.success else 400),
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'修复播放设备失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='修复播放设备失败',
        )


# Playback 配置 CRUD 模块级单例
playback_config_service = _PlaybackConfigProxy()
