# -*- coding: utf-8 -*-
"""algorithm_service ACL gateway

封装所有跨服务 gRPC 调用和 storage 访问。
domain 层通过此模块间接访问基础设施，不直接 import shared.clients/grpc_clients 或 storage。

调用方：domain/services/algorithm/ 下的模块通过延迟 import 调用本模块函数。
"""
import json
from typing import Any, Dict, List, Optional

from algorithm_service.domain.dto import ReferenceParamDTO, AudioDTO
from shared.utils.dto_utils import dict_to_dto, dict_list_to_dto
from shared.utils.log_handler import log_not_emit


# ==================== Storage 访问 ====================

def storage_save_bytes(data: bytes, bucket: str, key: str, content_type: str = 'application/octet-stream') -> str:
    """保存字节数据到存储，返回 path"""
    from shared.infrastructure.storage import storage
    return storage.save_bytes(data, bucket, key, content_type=content_type)


def storage_load_bytes(path: str) -> bytes:
    """从存储加载字节数据"""
    from shared.infrastructure.storage import storage
    return storage.load_bytes(path)


def storage_exists(path: str) -> bool:
    """检查存储对象是否存在"""
    from shared.infrastructure.storage import storage
    return storage.exists(path)


# ==================== algorithm_service 自身 gRPC ====================

def list_reference_params(algorithm_type: str) -> List[ReferenceParamDTO]:
    """通过 gRPC 获取参考参数列表（algorithm_service.ListReferenceParams）"""
    try:
        from shared.clients.grpc_clients import get_algorithm_definition_service_stub
        from shared.proto import algorithm_service_pb2 as _algo_pb
        from shared.utils.grpc_json import loads as _loads
        stub = get_algorithm_definition_service_stub()
        req = _algo_pb.ListReferenceParamsRequest(algorithm_type=algorithm_type or '')
        resp = stub.ListReferenceParams(req)
        if resp.success:
            params = (_loads(resp.data, {}) or {}).get('parameters', []) or []
            return dict_list_to_dto(params, ReferenceParamDTO)
    except Exception as e:
        log_not_emit('ERROR', 'algorithm_acl_gateway',
                     f'list_reference_params failed: {e}', category='algorithm')
    return []


# ==================== audio_service gRPC ====================

def get_audios_by_ids(audio_ids: List[int]) -> Dict[int, AudioDTO]:
    """通过 gRPC 批量获取音频数据（audio_service.GetAudiosByIds）

    Returns:
        {audio_id: AudioDTO, ...} 或空 dict
    """
    if not audio_ids:
        return {}
    try:
        from shared.clients.grpc_clients import get_audio_config_service_stub
        from shared.proto import audio_service_pb2 as e2e_pb
        from shared.utils.grpc_json import loads as _loads
        stub = get_audio_config_service_stub()
        req = e2e_pb.GetAudiosByIdsRequest(audio_ids=','.join(str(aid) for aid in audio_ids))
        resp = stub.GetAudiosByIds(req)
        if not resp.success:
            return {}
        data = _loads(resp.data, {})
        audio_map = {}
        for item in data.get('items', []):
            aid = item.get('id')
            audio_map[aid] = dict_to_dto(item, AudioDTO)
        return audio_map
    except Exception as e:
        log_not_emit('ERROR', 'algorithm_acl_gateway',
                     f'get_audios_by_ids failed: {e}', category='algorithm')
        return {}


def get_audio_by_id(audio_id: int) -> Optional[AudioDTO]:
    """通过 gRPC 获取单个音频（audio_service.GetAudio）"""
    if not audio_id:
        return None
    try:
        from shared.clients.grpc_clients import get_audio_config_service_stub
        from shared.proto import audio_service_pb2 as e2e_pb
        from shared.utils.grpc_json import loads as _loads
        stub = get_audio_config_service_stub()
        resp = stub.GetAudio(e2e_pb.GetAudioRequest(audio_id=int(audio_id)))
        if not resp.success:
            return None
        return dict_to_dto(_loads(resp.data, {}), AudioDTO)
    except Exception as e:
        log_not_emit('ERROR', 'algorithm_acl_gateway',
                     f'get_audio_by_id failed: {e}', category='algorithm')
        return None


# ==================== task_service gRPC（algorithm config） ====================

def call_algo_config_rpc(method_name: str, **kwargs) -> Any:
    """通用调用 task_service.AlgorithmConfigService RPC

    Args:
        method_name: RPC 方法名（如 'ListAlgorithms'）
        **kwargs: 请求字段

    Returns:
        解析后的 data 字段（dict 或 list），失败返回 None
    """
    try:
        from shared.clients.grpc_clients import get_algorithm_config_service_stub
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads
        stub = get_algorithm_config_service_stub()
        req_cls = getattr(task_pb, f'{method_name}Request')
        req = req_cls(**kwargs)
        resp = getattr(stub, method_name)(req)
        if not resp.success:
            log_not_emit('WARNING', 'algorithm_acl_gateway',
                         f'gRPC {method_name} failed: {resp.message}', category='algorithm')
            return None
        return _loads(resp.data, {})
    except Exception as e:
        log_not_emit('ERROR', 'algorithm_acl_gateway',
                     f'gRPC {method_name} exception: {e}', category='algorithm')
        return None
