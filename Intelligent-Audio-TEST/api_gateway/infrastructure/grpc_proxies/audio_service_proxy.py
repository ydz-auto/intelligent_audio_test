"""audio_service 代理：_AudioServiceProxy 及模块级单例 audio_service / 别名 AudioService。"""
import json

from shared.clients.grpc_clients import get_audio_service_stub

from ._common import _grpc_call, _CompletedFuture


class _AudioServiceProxy:
    """audio_service / AudioService 代理：把方法调用转发到 gRPC AudioService"""

    def play_audio(self, task_id=None, file_path=None, device_index=0, channel_index=0,
                   gain=0.0, player_type='dry', **kwargs):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_service_stub()
            play_config = {
                'file_path': file_path,
                'device_index': device_index,
                'channel_index': channel_index,
                'gain': gain,
                'player_type': player_type,
                'kwargs': kwargs,
            }
            resp = stub.PlayAudio(audio_pb.PlayAudioRequest(
                task_id=str(task_id or ''),
                audio_file_paths=json.dumps([file_path]) if file_path else '[]',
                play_config=json.dumps(play_config)
            ))
            return _CompletedFuture(resp.success)

        return _grpc_call(
            _call,
            default_return=lambda e: _CompletedFuture(False, str(e)),
            error_msg_prefix="播放音频失败",
        )

    def stop_task_audio(self, task_id):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_service_stub()
            stub.StopAudio(audio_pb.StopAudioRequest(task_id=str(task_id)))

        _grpc_call(_call, default_return=None, log_error=False)

    def get_audio_info(self, task_id, audio_file_path):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_service_stub()
            resp = stub.GetAudioInfo(audio_pb.GetAudioInfoRequest(
                task_id=str(task_id),
                audio_file_path=audio_file_path,
            ))
            if resp.success and resp.data:
                return json.loads(resp.data)
            return None

        return _grpc_call(_call, default_return=None, error_msg_prefix="获取音频信息失败")

    def get_all_physical_devices(self):
        """扫描所有可用的物理输出设备及通道"""
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_service_stub()
            resp = stub.GetPhysicalDevices(audio_pb.GetPhysicalDevicesRequest())
            if resp.success and resp.data:
                return json.loads(resp.data)
            return []

        return _grpc_call(_call, default_return=[], error_msg_prefix="get_all_physical_devices failed")

    def get_device_index(self, unique_id):
        """根据唯一标识获取物理设备索引"""
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_service_stub()
            resp = stub.GetDeviceIndex(audio_pb.GetDeviceIndexRequest(
                unique_id=unique_id or '',
            ))
            if resp.success and resp.data:
                return json.loads(resp.data).get('device_index')
            return None

        return _grpc_call(_call, default_return=None, error_msg_prefix="get_device_index failed")

    def stop_task_audio_by_pattern(self, task_id_pattern, player_type_pattern=None):
        """按模式停止音频播放"""
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_service_stub()
            resp = stub.StopAudioByPattern(audio_pb.StopAudioByPatternRequest(
                task_id_pattern=task_id_pattern or '',
                player_type_pattern=player_type_pattern or '',
            ))
            return resp.success

        return _grpc_call(_call, default_return=False, error_msg_prefix="stop_task_audio_by_pattern failed")

    @property
    def active_players(self):
        """获取活跃播放器快照"""
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_service_stub()
            resp = stub.GetPlayStatus(audio_pb.GetPlayStatusRequest(task_id=''))
            if resp.success and resp.data:
                return json.loads(resp.data).get('players', {})
            return {}

        return _grpc_call(_call, default_return={}, error_msg_prefix="获取活跃播放器失败")

    @property
    def _device_cache(self):
        """设备缓存属性占位 - 设为 None 触发重新扫描（兼容原代码）"""
        return None

    @_device_cache.setter
    def _device_cache(self, value):
        """_device_cache setter 占位 - 实际缓存在 audio_service 端管理"""
        pass


# AudioService 类别名，兼容历史 import 路径
AudioService = _AudioServiceProxy
# 模块级单例 audio_service
audio_service = _AudioServiceProxy()
