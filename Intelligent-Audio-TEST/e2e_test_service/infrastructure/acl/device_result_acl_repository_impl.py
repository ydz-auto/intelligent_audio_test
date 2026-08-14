# -*- coding: utf-8 -*-
"""DeviceResultService ACL 仓储 — gRPC 实现"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from e2e_test_service.domain.dto import CollectedResultDTO, ReextractResultDTO
from e2e_test_service.domain.repositories.device_result_acl_repository import (
    DeviceResultAclRepository,
)
from shared.utils.dto_utils import dict_to_dto, dict_list_to_dto, dto_to_dict

logger = logging.getLogger(__name__)

_KNOWN_COLLECTED = set(CollectedResultDTO.__dataclass_fields__.keys())
_KNOWN_REEXTRACT = set(ReextractResultDTO.__dataclass_fields__.keys())


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


class DeviceResultAclRepositoryImpl(DeviceResultAclRepository):
    """DeviceResultService ACL 仓储实现"""

    def collect_results(self, task_id: str, test_case_id: str,
                        device_info_list: List[Dict], extra_params: Dict,
                        **kwargs) -> List[CollectedResultDTO]:
        """采集设备原始结果"""
        from shared.clients.grpc_clients import get_device_result_service_stub
        from shared.proto import device_service_pb2 as device_pb
        try:
            stub = get_device_result_service_stub()
            serializable_device_list = [
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
            collect_config = {
                'mode': 'round' if kwargs.get('mode') == 'round' else 'raw',
                'task_id': task_id,
                'test_case_id': test_case_id,
                'device_info_list': serializable_device_list,
                'extra_params': extra_params,
                'kwargs': {k: v for k, v in kwargs.items() if k != 'mode'},
            }
            resp = stub.CollectResult(device_pb.CollectResultRequest(
                task_id=str(task_id),
                collect_config=json.dumps(collect_config, default=str),
            ))
            if not resp.success or not resp.data:
                return []
            result = json.loads(resp.data)
            return _to_collected_list(result)
        except Exception as e:
            logger.error("collect_results 失败: %s", e)
            return []

    def convert_results(self, tagged_results: List[Dict], algorithm_type: str) -> List[CollectedResultDTO]:
        """转换结果字段"""
        from shared.clients.grpc_clients import get_device_result_service_stub
        from shared.proto import device_service_pb2 as device_pb
        try:
            stub = get_device_result_service_stub()
            serializable_results = [dto_to_dict(r) for r in (tagged_results or [])]
            collect_config = {
                'mode': 'convert',
                'task_id': '',
                'tagged_results': serializable_results,
                'algorithm_type': algorithm_type,
            }
            resp = stub.CollectResult(device_pb.CollectResultRequest(
                task_id='',
                collect_config=json.dumps(collect_config, default=str),
            ))
            if not resp.success or not resp.data:
                return _to_collected_list(tagged_results)
            result = json.loads(resp.data)
            return _to_collected_list(result)
        except Exception as e:
            logger.error("convert_results 失败: %s", e)
            return _to_collected_list(tagged_results)

    def reextract_result(self, task_id: str, reextract_config: Dict) -> Optional[ReextractResultDTO]:
        """重新提取设备结果"""
        from shared.clients.grpc_clients import get_device_result_service_stub
        from shared.proto import device_service_pb2 as device_pb
        try:
            stub = get_device_result_service_stub()
            resp = stub.ReextractResult(device_pb.ReextractResultRequest(
                task_id=str(task_id),
                reextract_config=json.dumps(reextract_config, default=str),
            ))
            if not resp.success or not resp.data:
                return None
            data = json.loads(resp.data)
            dto = dict_to_dto(data, ReextractResultDTO)
            if dto and isinstance(data, dict):
                dto.result_data = {k: v for k, v in data.items() if k not in _KNOWN_REEXTRACT}
            return dto
        except Exception as e:
            logger.error("reextract_result 失败: %s", e)
            return None

    def build_case_result_log(self, algorithm_type: str, res: Dict, ref_fields=None, **kwargs) -> str:
        """构建用例结果日志"""
        from shared.clients.grpc_clients import get_device_result_service_stub
        from shared.proto import device_service_pb2 as device_pb
        try:
            stub = get_device_result_service_stub()
            collect_config = json.dumps({
                'action': 'build_case_result_log',
                'algorithm_type': algorithm_type,
                'res': res,
                'ref_fields': ref_fields,
                'kwargs': kwargs,
            }, default=str)
            resp = stub.CollectResult(device_pb.CollectResultRequest(
                task_id='', collect_config=collect_config,
            ))
            if not resp.success or not resp.data:
                return ''
            return resp.data
        except Exception as e:
            logger.error("build_case_result_log 失败: %s", e)
            return ''
