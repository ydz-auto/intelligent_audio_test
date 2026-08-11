# -*- coding: utf-8 -*-
"""DeviceService ACL 仓储 — gRPC 实现

封装 device_service gRPC 调用，实现 domain/repositories/DeviceAclRepository 接口。
替代原 core/e2e_executor/grpc_helpers.py 中的 DeviceService 相关函数 + DB 直连。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from e2e_test_service.domain.dto import (
    CollectedResultDTO,
    DeviceDTO,
    DriverScanDTO,
    RegisteredKeywordsDTO,
)
from e2e_test_service.domain.repositories.device_acl_repository import (
    DeviceAclRepository,
)
from shared.utils.dto_utils import dict_to_dto, dict_list_to_dto

logger = logging.getLogger(__name__)

_KNOWN_COLLECTED = set(CollectedResultDTO.__dataclass_fields__.keys())


def _to_collected_list(raw: Any) -> List[CollectedResultDTO]:
    """将 gRPC 返回的原始数据转换为 CollectedResultDTO 列表，动态字段存入 result_data。"""
    if isinstance(raw, dict) and 'results' in raw:
        items = raw['results']
    elif isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        items = [raw]
    else:
        return []
    dtos: List[CollectedResultDTO] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        dto = dict_to_dto(item, CollectedResultDTO)
        if dto:
            dto.result_data = {k: v for k, v in item.items() if k not in _KNOWN_COLLECTED}
            dtos.append(dto)
    return dtos


class DeviceAclRepositoryImpl(DeviceAclRepository):
    """DeviceService ACL 仓储实现"""

    def get_devices_by_ids(self, device_ids: List[int]) -> List[DeviceDTO]:
        """按 ID 列表获取设备信息（通过 DeviceConfigService.GetDevice 逐个查询）

        device_service 没有 batch get，用 GetDeviceStatuses 获取状态，
        再逐个 GetDevice 获取详情。为简化，这里逐个调用 GetDevice。
        """
        from shared.clients.grpc_clients import get_device_config_service_stub
        from shared.proto import device_service_pb2 as device_pb
        try:
            stub = get_device_config_service_stub()
            devices = []
            for did in device_ids:
                resp = stub.GetDevice(device_pb.GetDeviceRequest(device_id=int(did)))
                if resp.success and resp.data:
                    data = json.loads(resp.data)
                    if isinstance(data, dict):
                        devices.append(data)
            return dict_list_to_dto(devices, DeviceDTO)
        except Exception as e:
            logger.error("get_devices_by_ids 失败: %s", e)
            return []

    def register_task_events(self, task_id: str, stop_event_set: bool,
                             pause_event_set: bool) -> bool:
        """注册/同步任务事件"""
        from shared.clients.grpc_clients import get_device_service_stub
        from shared.proto import device_service_pb2 as device_pb
        try:
            stub = get_device_service_stub()
            callback_config = {
                'stop_event_set': stop_event_set,
                'pause_event_set': pause_event_set,
            }
            resp = stub.RegisterTaskEvents(device_pb.RegisterTaskEventsRequest(
                task_id=str(task_id),
                callback_config=json.dumps(callback_config),
            ))
            return resp.success
        except Exception as e:
            logger.error("register_task_events 失败: %s", e)
            return False

    def register_task_devices(self, task_id: str, device_info_list: List[Dict]) -> bool:
        """注册任务设备（通过 CreateDriver 传递设备元数据）"""
        from shared.clients.grpc_clients import get_device_service_stub
        from shared.proto import device_service_pb2 as device_pb
        try:
            stub = get_device_service_stub()
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
            resp = stub.CreateDriver(device_pb.CreateDriverRequest(
                task_id=str(task_id),
                device_config=json.dumps(serializable_info),
            ))
            return resp.success
        except Exception as e:
            logger.error("register_task_devices 失败: %s", e)
            return False

    def create_driver(self, task_id: str, device_config: List[Dict]) -> bool:
        """创建设备驱动"""
        from shared.clients.grpc_clients import get_device_service_stub
        from shared.proto import device_service_pb2 as device_pb
        try:
            stub = get_device_service_stub()
            resp = stub.CreateDriver(device_pb.CreateDriverRequest(
                task_id=str(task_id),
                device_config=json.dumps(device_config),
            ))
            return resp.success
        except Exception as e:
            logger.error("create_driver 失败: %s", e)
            return False

    def extract_archive_results(self, task_id: str, device_config: Dict) -> List[CollectedResultDTO]:
        """提取存档结果

        通过 CreateDriver RPC 的 action 分发机制调用 driver.extract_results_from_archive。
        """
        from shared.clients.grpc_clients import get_device_service_stub
        from shared.proto import device_service_pb2 as device_pb
        try:
            stub = get_device_service_stub()
            config = dict(device_config) if isinstance(device_config, dict) else {}
            config.setdefault('action', 'extract_results_from_archive')
            resp = stub.CreateDriver(device_pb.CreateDriverRequest(
                task_id=str(task_id),
                device_config=json.dumps(config),
            ))
            if not resp.success or not resp.data:
                return []
            result = json.loads(resp.data)
            return _to_collected_list(result)
        except Exception as e:
            logger.error("extract_archive_results 失败: %s", e)
            return []

    def get_final_results(self, task_id: str, device_config: Dict) -> List[CollectedResultDTO]:
        """所有轮次完成后获取最终聚合结果

        通过 CreateDriver RPC 的 action 分发机制调用 driver.get_final_results。
        """
        from shared.clients.grpc_clients import get_device_service_stub
        from shared.proto import device_service_pb2 as device_pb
        try:
            stub = get_device_service_stub()
            config = dict(device_config) if isinstance(device_config, dict) else {}
            config.setdefault('action', 'get_final_results')
            resp = stub.CreateDriver(device_pb.CreateDriverRequest(
                task_id=str(task_id),
                device_config=json.dumps(config),
            ))
            if not resp.success or not resp.data:
                return []
            result = json.loads(resp.data)
            return _to_collected_list(result)
        except Exception as e:
            logger.error("get_final_results 失败: %s", e)
            return []

    def destroy_driver(self, task_id: str) -> bool:
        """销毁设备驱动"""
        from shared.clients.grpc_clients import get_device_service_stub
        from shared.proto import device_service_pb2 as device_pb
        try:
            stub = get_device_service_stub()
            resp = stub.DestroyDriver(device_pb.DestroyDriverRequest(task_id=str(task_id)))
            return resp.success
        except Exception as e:
            logger.error("destroy_driver 失败: %s", e)
            return False

    def driver_scan(self, system: str, keywords: str = '') -> List[DriverScanDTO]:
        """扫描设备"""
        from shared.clients.grpc_clients import get_device_service_stub
        from shared.proto import device_service_pb2 as device_pb
        try:
            stub = get_device_service_stub()
            resp = stub.DriverScan(device_pb.DriverScanRequest(
                system=system, keywords=keywords or '',
            ))
            if resp.success and resp.data:
                data = json.loads(resp.data)
                return dict_list_to_dto(data, DriverScanDTO) if isinstance(data, list) else []
            return []
        except Exception as e:
            logger.error("driver_scan 失败: %s", e)
            return []

    def driver_unlock(self, system: str, keywords: str, serial_or_ip: str) -> bool:
        """解锁设备"""
        from shared.clients.grpc_clients import get_device_service_stub
        from shared.proto import device_service_pb2 as device_pb
        try:
            stub = get_device_service_stub()
            resp = stub.DriverUnlock(device_pb.DriverUnlockRequest(
                system=system, keywords=keywords or '',
                serial_or_ip=serial_or_ip or '',
            ))
            return resp.success
        except Exception as e:
            logger.error("driver_unlock 失败: %s", e)
            return False

    def get_driver_name_by_keywords(self, system: str, keywords: str) -> str:
        """获取驱动名称"""
        from shared.clients.grpc_clients import get_device_service_stub
        from shared.proto import device_service_pb2 as device_pb
        try:
            stub = get_device_service_stub()
            resp = stub.GetDriverNameByKeywords(device_pb.GetDriverNameByKeywordsRequest(
                system=system, keywords=keywords or '',
            ))
            if resp.success and resp.data:
                data = json.loads(resp.data)
                return data.get('driver_name', '') if isinstance(data, dict) else ''
            return ''
        except Exception as e:
            logger.error("get_driver_name_by_keywords 失败: %s", e)
            return ''

    def get_registered_keywords(self) -> Optional[RegisteredKeywordsDTO]:
        """获取所有已注册驱动关键字"""
        from shared.clients.grpc_clients import get_device_service_stub
        from shared.proto import device_service_pb2 as device_pb
        try:
            stub = get_device_service_stub()
            resp = stub.GetRegisteredKeywords(device_pb.GetRegisteredKeywordsRequest())
            if resp.success and resp.data:
                data = json.loads(resp.data)
                dto = dict_to_dto(data, RegisteredKeywordsDTO) if isinstance(data, dict) else None
                if dto:
                    dto.keywords = data
                return dto
            return None
        except Exception as e:
            logger.error("get_registered_keywords 失败: %s", e)
            return None

    def get_mock_mode(self, system: str = '') -> bool:
        """获取 mock 模式"""
        from shared.clients.grpc_clients import get_device_service_stub
        from shared.proto import device_service_pb2 as device_pb
        try:
            stub = get_device_service_stub()
            resp = stub.GetMockMode(device_pb.GetMockModeRequest(system=system or ''))
            if resp.success and resp.data:
                data = json.loads(resp.data)
                return data.get('mock_mode', False) if isinstance(data, dict) else False
            return False
        except Exception as e:
            logger.error("get_mock_mode 失败: %s", e)
            return False

    def set_mock_mode(self, system: str, mock_mode: bool) -> bool:
        """设置 mock 模式"""
        from shared.clients.grpc_clients import get_device_service_stub
        from shared.proto import device_service_pb2 as device_pb
        try:
            stub = get_device_service_stub()
            resp = stub.SetMockMode(device_pb.SetMockModeRequest(
                system=system or '', mock_mode=mock_mode,
            ))
            return resp.success
        except Exception as e:
            logger.error("set_mock_mode 失败: %s", e)
            return False
