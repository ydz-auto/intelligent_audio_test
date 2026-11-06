# -*- coding: utf-8 -*-
"""audio_service 防腐层仓储（ACL Repository）

封装对 audio_service.AudioService / AudioConfigService 的 gRPC 调用，
替代 device_service application 层中对 shared.clients.grpc_clients 的直接 import。

- 读/写操作均通过 gRPC 完成，返回 dict / list / bool / int，不返回 ORM 对象。
- 与 device_service/infrastructure/acl/task_acl_repository.py 风格一致，
  采用具体类 + 模块级单例（device_service ACL 层无统一 ABC）。
"""
import json
import logging

logger = logging.getLogger(__name__)


def _parse_physical_devices_payload(raw):
    """解析 audio_service.GetPhysicalDevices 的 data 载荷（INT-1974）

    现行契约是**裸数组**（audio_service servicer 直接 `_dumps(devices)`，
    api_gateway 代理也按裸数组 `json.loads` 使用），此处一并兼容早期
    `{"devices": [...]}` 形状，避免任一形态变化把整域设备判成离线。

    Args:
        raw: gRPC 响应的 data（JSON 文本，通常为 str）

    Returns:
        list | None: 设备列表（可能为空）；JSON 解码失败返回 None，
        由调用方据此判定「枚举不可用」，不要与「没有设备」混同。
    """
    if not raw:
        return []
    if isinstance(raw, bytes):
        raw = raw.decode('utf-8', errors='replace')
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        logger.warning(
            "GetPhysicalDevices 载荷非 JSON，按枚举解析失败处理: %.200s", raw)
        return None
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        devices = data.get('devices')
        if isinstance(devices, list):
            return devices
        logger.warning(
            "GetPhysicalDevices 载荷 dict 无 devices 列表，按空列表处理: %.200s", raw)
        return []
    logger.warning(
        "GetPhysicalDevices 载荷形状不可识别(%s)，按空列表处理: %.200s",
        type(data).__name__, raw)
    return []


class AudioServiceACLRepository:
    """audio_service 防腐层仓储

    封装 gRPC 调用，提供 application 层可用的返回值。
    所有方法返回纯 dict / list / bool，不返回 ORM 对象。
    """

    def enumerate_physical_devices(self) -> tuple:
        """枚举物理设备并区分「枚举不可用」与「没有设备」

        契约 §2.5 要求：诊断在枚举不可用时返回 unsupported 而不是 error，
        因此调用方必须能分辨 gRPC 失败（available=False）与空列表。

        载荷解析兼容裸数组与 `{"devices": [...]}` 两种形状（见
        `_parse_physical_devices_payload`）。`available` 语义：`resp.success`
        为真且载荷可解析即 True —— 空列表表示「没有设备」，不等于枚举不可用。

        Returns:
            (devices: list, available: bool)
        """
        from shared.clients.grpc_clients import get_audio_service_stub
        from shared.proto import audio_service_pb2 as _audio_pb
        try:
            stub = get_audio_service_stub()
            resp = stub.GetPhysicalDevices(_audio_pb.GetPhysicalDevicesRequest())
            if not resp.success:
                logger.warning(
                    "gRPC GetPhysicalDevices 返回失败 message=%s", resp.message)
                return [], False
            raw_data = resp.data
        except Exception:
            logger.warning("gRPC 获取物理设备列表失败", exc_info=True)
            return [], False
        # 解析放在 try 之外：载荷形状异常不再被 except Exception 静默吞掉（INT-1974）
        devices = _parse_physical_devices_payload(raw_data)
        if devices is None:
            return [], False
        return devices, True

    def get_physical_devices(self) -> list:
        """获取物理设备列表

        通过 gRPC 调用 audio_service.AudioService.GetPhysicalDevices，
        返回设备列表；gRPC 不可用时返回空列表。
        """
        return self.enumerate_physical_devices()[0]

    def get_device_index(self, unique_id: str):
        """获取设备索引

        通过 gRPC 调用 audio_service.AudioService.GetDeviceIndex，
        返回 device_index；gRPC 不可用时返回 None。
        """
        from shared.clients.grpc_clients import get_audio_service_stub
        from shared.proto import audio_service_pb2 as _audio_pb
        from shared.utils.grpc_json import loads as _grpc_loads
        try:
            stub = get_audio_service_stub()
            resp = stub.GetDeviceIndex(_audio_pb.GetDeviceIndexRequest(unique_id=unique_id))
            if resp.success:
                data = _grpc_loads(resp.data, {}) or {}
                return data.get('device_index')
        except Exception:
            logger.debug("gRPC 获取设备索引失败 unique_id=%s", unique_id, exc_info=True)
        return None

    def play_audio(self, task_id, file_path, device_index, channel_index, gain,
                   loop=False, player_type='', offset=0) -> bool:
        """播放音频

        通过 gRPC 调用 audio_service.AudioService.PlayAudio，
        返回是否成功；gRPC 异常时返回 False。
        """
        from shared.clients.grpc_clients import get_audio_service_stub
        from shared.proto import audio_service_pb2 as _audio_pb
        try:
            stub = get_audio_service_stub()
            play_config = json.dumps({
                'device_index': device_index,
                'channel_index': channel_index,
                'gain': gain,
                'loop': loop,
                'player_type': player_type,
                'offset': offset,
            })
            resp = stub.PlayAudio(_audio_pb.PlayAudioRequest(
                task_id=task_id,
                audio_file_paths=json.dumps([file_path]),
                play_config=play_config,
            ))
            return resp.success
        except Exception:
            return False

    def stop_audio(self, task_id) -> bool:
        """停止音频

        通过 gRPC 调用 audio_service.AudioService.StopAudio，
        返回是否成功；gRPC 异常时返回 False。
        """
        from shared.clients.grpc_clients import get_audio_service_stub
        from shared.proto import audio_service_pb2 as _audio_pb
        try:
            stub = get_audio_service_stub()
            stub.StopAudio(_audio_pb.StopAudioRequest(task_id=task_id))
            return True
        except Exception:
            return False

    def stop_audio_by_pattern(self, task_id_pattern: str, player_type_pattern: str) -> int:
        """按模式停止音频

        通过 gRPC 调用 audio_service.AudioService.StopAudioByPattern，
        返回已停止的任务数；gRPC 不可用时返回 0。
        """
        from shared.clients.grpc_clients import get_audio_service_stub
        from shared.proto import e2e_service_pb2 as _e2e_pb
        from shared.utils.grpc_json import loads as _grpc_loads
        try:
            stub = get_audio_service_stub()
            resp = stub.StopAudioByPattern(_e2e_pb.StopAudioByPatternRequest(
                task_id_pattern=task_id_pattern,
                player_type_pattern=player_type_pattern,
            ))
            if resp.success:
                data = _grpc_loads(resp.data, {}) or {}
                return data.get('stopped_count', 0)
        except Exception:
            logger.debug("gRPC 按模式停止音频失败 task_id_pattern=%s player_type_pattern=%s", task_id_pattern, player_type_pattern, exc_info=True)
        return 0

    def get_audio(self, audio_id):
        """获取音频元数据

        通过 gRPC 调用 audio_service.AudioConfigService.GetAudio，
        返回音频 dict；gRPC 不可用时返回 None。
        """
        from shared.clients.grpc_clients import get_audio_config_service_stub
        from shared.proto import audio_service_pb2 as _audio_pb
        from shared.utils.grpc_json import loads as _loads
        try:
            stub = get_audio_config_service_stub()
            resp = stub.GetAudio(_audio_pb.GetAudioRequest(audio_id=audio_id))
            if resp.success and resp.data:
                return _loads(resp.data, {}) or {}
        except Exception:
            logger.debug("gRPC 获取音频元数据失败 audio_id=%s", audio_id, exc_info=True)
        return None


# 模块级单例
audio_service_acl_repository = AudioServiceACLRepository()
