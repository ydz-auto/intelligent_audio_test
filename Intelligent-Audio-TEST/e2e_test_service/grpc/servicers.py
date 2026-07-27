# -*- coding: utf-8 -*-
"""
e2e_test_service gRPC servicer 实现。

将 gRPC RPC 方法委托给已有业务类：
- AudioServiceServicer        -> audio_service
- DeviceServiceServicer       -> device_driver_factory
- PlaybackServiceServicer     -> playback_orchestrator
- DeviceResultServiceServicer -> device_result_collector
- EnvDeviceServiceServicer    -> EnvDeviceFactory

约定：
- 复杂参数通过 JSON string 传递，方法内 json.loads 解析
- 返回结果通过 JSON string 封装到 data 字段
- 所有方法用 try/except 包裹，异常返回 success=False
"""

import json
import threading

from shared.proto import e2e_service_pb2 as e2e_pb
from shared.proto import e2e_service_pb2_grpc as e2e_grpc


def _loads(s, default):
    """安全 JSON 解析，空字符串返回默认值"""
    if not s:
        return default
    if isinstance(s, bytes):
        s = s.decode('utf-8')
    return json.loads(s)


def _dumps(obj):
    """JSON 序列化，None/不可序列化对象返回空字符串"""
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        return ""


# ==================== AudioServiceServicer ====================

class AudioServiceServicer(e2e_grpc.AudioServiceServicer):
    """音频服务 gRPC servicer，委托给 audio_service"""

    def __init__(self):
        self._audio_service = None

    @property
    def audio_service(self):
        if self._audio_service is None:
            from e2e_test_service.audio.audio_engine import audio_service
            self._audio_service = audio_service
        return self._audio_service

    def PlayAudio(self, request, context=None):
        """播放音频"""
        try:
            play_config = _loads(request.play_config, {})
            file_path = request.audio_file_paths
            task_id = request.task_id or play_config.get('task_id', '0')
            device_index = play_config.get('device_index')
            channel_index = play_config.get('channel_index', 0)
            gain = play_config.get('gain', 1.0)
            loop = play_config.get('loop', False)
            player_type = play_config.get('player_type', 'dry')
            offset = play_config.get('offset', 0)

            self.audio_service.play_audio(
                task_id=task_id,
                file_path=file_path,
                device_index=device_index,
                channel_index=channel_index,
                gain=gain,
                loop=loop,
                player_type=player_type,
                offset=offset,
            )
            return e2e_pb.PlayAudioResponse(
                success=True,
                message="ok",
                data=_dumps({"task_id": str(task_id), "file": file_path}),
            )
        except Exception as e:
            return e2e_pb.PlayAudioResponse(success=False, message=str(e), data="")

    def StopAudio(self, request, context=None):
        """停止播放"""
        try:
            task_id = request.task_id
            self.audio_service.stop_task_audio(task_id)
            return e2e_pb.StopAudioResponse(success=True, message="ok", data=_dumps({"task_id": str(task_id)}))
        except Exception as e:
            return e2e_pb.StopAudioResponse(success=False, message=str(e), data="")

    def GetPlayStatus(self, request, context=None):
        """获取播放状态"""
        try:
            task_id = request.task_id
            active_players = getattr(self.audio_service, 'active_players', {})
            players_info = {}
            task_key = task_id
            if task_key not in active_players and task_id is not None:
                task_key = str(task_id)
            if task_key not in active_players and isinstance(task_id, str) and task_id.isdigit():
                int_key = int(task_id)
                if int_key in active_players:
                    task_key = int_key
            task_players = active_players.get(task_key, {})
            for p_type, info in task_players.items():
                players_info[p_type] = {
                    "running": not info.get("future").done() if info.get("future") else False,
                }
            return e2e_pb.GetPlayStatusResponse(
                success=True, message="ok", data=_dumps({"task_id": str(task_id), "players": players_info})
            )
        except Exception as e:
            return e2e_pb.GetPlayStatusResponse(success=False, message=str(e), data="")

    def GetAudioInfo(self, request, context=None):
        """获取音频文件信息"""
        try:
            file_path = request.audio_file_path
            from e2e_test_service.audio.audio_timeline import get_audio_duration
            duration = get_audio_duration(file_path)
            import os
            file_size = os.path.getsize(file_path) if file_path and os.path.exists(file_path) else 0
            return e2e_pb.AudioInfoResponse(
                success=True, message="ok",
                data=_dumps({"file_path": file_path, "duration": duration, "file_size": file_size}),
            )
        except Exception as e:
            return e2e_pb.AudioInfoResponse(success=False, message=str(e), data="")

    def MeasureSPL(self, request, context=None):
        """声压级测量"""
        try:
            measure_config = _loads(request.measure_config, {})
            # SPL 测量需要硬件支持，当前返回占位结果
            # 实际测量由 spl_service / spl_mapping 完成
            from e2e_test_service.audio.spl_service import spl_service
            mapping_id = measure_config.get('mapping_id')
            target_spl = measure_config.get('target_spl', 70.0)
            gain = 1.0
            if mapping_id is not None:
                gain = spl_service.spl_to_gain(mapping_id, target_spl)
            return e2e_pb.SPLResponse(
                success=True, message="ok",
                data=_dumps({"mapping_id": mapping_id, "target_spl": target_spl, "gain": gain}),
            )
        except Exception as e:
            return e2e_pb.SPLResponse(success=False, message=str(e), data="")

    def StartSPL(self, request, context=None):
        """开始 SPL 测量"""
        try:
            spl_config = _loads(request.spl_config, {})
            # SPL 测量后台任务，当前实现为占位
            # 实际后台 SPL 测量需要硬件配合
            return e2e_pb.StartSPLResponse(
                success=True, message="ok",
                data=_dumps({"task_id": request.task_id, "config": spl_config, "started": True}),
            )
        except Exception as e:
            return e2e_pb.StartSPLResponse(success=False, message=str(e), data="")

    def StopSPL(self, request, context=None):
        """停止 SPL 测量"""
        try:
            # 停止后台 SPL 测量任务
            return e2e_pb.StopSPLResponse(
                success=True, message="ok",
                data=_dumps({"task_id": request.task_id, "stopped": True}),
            )
        except Exception as e:
            return e2e_pb.StopSPLResponse(success=False, message=str(e), data="")


# ==================== DeviceServiceServicer ====================

class DeviceServiceServicer(e2e_grpc.DeviceServiceServicer):
    """设备驱动服务 gRPC servicer，委托给 device_driver_factory"""

    def __init__(self):
        self._factory = None

    @property
    def factory(self):
        if self._factory is None:
            from e2e_test_service.drivers import device_driver_factory
            self._factory = device_driver_factory
        return self._factory

    def CreateDriver(self, request, context=None):
        """创建设备驱动（连接设备）"""
        try:
            device_config = _loads(request.device_config, {})
            system = device_config.get('system')
            keywords = device_config.get('keywords')
            device_sn = device_config.get('device_sn')
            device_info_list = device_config.get('device_info_list', [])
            task_id = request.task_id

            # 注册任务设备
            if device_info_list:
                self.factory.register_task_devices(task_id, device_info_list)

            driver = self.factory.get_driver(system, keywords=keywords, device_sn=device_sn)
            driver_info = {
                "system": system,
                "keywords": keywords,
                "device_sn": device_sn,
                "driver_found": driver is not None,
                "driver_name": driver.__class__.__name__ if driver else None,
            }
            return e2e_pb.CreateDriverResponse(success=True, message="ok", data=_dumps(driver_info))
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
            from e2e_test_service.drivers import register_task_events
            callback_config = _loads(request.callback_config, {})
            task_id = request.task_id
            stop_event = threading.Event()
            pause_event = threading.Event()
            pause_event.set()
            register_task_events(task_id, stop_event, pause_event)
            return e2e_pb.RegisterTaskEventsResponse(
                success=True, message="ok",
                data=_dumps({"task_id": str(task_id), "registered": True}),
            )
        except Exception as e:
            return e2e_pb.RegisterTaskEventsResponse(success=False, message=str(e), data="")

    def UnregisterTaskEvents(self, request, context=None):
        """注销任务事件回调"""
        try:
            from e2e_test_service.drivers import unregister_task_events
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
            from e2e_test_service.drivers import get_task_events
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


# ==================== PlaybackServiceServicer ====================

class PlaybackServiceServicer(e2e_grpc.PlaybackServiceServicer):
    """播放编排服务 gRPC servicer，委托给 playback_orchestrator"""

    def __init__(self):
        self._orchestrator = None

    @property
    def orchestrator(self):
        if self._orchestrator is None:
            from e2e_test_service.audio.playback_orchestrator import playback_orchestrator
            self._orchestrator = playback_orchestrator
        return self._orchestrator

    def StartPlayback(self, request, context=None):
        """开始播放编排"""
        try:
            playback_config = _loads(request.playback_config, {})
            task_id = request.task_id
            mode = playback_config.get('mode', 'round')

            if mode == 'preview':
                audio_configs = playback_config.get('audio_configs', [])
                case_config = playback_config.get('case_config', {})
                offset = playback_config.get('offset', 0)
                overlap_rate = playback_config.get('overlap_rate', 0)
                overlap_time = playback_config.get('overlap_time', 0)
                result = self.orchestrator.preview(
                    audio_configs, case_config, task_id,
                    offset=offset, overlap_rate=overlap_rate, overlap_time=overlap_time,
                )
            elif mode == 'voiceprint':
                vp_config = playback_config.get('vp_config', {})
                result = self.orchestrator.play_voiceprint(vp_config, task_id)
            else:
                round_config = playback_config.get('round_config', {})
                case_config = playback_config.get('case_config')
                test_case_id = playback_config.get('test_case_id')
                round_number = playback_config.get('round_number')
                result = self.orchestrator.play_round(
                    round_config, task_id,
                    case_config=case_config,
                    test_case_id=test_case_id,
                    round_number=round_number,
                )
            return e2e_pb.StartPlaybackResponse(
                success=True, message="ok",
                data=_dumps({"result": result, "mode": mode}),
            )
        except Exception as e:
            return e2e_pb.StartPlaybackResponse(success=False, message=str(e), data="")

    def StopPlayback(self, request, context=None):
        """停止播放编排"""
        try:
            from e2e_test_service.audio.audio_engine import audio_service
            task_id = request.task_id
            audio_service.stop_task_audio(task_id)
            return e2e_pb.StopPlaybackResponse(
                success=True, message="ok", data=_dumps({"task_id": str(task_id), "stopped": True})
            )
        except Exception as e:
            return e2e_pb.StopPlaybackResponse(success=False, message=str(e), data="")


# ==================== DeviceResultServiceServicer ====================

class DeviceResultServiceServicer(e2e_grpc.DeviceResultServiceServicer):
    """设备结果采集服务 gRPC servicer，委托给 device_result_collector"""

    def __init__(self):
        self._collector = None

    @property
    def collector(self):
        if self._collector is None:
            from e2e_test_service.device.device_result_collector import get_device_result_collector
            self._collector = get_device_result_collector()
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

            if mode == 'round':
                round_idx = collect_config.get('round_idx', 0)
                round_config = collect_config.get('round_config', {})
                round_start_time = collect_config.get('round_start_time')
                result = self.collector.collect_round_results(
                    task_id, test_case_id, device_info_list,
                    round_idx, round_config, round_start_time,
                )
            else:
                result = self.collector.collect_raw_results(
                    task_id, test_case_id, device_info_list, extra_params,
                )
            return e2e_pb.CollectResultResponse(
                success=True, message="ok", data=_dumps({"results": result, "count": len(result) if result else 0})
            )
        except Exception as e:
            return e2e_pb.CollectResultResponse(success=False, message=str(e), data="")

    def ReextractResult(self, request, context=None):
        """重新提取设备结果"""
        try:
            from e2e_test_service.device.device_result_reextractor import get_device_result_reextractor
            reextract_config = _loads(request.reextract_config, {})
            task_id = request.task_id
            execution_status = reextract_config.get('execution_status', 'completed')
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
            from e2e_test_service.env_device import EnvDeviceFactory
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

            # 批量创建并控制设备
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
