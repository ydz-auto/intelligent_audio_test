"""api_gateway 端 gRPC 代理对象

把对 task_service / e2e_test_service 的直接 import 调用替换为 gRPC stub 调用。
- ExecutionEngine / ReevaluationExecutor → gRPC ExecutionService
- device_driver_factory → gRPC DeviceService
- audio_service / AudioService / spl_service → gRPC AudioService
- playback_orchestrator → gRPC PlaybackService
- get_device_result_reextractor → gRPC DeviceResultService
"""
import json
from shared.clients.grpc_clients import (
    get_execution_service_stub,
    get_device_service_stub,
    get_audio_service_stub,
    get_playback_service_stub,
    get_device_result_service_stub,
)


class _ExecutionEngineProxy:
    """ExecutionEngine 代理：把方法调用转发到 gRPC ExecutionService"""

    @property
    def event_manager(self):
        return _EventManagerProxy()

    def start_task(self, app, task_id):
        from shared.proto import task_service_pb2
        try:
            stub = get_execution_service_stub()
            resp = stub.StartTask(task_service_pb2.StartTaskRequest(task_id=str(task_id)))
            return resp.success, resp.message
        except Exception as e:
            return False, f"启动任务失败: {str(e)}"

    def control_task(self, app, task_id, action):
        from shared.proto import task_service_pb2
        try:
            stub = get_execution_service_stub()
            if action == 'stop':
                resp = stub.StopTask(task_service_pb2.StopTaskRequest(task_id=str(task_id)))
            elif action == 'pause':
                resp = stub.PauseTask(task_service_pb2.PauseTaskRequest(task_id=str(task_id)))
            elif action == 'resume':
                resp = stub.ResumeTask(task_service_pb2.ResumeTaskRequest(task_id=str(task_id)))
            else:
                return False, f"不支持的控制操作: {action}"
            return resp.success, resp.message
        except Exception as e:
            return False, f"控制任务失败: {str(e)}"

    def remove_from_queue(self, task_id):
        from shared.proto import task_service_pb2
        try:
            stub = get_execution_service_stub()
            resp = stub.RemoveFromQueue(task_service_pb2.RemoveFromQueueRequest(task_id=str(task_id)))
            return resp.success
        except Exception:
            return False


class _EventManagerProxy:
    """EventManager 代理

    calculate_time_estimate 是 shared 层的算法函数（shared.utils.event_manager），
    非跨服务调用，直接 import 使用，无需 gRPC。
    """

    def calculate_time_estimate(self, task):
        from shared.utils.event_manager import event_manager
        return event_manager.calculate_time_estimate(task)


# 模块级单例，供外部直接使用（替代原 execution_engine）
execution_engine = _ExecutionEngineProxy()


class _ReevaluationExecutorProxy:
    """ReevaluationExecutor 代理：把方法调用转发到 gRPC ExecutionService"""

    @classmethod
    def get_instance(cls):
        return cls()

    def submit(self, task_id, reextract_device_output=True, reevaluate_type='all'):
        from shared.proto import task_service_pb2
        try:
            stub = get_execution_service_stub()
            resp = stub.Reevaluate(task_service_pb2.ReevaluateRequest(
                task_id=str(task_id),
                reextract_device_output=reextract_device_output,
                reevaluate_type=reevaluate_type,
            ))
            return resp.success, resp.message
        except Exception as e:
            return False, f"重新评估失败: {str(e)}"

    def _reevaluate_multi_round(self, task_id, result, test_case_id, algorithm_result,
                                 test_type, algorithm_type):
        """多轮用例重新评估"""
        from shared.proto import task_service_pb2
        try:
            stub = get_execution_service_stub()
            resp = stub.ReevaluateMultiRound(task_service_pb2.ReevaluateMultiRoundRequest(
                task_id=str(task_id),
                result_json=json.dumps(result or {}, ensure_ascii=False, default=str),
                test_case_id=str(test_case_id or ''),
                algorithm_result=json.dumps(algorithm_result or {}, ensure_ascii=False, default=str),
                test_type=test_type or 'api',
                algorithm_type=algorithm_type or 'translation',
            ))
            return resp.success, resp.message
        except Exception as e:
            return False, f"多轮重新评估失败: {str(e)}"

    def _reevaluate_single(self, task_id, result_id, test_case_id, algorithm_result,
                           reference_params, test_type, algorithm_type):
        """单轮用例重新评估"""
        from shared.proto import task_service_pb2
        try:
            stub = get_execution_service_stub()
            resp = stub.ReevaluateSingle(task_service_pb2.ReevaluateSingleRequest(
                task_id=str(task_id),
                result_id=str(result_id or ''),
                test_case_id=str(test_case_id or ''),
                algorithm_result=json.dumps(algorithm_result or {}, ensure_ascii=False, default=str),
                reference_params=json.dumps(reference_params or {}, ensure_ascii=False, default=str),
                test_type=test_type or 'api',
                algorithm_type=algorithm_type or 'translation',
            ))
            return resp.success, resp.message
        except Exception as e:
            return False, f"单轮重新评估失败: {str(e)}"


class _DeviceDriverFactoryProxy:
    """device_driver_factory 代理：把方法调用转发到 gRPC DeviceService"""

    def get_driver(self, system, keywords=None, **kwargs):
        """获取 driver 代理对象"""
        return _DriverProxy(system, keywords, **kwargs)

    def get_driver_name_by_keywords(self, system, keywords):
        from shared.proto import e2e_service_pb2
        try:
            stub = get_device_service_stub()
            resp = stub.GetDriverNameByKeywords(e2e_service_pb2.GetDriverNameByKeywordsRequest(
                system=system or '',
                keywords=keywords or '',
            ))
            if resp.success and resp.data:
                return json.loads(resp.data).get('driver_name', '')
            return ''
        except Exception:
            return ''

    def get_registered_keywords(self):
        from shared.proto import e2e_service_pb2
        try:
            stub = get_device_service_stub()
            resp = stub.GetRegisteredKeywords(e2e_service_pb2.GetRegisteredKeywordsRequest())
            if resp.success and resp.data:
                return json.loads(resp.data)
            return []
        except Exception:
            return []

    def get_mock_mode(self):
        from shared.proto import e2e_service_pb2
        try:
            stub = get_device_service_stub()
            resp = stub.GetMockMode(e2e_service_pb2.GetMockModeRequest())
            if resp.success and resp.data:
                return json.loads(resp.data).get('mock_mode', False)
            return False
        except Exception:
            return False


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
        from shared.proto import e2e_service_pb2
        try:
            stub = get_device_service_stub()
            resp = stub.DriverScan(e2e_service_pb2.DriverScanRequest(
                system=self._system or '',
                keywords=self._keywords or '',
            ))
            if resp.success and resp.data:
                return json.loads(resp.data)
            return []
        except Exception:
            return []

    def unlock(self, serial_or_ip):
        """解锁设备"""
        from shared.proto import e2e_service_pb2
        try:
            stub = get_device_service_stub()
            resp = stub.DriverUnlock(e2e_service_pb2.DriverUnlockRequest(
                system=self._system or '',
                keywords=self._keywords or '',
                serial_or_ip=serial_or_ip or '',
            ))
            return resp.success
        except Exception:
            return False

    @property
    def _mock_mode(self):
        """获取 mock 模式状态"""
        from shared.proto import e2e_service_pb2
        try:
            stub = get_device_service_stub()
            resp = stub.GetMockMode(e2e_service_pb2.GetMockModeRequest())
            if resp.success and resp.data:
                return json.loads(resp.data).get('mock_mode', False)
            return False
        except Exception:
            return False

    @_mock_mode.setter
    def _mock_mode(self, value):
        """设置 mock 模式"""
        from shared.proto import e2e_service_pb2
        try:
            stub = get_device_service_stub()
            stub.SetMockMode(e2e_service_pb2.SetMockModeRequest(
                mock_mode=bool(value),
            ))
        except Exception:
            pass


class _AudioServiceProxy:
    """audio_service / AudioService 代理：把方法调用转发到 gRPC AudioService"""

    def play_audio(self, task_id=None, file_path=None, device_index=0, channel_index=0,
                   gain=0.0, player_type='dry', **kwargs):
        from shared.proto import e2e_service_pb2
        try:
            stub = get_audio_service_stub()
            play_config = {
                'file_path': file_path,
                'device_index': device_index,
                'channel_index': channel_index,
                'gain': gain,
                'player_type': player_type,
                'kwargs': kwargs,
            }
            resp = stub.PlayAudio(e2e_service_pb2.PlayAudioRequest(
                task_id=str(task_id or ''),
                audio_file_paths=json.dumps([file_path]) if file_path else '[]',
                play_config=json.dumps(play_config)
            ))
            return _CompletedFuture(resp.success)
        except Exception as e:
            return _CompletedFuture(False, str(e))

    def stop_task_audio(self, task_id):
        from shared.proto import e2e_service_pb2
        try:
            stub = get_audio_service_stub()
            stub.StopAudio(e2e_service_pb2.StopAudioRequest(task_id=str(task_id)))
        except Exception:
            pass

    def get_audio_info(self, task_id, audio_file_path):
        from shared.proto import e2e_service_pb2
        try:
            stub = get_audio_service_stub()
            resp = stub.GetAudioInfo(e2e_service_pb2.GetAudioInfoRequest(
                task_id=str(task_id),
                audio_file_path=audio_file_path,
            ))
            if resp.success and resp.data:
                return json.loads(resp.data)
            return None
        except Exception:
            return None

    def get_all_physical_devices(self):
        """扫描所有可用的物理输出设备及通道"""
        from shared.proto import e2e_service_pb2
        try:
            stub = get_audio_service_stub()
            resp = stub.GetPhysicalDevices(e2e_service_pb2.GetPhysicalDevicesRequest())
            if resp.success and resp.data:
                return json.loads(resp.data)
            return []
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"get_all_physical_devices failed: {e}")
            return []

    def get_device_index(self, unique_id):
        """根据唯一标识获取物理设备索引"""
        from shared.proto import e2e_service_pb2
        try:
            stub = get_audio_service_stub()
            resp = stub.GetDeviceIndex(e2e_service_pb2.GetDeviceIndexRequest(
                unique_id=unique_id or '',
            ))
            if resp.success and resp.data:
                return json.loads(resp.data).get('device_index')
            return None
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"get_device_index failed: {e}")
            return None

    def stop_task_audio_by_pattern(self, task_id_pattern, player_type_pattern=None):
        """按模式停止音频播放"""
        from shared.proto import e2e_service_pb2
        try:
            stub = get_audio_service_stub()
            resp = stub.StopAudioByPattern(e2e_service_pb2.StopAudioByPatternRequest(
                task_id_pattern=task_id_pattern or '',
                player_type_pattern=player_type_pattern or '',
            ))
            return resp.success
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"stop_task_audio_by_pattern failed: {e}")
            return False

    @property
    def active_players(self):
        """获取活跃播放器快照"""
        from shared.proto import e2e_service_pb2
        try:
            stub = get_audio_service_stub()
            resp = stub.GetPlayStatus(e2e_service_pb2.GetPlayStatusRequest(task_id=''))
            if resp.success and resp.data:
                return json.loads(resp.data).get('players', {})
            return {}
        except Exception:
            return {}

    @property
    def _device_cache(self):
        """设备缓存属性占位 - 设为 None 触发重新扫描（兼容原代码）"""
        return None

    @_device_cache.setter
    def _device_cache(self, value):
        """_device_cache setter 占位 - 实际缓存在 e2e_test_service 端管理"""
        pass


# AudioService 类别名，兼容 from e2e_test_service.audio.audio_engine import AudioService
AudioService = _AudioServiceProxy
# 模块级单例 audio_service
audio_service = _AudioServiceProxy()


class _SplServiceProxy:
    """spl_service 代理：把方法调用转发到 gRPC AudioService 的 SPL 相关 RPC"""

    def measure_spl(self, task_id=None, **kwargs):
        from shared.proto import e2e_service_pb2
        try:
            stub = get_audio_service_stub()
            resp = stub.MeasureSPL(e2e_service_pb2.MeasureSPLRequest(
                task_id=str(task_id or ''),
                measure_config=json.dumps(kwargs)
            ))
            if resp.success and resp.data:
                return json.loads(resp.data)
            return None
        except Exception:
            return None

    def start_spl(self, task_id=None, **kwargs):
        from shared.proto import e2e_service_pb2
        try:
            stub = get_audio_service_stub()
            resp = stub.StartSPL(e2e_service_pb2.StartSPLRequest(
                task_id=str(task_id or ''),
                spl_config=json.dumps(kwargs)
            ))
            return resp.success
        except Exception:
            return False

    def stop_spl(self, task_id=None, **kwargs):
        from shared.proto import e2e_service_pb2
        try:
            stub = get_audio_service_stub()
            resp = stub.StopSPL(e2e_service_pb2.StopSPLRequest(task_id=str(task_id or '')))
            return resp.success
        except Exception:
            return False

    def spl_to_gain(self, mapping_id, target_spl, app=None):
        """通过 gRPC MeasureSPL 计算 SPL 到增益的映射"""
        from shared.proto import e2e_service_pb2
        try:
            stub = get_audio_service_stub()
            measure_config = {'mapping_id': mapping_id, 'target_spl': target_spl}
            resp = stub.MeasureSPL(e2e_service_pb2.MeasureSPLRequest(
                task_id='',
                measure_config=json.dumps(measure_config)
            ))
            if resp.success and resp.data:
                result = json.loads(resp.data)
                return result.get('gain', 1.0)
            return 1.0
        except Exception:
            return 1.0


spl_service = _SplServiceProxy()


class _PlaybackOrchestratorProxy:
    """playback_orchestrator 代理：把方法调用转发到 gRPC PlaybackService"""

    def preview(self, audio_configs=None, case_config=None, task_id=None,
                offset=0, overlap_rate=0, overlap_time=0, **kwargs):
        """预览播放编排"""
        from shared.proto import e2e_service_pb2
        try:
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
            resp = stub.StartPlayback(e2e_service_pb2.StartPlaybackRequest(
                task_id=str(task_id or ''),
                playback_config=json.dumps(playback_config)
            ))
            if not resp.success or not resp.data:
                return None
            return json.loads(resp.data)
        except Exception:
            return None

    def play_round(self, round_config=None, task_id=None, case_config=None,
                   test_case_id=None, round_number=None, **kwargs):
        from shared.proto import e2e_service_pb2
        try:
            stub = get_playback_service_stub()
            playback_config = {
                'mode': 'round',
                'round_config': round_config,
                'case_config': case_config,
                'test_case_id': test_case_id,
                'round_number': round_number,
                'kwargs': kwargs,
            }
            resp = stub.StartPlayback(e2e_service_pb2.StartPlaybackRequest(
                task_id=str(task_id or ''),
                playback_config=json.dumps(playback_config)
            ))
            if not resp.success or not resp.data:
                return None
            return json.loads(resp.data)
        except Exception:
            return None

    def play_voiceprint(self, voiceprint_config, task_id=None, **kwargs):
        from shared.proto import e2e_service_pb2
        try:
            stub = get_playback_service_stub()
            playback_config = {
                'mode': 'voiceprint',
                'vp_config': voiceprint_config,
                'kwargs': kwargs,
            }
            resp = stub.StartPlayback(e2e_service_pb2.StartPlaybackRequest(
                task_id=str(task_id or ''),
                playback_config=json.dumps(playback_config)
            ))
            return resp.success
        except Exception:
            return False

    def stop_playback(self, task_id=None, **kwargs):
        from shared.proto import e2e_service_pb2
        try:
            stub = get_playback_service_stub()
            stub.StopPlayback(e2e_service_pb2.StopPlaybackRequest(task_id=str(task_id or '')))
        except Exception:
            pass


playback_orchestrator = _PlaybackOrchestratorProxy()


class _DeviceResultReextractorProxy:
    """get_device_result_reextractor 返回的对象的代理"""

    def reextract_for_task(self, task_id, evaluation_status=None):
        from shared.proto import e2e_service_pb2
        try:
            stub = get_device_result_service_stub()
            reextract_config = {
                'evaluation_status': evaluation_status,
            }
            resp = stub.ReextractResult(e2e_service_pb2.ReextractResultRequest(
                task_id=str(task_id),
                reextract_config=json.dumps(reextract_config)
            ))
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
            }
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None}


def get_device_result_reextractor():
    """原 get_device_result_reextractor 返回单例，此处返回代理"""
    return _DeviceResultReextractorProxy()


def get_device_result_collector():
    """原 get_device_result_collector 返回单例，此处返回代理"""
    return _DeviceResultCollectorApiProxy()


class _DeviceResultCollectorApiProxy:
    """设备结果采集器代理（api_gateway 端）"""

    def convert_results(self, all_results, algorithm_type):
        from shared.proto import e2e_service_pb2
        try:
            stub = get_device_result_service_stub()
            collect_config = {
                'action': 'convert_results',
                'all_results': all_results,
                'algorithm_type': algorithm_type,
            }
            resp = stub.CollectResult(e2e_service_pb2.CollectResultRequest(
                task_id='',
                collect_config=json.dumps(collect_config)
            ))
            if not resp.success or not resp.data:
                return all_results
            return json.loads(resp.data)
        except Exception:
            return all_results

    def build_case_result_log(self, algorithm_type, res, ref_fields=None, **kwargs):
        from shared.proto import e2e_service_pb2
        try:
            stub = get_device_result_service_stub()
            collect_config = {
                'action': 'build_case_result_log',
                'algorithm_type': algorithm_type,
                'res': res,
                'ref_fields': ref_fields,
                'kwargs': kwargs,
            }
            resp = stub.CollectResult(e2e_service_pb2.CollectResultRequest(
                task_id='',
                collect_config=json.dumps(collect_config)
            ))
            if resp.success and resp.data:
                return resp.data
            return ''
        except Exception:
            return ''


class _CompletedFuture:
    """已完成的 future 代理：兼容原 audio_service.play_audio 返回 future 的用法"""

    def __init__(self, success, error=None):
        self._success = success
        self._error = error

    def result(self, timeout=None):
        if not self._success:
            raise Exception(self._error or "audio play failed")
        return self._success
