import json as _json


def _register_task_events_via_grpc(task_id, stop_event, pause_event):
    """通过 gRPC DeviceService 注册/同步任务事件

    e2e_test_service 端首次调用创建本地 Event，后续调用根据传入的
    stop_event_set/pause_event_set 同步其本地 Event 状态，实现跨进程事件通知。
    """
    from shared.clients.grpc_clients import get_device_service_stub
    from shared.proto import e2e_service_pb2
    try:
        stub = get_device_service_stub()
        callback_config = {
            'stop_event_set': stop_event.is_set() if stop_event else False,
            'pause_event_set': pause_event.is_set() if pause_event else True,
        }
        resp = stub.RegisterTaskEvents(e2e_service_pb2.RegisterTaskEventsRequest(
            task_id=str(task_id),
            callback_config=_json.dumps(callback_config)
        ))
        return resp.success
    except Exception:
        return False


def _register_task_devices_via_grpc(task_id, device_info_list):
    """通过 gRPC DeviceService 注册任务设备（原 device_driver_factory.register_task_devices）"""
    from shared.clients.grpc_clients import get_device_service_stub
    from shared.proto import e2e_service_pb2
    try:
        stub = get_device_service_stub()
        # device_info_list 内含 driver 对象，无法跨进程序列化
        # 只传递设备元数据
        serializable_info = [
            {
                'device_id': info.get('device_id'),
                'device_sn': info.get('device_sn'),
                'device_name': info.get('device_name'),
                'needs_prompt_audio': info.get('needs_prompt_audio'),
                'prompt_audio_path': info.get('prompt_audio_path'),
                'prompt_audio_name': info.get('prompt_audio_name'),
            }
            for info in device_info_list
        ]
        resp = stub.CreateDriver(e2e_service_pb2.CreateDriverRequest(
            task_id=str(task_id),
            device_config=_json.dumps(serializable_info)
        ))
        return resp.success
    except Exception:
        return False


def _play_voiceprint_via_grpc(voiceprint_config, task_id):
    """通过 gRPC PlaybackService 播放声纹（原 playback_orchestrator.play_voiceprint）"""
    from shared.clients.grpc_clients import get_playback_service_stub
    from shared.proto import e2e_service_pb2
    try:
        stub = get_playback_service_stub()
        playback_config = {
            'action': 'play_voiceprint',
            'voiceprint_config': voiceprint_config,
        }
        resp = stub.StartPlayback(e2e_service_pb2.StartPlaybackRequest(
            task_id=str(task_id),
            playback_config=_json.dumps(playback_config)
        ))
        return resp.success
    except Exception:
        return False


def _play_round_via_grpc(round_config, task_id, case_config, test_case_id, round_number,
                          audio_local_paths=None):
    """通过 gRPC PlaybackService 播放本轮音频（原 playback_orchestrator.play_round）

    Args:
        audio_local_paths: 准备阶段预下载的 audio_id→本地路径 映射，
            传给播放服务使其直接用本地文件，不再查 OSS。
    """
    from shared.clients.grpc_clients import get_playback_service_stub
    from shared.proto import e2e_service_pb2
    try:
        stub = get_playback_service_stub()
        playback_config = {
            'action': 'play_round',
            'round_config': round_config,
            'case_config': case_config,
            'test_case_id': test_case_id,
            'round_number': round_number,
            'audio_local_paths': audio_local_paths or {},
        }
        resp = stub.StartPlayback(e2e_service_pb2.StartPlaybackRequest(
            task_id=str(task_id),
            playback_config=_json.dumps(playback_config)
        ))
        if not resp.success or not resp.data:
            return None
        wrapper = _json.loads(resp.data)
        # gRPC 服务端把 result 包装在 {"result": ..., "mode": ...} 里，解包返回 result
        return wrapper.get('result') if isinstance(wrapper, dict) else wrapper
    except Exception:
        return None
