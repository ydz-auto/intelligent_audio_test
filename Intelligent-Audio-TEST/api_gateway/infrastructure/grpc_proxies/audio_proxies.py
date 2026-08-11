"""音频服务代理：_AudioServiceProxy、_SplServiceProxy、_PlaybackOrchestratorProxy、_PlaybackConfigProxy、_SPLConfigProxy、_AudioConfigProxy 及相关单例/别名。"""
import json

from shared.clients.grpc_clients import (
    get_audio_service_stub,
    get_playback_service_stub,
    get_playback_config_service_stub,
    get_spl_config_service_stub,
    get_audio_config_service_stub,
)

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


class _SplServiceProxy:
    """spl_service 代理：把方法调用转发到 gRPC AudioService 的 SPL 相关 RPC"""

    def measure_spl(self, task_id=None, **kwargs):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_service_stub()
            resp = stub.MeasureSPL(audio_pb.MeasureSPLRequest(
                task_id=str(task_id or ''),
                measure_config=json.dumps(kwargs)
            ))
            if resp.success and resp.data:
                return json.loads(resp.data)
            return None

        return _grpc_call(_call, default_return=None, error_msg_prefix="测量 SPL 失败")

    def start_spl(self, task_id=None, **kwargs):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_service_stub()
            resp = stub.StartSPL(audio_pb.StartSPLRequest(
                task_id=str(task_id or ''),
                spl_config=json.dumps(kwargs)
            ))
            return resp.success

        return _grpc_call(_call, default_return=False, error_msg_prefix="启动 SPL 失败")

    def stop_spl(self, task_id=None, **kwargs):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_service_stub()
            resp = stub.StopSPL(audio_pb.StopSPLRequest(task_id=str(task_id or '')))
            return resp.success

        return _grpc_call(_call, default_return=False, error_msg_prefix="停止 SPL 失败")

    def spl_to_gain(self, mapping_id, target_spl, app=None):
        """通过 gRPC MeasureSPL 计算 SPL 到增益的映射"""
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_service_stub()
            measure_config = {'mapping_id': mapping_id, 'target_spl': target_spl}
            resp = stub.MeasureSPL(audio_pb.MeasureSPLRequest(
                task_id='',
                measure_config=json.dumps(measure_config)
            ))
            if resp.success and resp.data:
                result = json.loads(resp.data)
                return result.get('gain', 1.0)
            return 1.0

        return _grpc_call(_call, default_return=1.0, error_msg_prefix="SPL 转增益失败")


spl_service = _SplServiceProxy()


class _PlaybackOrchestratorProxy:
    """playback_orchestrator 代理：把方法调用转发到 gRPC PlaybackService"""

    def preview(self, audio_configs=None, case_config=None, task_id=None,
                offset=0, overlap_rate=0, overlap_time=0, **kwargs):
        """预览播放编排"""
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_playback_service_stub()
            playback_config = {
                'mode': 'preview',
                'audio_configs': audio_configs,
                'case_config': case_config,
                'offset': offset,
                'overlap_rate': overlap_rate,
                'overlap_time': overlap_time,
                'kwargs': kwargs,
            }
            resp = stub.StartPlayback(audio_pb.StartPlaybackRequest(
                task_id=str(task_id or ''),
                playback_config=json.dumps(playback_config)
            ))
            if not resp.success or not resp.data:
                return None
            return json.loads(resp.data)

        return _grpc_call(_call, default_return=None, error_msg_prefix="预览播放编排失败")

    def play_round(self, round_config=None, task_id=None, case_config=None,
                   test_case_id=None, round_number=None, **kwargs):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_playback_service_stub()
            playback_config = {
                'mode': 'round',
                'round_config': round_config,
                'case_config': case_config,
                'test_case_id': test_case_id,
                'round_number': round_number,
                'kwargs': kwargs,
            }
            resp = stub.StartPlayback(audio_pb.StartPlaybackRequest(
                task_id=str(task_id or ''),
                playback_config=json.dumps(playback_config)
            ))
            if not resp.success or not resp.data:
                return None
            return json.loads(resp.data)

        return _grpc_call(_call, default_return=None, error_msg_prefix="轮次播放失败")

    def play_voiceprint(self, voiceprint_config, task_id=None, **kwargs):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_playback_service_stub()
            playback_config = {
                'mode': 'voiceprint',
                'vp_config': voiceprint_config,
                'kwargs': kwargs,
            }
            resp = stub.StartPlayback(audio_pb.StartPlaybackRequest(
                task_id=str(task_id or ''),
                playback_config=json.dumps(playback_config)
            ))
            return resp.success

        return _grpc_call(_call, default_return=False, error_msg_prefix="声纹播放失败")

    def stop_playback(self, task_id=None, **kwargs):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_playback_service_stub()
            stub.StopPlayback(audio_pb.StopPlaybackRequest(task_id=str(task_id or '')))

        _grpc_call(_call, default_return=None, log_error=False)


playback_orchestrator = _PlaybackOrchestratorProxy()


# ==================== Playback 配置 CRUD 代理 ====================

class _PlaybackConfigProxy:
    """Playback 配置 CRUD 代理：把方法调用转发到 gRPC PlaybackConfigService

    替代原 PlaybackCommandService/PlaybackQueryService 直接操作 DB 的方式，
    网关侧不再 import PlaybackDevice 模型和 get_db_session()，统一走 gRPC。
    """

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

    def get_all(self, page=1, per_page=10, keyword=None, device_type=None):
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


# Playback 配置 CRUD 模块级单例
playback_config_service = _PlaybackConfigProxy()


# ==================== SPL 配置 CRUD 代理 ====================

class _SPLConfigProxy:
    """SPL 配置 CRUD 代理：把方法调用转发到 gRPC SPLConfigService

    替代原 SPLCommandService/SPLQueryService 直接操作 DB 的方式，
    网关侧不再 import SPLMapping 模型和 get_db_session()，统一走 gRPC。
    """

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


# ==================== Audio 配置 CRUD 代理 ====================

class _AudioConfigProxy:
    """Audio 配置 CRUD 代理：把方法调用转发到 gRPC AudioConfigService

    替代原 AudioCommandService/AudioQueryService/AudioUploadService/
    AudioConvertService/AudioPreviewService 直接操作 DB 的方式，
    网关侧不再 import Audio 模型和 get_db_session()，统一走 gRPC。
    所有方法返回 dict: {success, message, data, code}
    """

    def _resp(self, resp):
        """统一解析 AudioConfigResponse 为 dict"""
        return {
            'success': resp.success,
            'message': resp.message,
            'data': json.loads(resp.data) if resp.data else None,
        }

    # ---------- 写操作 ----------

    def update_metadata(self, audio_id, data):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.UpdateAudioMetadata(audio_pb.UpdateAudioMetadataRequest(
                audio_id=int(audio_id),
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'更新音频元数据失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='更新音频元数据失败',
        )

    def batch_update_annotations(self, data):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.BatchUpdateAnnotations(audio_pb.BatchUpdateAnnotationsRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'批量更新标注失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='批量更新标注失败',
        )

    def batch_action(self, data):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.BatchActionAudios(audio_pb.BatchActionAudiosRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'批量操作失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='批量操作失败',
        )

    def delete(self, audio_id):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.DeleteAudio(audio_pb.DeleteAudioRequest(
                audio_id=int(audio_id),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'删除音频失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='删除音频失败',
        )

    def update_audio_algorithms(self, audio_id, data):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.UpdateAudioAlgorithms(audio_pb.UpdateAudioAlgorithmsRequest(
                audio_id=int(audio_id),
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'更新算法关联失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='更新算法关联失败',
        )

    def batch_update_audio_algorithms(self, data):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.BatchUpdateAudioAlgorithms(audio_pb.BatchUpdateAudioAlgorithmsRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'批量更新算法关联失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='批量更新算法关联失败',
        )

    # ---------- 读操作 ----------

    def get_all_tags(self):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.GetAllAudioTags(audio_pb.GetAllAudioTagsRequest())
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取标签失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='获取标签失败',
        )

    def get_all(self, params):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.ListAudios(audio_pb.ListAudiosRequest(
                data=json.dumps(params or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'查询音频列表失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='查询音频列表失败',
        )

    def get_one(self, audio_id):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.GetAudio(audio_pb.GetAudioRequest(
                audio_id=int(audio_id),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'查询音频详情失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='查询音频详情失败',
        )

    def get_by_ids(self, data):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.GetAudiosByIds(audio_pb.GetAudiosByIdsRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'按ID查询音频失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='按ID查询音频失败',
        )

    def get_by_md5(self, data):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.GetAudioByMD5(audio_pb.GetAudioByMD5Request(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'按MD5查询音频失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='按MD5查询音频失败',
        )

    def get_all_ids(self, params):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.GetAllAudioIds(audio_pb.GetAllAudioIdsRequest(
                data=json.dumps(params or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取音频ID列表失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='获取音频ID列表失败',
        )

    def stream_audio(self, audio_id, data=None):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.StreamAudio(audio_pb.StreamAudioRequest(
                audio_id=int(audio_id),
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'流式播放音频失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='流式播放音频失败',
        )

    def stream_audio_by_path(self, data):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.StreamAudioByPath(audio_pb.StreamAudioByPathRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'按路径流式播放失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='按路径流式播放失败',
        )

    def get_audio_algorithms(self, audio_id):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.GetAudioAlgorithms(audio_pb.GetAudioAlgorithmsRequest(
                audio_id=int(audio_id),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取音频算法失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='获取音频算法失败',
        )

    def get_folder_tree(self, data):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.GetAudioFolderTree(audio_pb.GetAudioFolderTreeRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取音频目录树失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='获取音频目录树失败',
        )

    # ---------- 上传操作 ----------

    def presign_upload(self, data):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.PresignUpload(audio_pb.PresignUploadRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'预签名上传失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='预签名上传失败',
        )

    def presign_part(self, data):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.PresignPart(audio_pb.PresignPartRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'预签名分片失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='预签名分片失败',
        )

    def complete_direct_upload(self, data):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.CompleteDirectUpload(audio_pb.CompleteDirectUploadRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'完成直传失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='完成直传失败',
        )

    def init_upload_task(self, data=None):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.InitUploadTask(audio_pb.InitUploadTaskRequest())
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'初始化上传任务失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='初始化上传任务失败',
        )

    def register_upload_file(self, data):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.RegisterUploadFile(audio_pb.RegisterUploadFileRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'注册上传文件失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='注册上传文件失败',
        )

    def upload_chunk(self, data):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.UploadChunk(audio_pb.UploadChunkRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'上传分片失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='上传分片失败',
        )

    def merge_chunks(self, data):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.MergeChunks(audio_pb.MergeChunksRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'合并分片失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='合并分片失败',
        )

    def get_upload_progress(self, data):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.GetUploadProgress(audio_pb.GetUploadProgressRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取上传进度失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='获取上传进度失败',
        )

    def url_import(self, data):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.UrlImport(audio_pb.UrlImportRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'URL导入失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='URL导入失败',
        )

    # ---------- 转换/预览操作 ----------

    def convert_audio(self, audio_id, data):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.ConvertAudio(audio_pb.ConvertAudioRequest(
                audio_id=int(audio_id),
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'转换音频失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='转换音频失败',
        )

    def preview_audio(self, audio_id, data):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.PreviewAudio(audio_pb.PreviewAudioRequest(
                audio_id=int(audio_id),
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'预览音频失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='预览音频失败',
        )

    def stop_preview_audio(self, audio_id):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.StopPreviewAudio(audio_pb.StopPreviewAudioRequest(
                audio_id=int(audio_id),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'停止预览失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='停止预览失败',
        )


# Audio 配置 CRUD 模块级单例
audio_config_service = _AudioConfigProxy()
