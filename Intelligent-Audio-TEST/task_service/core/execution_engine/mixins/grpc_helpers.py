# gRPC 调用封装：把对 e2e_test_service 的直接 import 调用替换为 gRPC stub 调用
# 注意：stub 获取函数采用方法内延迟 import，避免模块顶层 import 导致循环依赖。

import logging

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────
#  gRPC 调用封装：把对 e2e_test_service 的直接 import 调用替换为 gRPC stub 调用
# ──────────────────────────────────────────────────────────────────

def _stop_task_audio_via_grpc(task_id):
    """通过 gRPC AudioService 停止任务音频（原 audio_service.stop_task_audio）"""
    import json as _json
    from shared.proto import audio_service_pb2
    # 延迟 import 避免循环依赖
    from shared.clients.grpc_clients import get_audio_service_stub
    try:
        stub = get_audio_service_stub()
        stub.StopAudio(audio_service_pb2.StopAudioRequest(task_id=str(task_id)))
    except Exception:
        logger.debug("gRPC 停止任务音频失败 task_id=%s", task_id, exc_info=True)


def _cleanup_devices_via_grpc(task_id):
    """通过 gRPC DeviceService 清理任务设备（原 device_driver_factory.cleanup_devices）"""
    import json as _json
    from shared.proto import device_service_pb2
    # 延迟 import 避免 circular dependency
    from shared.clients.grpc_clients import get_device_service_stub
    try:
        stub = get_device_service_stub()
        stub.DestroyDriver(device_service_pb2.DestroyDriverRequest(
            task_id=str(task_id),
            driver_id='',
        ))
    except Exception:
        logger.debug("gRPC 清理任务设备失败 task_id=%s", task_id, exc_info=True)


def _unregister_task_events_via_grpc(task_id):
    """通过 gRPC DeviceService 注销任务事件（原 unregister_task_events）"""
    import json as _json
    from shared.proto import device_service_pb2
    # 延迟 import 避免 circular dependency
    from shared.clients.grpc_clients import get_device_service_stub
    try:
        stub = get_device_service_stub()
        stub.UnregisterTaskEvents(device_service_pb2.UnregisterTaskEventsRequest(
            task_id=str(task_id)
        ))
    except Exception:
        logger.debug("gRPC 注销任务事件失败 task_id=%s", task_id, exc_info=True)


def _get_task_events_via_grpc(task_id):
    """通过 gRPC DeviceService 获取任务事件（原 get_task_events）

    返回 None 表示未注册事件（用于 resume 时判断是否需要重新注册）
    """
    import json as _json
    from shared.proto import device_service_pb2
    # 延迟 import 避免 circular dependency
    from shared.clients.grpc_clients import get_device_service_stub
    try:
        stub = get_device_service_stub()
        resp = stub.GetTaskEvents(device_service_pb2.GetTaskEventsRequest(
            task_id=str(task_id), max_events=1
        ))
        if not resp.success or not resp.data:
            return None
        return _json.loads(resp.data)
    except Exception:
        return None


def _register_task_events_via_grpc(task_id, stop_event, pause_event):
    """通过 gRPC DeviceService 注册/同步任务事件

    e2e_test_service 端首次调用创建本地 Event，后续调用根据传入的
    stop_event_set/pause_event_set 同步其本地 Event 状态，实现跨进程事件通知。
    """
    import json as _json
    from shared.proto import device_service_pb2
    # 延迟 import 避免 circular dependency
    from shared.clients.grpc_clients import get_device_service_stub
    try:
        stub = get_device_service_stub()
        callback_config = {
            'stop_event_set': stop_event.is_set() if stop_event else False,
            'pause_event_set': pause_event.is_set() if pause_event else True,
        }
        stub.RegisterTaskEvents(device_service_pb2.RegisterTaskEventsRequest(
            task_id=str(task_id),
            callback_config=_json.dumps(callback_config)
        ))
    except Exception:
        logger.debug("gRPC 注册任务事件失败 task_id=%s", task_id, exc_info=True)


def _execute_e2e_case_via_grpc(task_id, tc_rel_id):
    """通过 gRPC 调用 e2e_test_service 的 ExecutionService.StartE2ETask

    原 `self.e2e_executor.execute_e2e_case(task_id, tc_rel_id)` 已替换为跨服务
    gRPC 调用，E2E 业务逻辑已下沉到 e2e_test_service 进程。
    """
    import json as _json
    from shared.proto import e2e_test_service_pb2
    # 延迟 import 避免 circular dependency
    from shared.clients.grpc_clients import get_e2e_execution_service_stub
    try:
        stub = get_e2e_execution_service_stub()
        resp = stub.StartE2ETask(e2e_test_service_pb2.StartE2ETaskRequest(
            task_id=str(task_id),
            tc_rel_id=str(tc_rel_id),
            e2e_config='',
        ))
        if not resp.success:
            return False
        return True
    except Exception as e:
        import logging as _logging
        _logging.getLogger('task_service').exception(
            f"[_execute_e2e_case_via_grpc] gRPC调用StartE2ETask异常: task_id={task_id}, tc_rel_id={tc_rel_id}, error={e}"
        )
        return False
