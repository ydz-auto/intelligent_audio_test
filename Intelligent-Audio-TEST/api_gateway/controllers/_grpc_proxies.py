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
    """ExecutionEngine 代理：把方法调用转发到 gRPC ExecutionService

    原 ExecutionEngine 单例提供：start_task / control_task / remove_from_queue /
    event_manager.calculate_time_estimate 等方法和属性。
    gRPC 只暴露 StartTask / StopTask / GetTaskStatus / Reevaluate 等 RPC。
    """

    @property
    def event_manager(self):
        # event_manager.calculate_time_estimate 原为本地估算，
        # gRPC 暂无对应 RPC，返回一个哑代理
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
            else:
                # TODO: ExecutionService proto 暂无 pause/resume RPC，需扩展
                resp = stub.GetTaskStatus(task_service_pb2.GetTaskStatusRequest(task_id=str(task_id)))
            return resp.success, resp.message
        except Exception as e:
            return False, f"控制任务失败: {str(e)}"

    def remove_from_queue(self, task_id):
        # TODO: ExecutionService proto 暂无 remove_from_queue RPC，需扩展
        pass


class _EventManagerProxy:
    """EventManager 代理：原 event_manager.calculate_time_estimate 等方法的 gRPC 封装"""

    def calculate_time_estimate(self, task):
        # TODO: ExecutionService proto 暂无对应 RPC，需扩展
        # 返回一个默认估算值，避免阻断流程
        return None


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
            reevaluate_config = {
                'reextract_device_output': reextract_device_output,
                'reevaluate_type': reevaluate_type,
            }
            resp = stub.Reevaluate(task_service_pb2.ReevaluateRequest(
                task_id=str(task_id),
                reevaluate_config=json.dumps(reevaluate_config)
            ))
            return resp.success, resp.message
        except Exception as e:
            return False, f"重新评估失败: {str(e)}"


class _DeviceDriverFactoryProxy:
    """device_driver_factory 代理：把方法调用转发到 gRPC DeviceService

    原 device_driver_factory 提供 get_driver / get_driver_name_by_keywords /
    get_registered_keywords / get_mock_mode 等方法。
    """

    def get_driver(self, system, keywords=None, **kwargs):
        # 原 get_driver 返回一个本地 driver 对象，gRPC 无法返回对象
        # 返回一个简单的字典描述，实际驱动逻辑需在 e2e_test_service 端执行
        # TODO: 复杂的 driver 对象交互需重新设计 proto
        return None

    def get_driver_name_by_keywords(self, system, keywords):
        from shared.proto import e2e_service_pb2
        try:
            stub = get_device_service_stub()
            resp = stub.CreateDriver(e2e_service_pb2.CreateDriverRequest(
                task_id='',
                device_config=json.dumps({
                    'action': 'get_driver_name_by_keywords',
                    'system': system,
                    'keywords': keywords,
                })
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
            resp = stub.CreateDriver(e2e_service_pb2.CreateDriverRequest(
                task_id='',
                device_config=json.dumps({'action': 'get_registered_keywords'})
            ))
            if resp.success and resp.data:
                return json.loads(resp.data)
            return []
        except Exception:
            return []

    def get_mock_mode(self):
        # TODO: gRPC DeviceService 暂无对应 RPC
        return False


# 模块级单例
device_driver_factory = _DeviceDriverFactoryProxy()


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
            # 原 play_audio 返回 future，gRPC 是同步的，返回一个已完成的哑 future
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


spl_service = _SplServiceProxy()


class _PlaybackOrchestratorProxy:
    """playback_orchestrator 代理：把方法调用转发到 gRPC PlaybackService"""

    def play_round(self, round_config=None, task_id=None, case_config=None,
                   test_case_id=None, round_number=None, **kwargs):
        from shared.proto import e2e_service_pb2
        try:
            stub = get_playback_service_stub()
            playback_config = {
                'action': 'play_round',
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
                'action': 'play_voiceprint',
                'voiceprint_config': voiceprint_config,
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
    """原 get_device_result_collector 返回单例，此处返回代理

    用于 api_gateway 端调用 convert_results 等
    """
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
