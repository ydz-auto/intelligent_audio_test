# -*- coding: utf-8 -*-
"""参数变更历史 / 回滚编排（api_gateway application）。

- 记录：设备 / API 参数与映射写成功后，采集该作用域覆盖行快照追加版本；
- 列表：按 (scope, scope_id, algorithm_type) 返回最近 N 个版本；
- 回滚：
  * API 作用域复用 ``SaveApiScopeOverrides``（整份同步：upsert + 提交集外软删）；
  * 设备作用域按自然键 diff 后逐行 create / update / delete（无整份同步接口）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from api_gateway.infrastructure.acl.config_acl_repository import (
    AlgorithmConfigAclRepositoryImpl,
)
from api_gateway.infrastructure.grpc_proxies.algorithm_proxies import (
    algorithm_query_service as _algo_proxy,
)
from api_gateway.infrastructure.repositories.param_history_repository import (
    ACTION_RESTORE,
    ACTION_SAVE,
    SCOPE_API,
    SCOPE_DEVICE,
    ParamHistoryRepository,
    param_history_repository,
)
from api_gateway.utils.response import error_response, success_response

_algorithm_acl = AlgorithmConfigAclRepositoryImpl()


def _ok(result: Optional[dict]) -> bool:
    return bool(result and result.get('success'))


def _error(result: Optional[dict], fallback: str) -> str:
    if result and result.get('message'):
        return str(result['message'])
    return fallback


def _strip_id(row: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in row.items() if key != 'id'}


def _param_key(row: Dict[str, Any]):
    return (row.get('param_code'), row.get('direction'))


def _mapping_key(row: Dict[str, Any]):
    return (row.get('source'), row.get('source_param'), row.get('dimension_id'))


class ParamHistoryService:
    """历史列表 + 版本回滚。"""

    @staticmethod
    def list_history(scope: str, scope_id: int, algorithm_type: str):
        if scope not in (SCOPE_API, SCOPE_DEVICE):
            return error_response(f'未知作用域: {scope}', 400)
        if not algorithm_type:
            return error_response('algorithm_type 必填', 400)
        repo: ParamHistoryRepository = param_history_repository
        versions = repo.list_versions(scope, scope_id, algorithm_type)
        return success_response({'items': versions, 'total': len(versions)})

    @staticmethod
    def record(
        scope: str, scope_id: int, algorithm_type: str,
        action: str = ACTION_SAVE,
    ) -> Optional[Dict[str, Any]]:
        """写操作成功后的记录入口；审计失败不阻断主流程。"""
        if not scope or scope_id is None or not algorithm_type:
            return None
        try:
            return param_history_repository.record_snapshot(
                scope, int(scope_id), algorithm_type, action)
        except Exception:  # 历史表缺失 / 并发冲突都不影响主流程
            return None

    @staticmethod
    def restore(history_id: int):
        history = param_history_repository.get(history_id)
        if history is None:
            return error_response('历史版本不存在', 404)

        scope = history['scope']
        scope_id = history['scopeId']
        algorithm_type = history['algorithmType']
        payload = history['payload'] or {}

        if scope == SCOPE_API:
            counts = _restore_api(scope_id, algorithm_type, payload)
        elif scope == SCOPE_DEVICE:
            counts = _restore_device(scope_id, algorithm_type, payload)
        else:
            return error_response(f'未知作用域: {scope}', 400)

        if counts.get('error'):
            return error_response(counts['error'], 400)

        # 回滚本身也记一个版本，便于再回退
        ParamHistoryService.record(
            scope, scope_id, algorithm_type, action=ACTION_RESTORE)
        return success_response(counts, '已回滚到所选版本')


def _restore_api(api_id: int, algorithm_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    params: List[Dict[str, Any]] = [
        _strip_id(row) for row in payload.get('params') or []
    ]
    mappings: List[Dict[str, Any]] = [
        _strip_id(row) for row in payload.get('mappings') or []
    ]
    result = _algo_proxy.save_api_scope_overrides(
        int(api_id), algorithm_type, params, mappings)
    if not _ok(result):
        return {'error': _error(result, '回滚 API 参数失败')}
    data = result.get('data') or {}
    return {
        'paramsRestored': len(params),
        'mappingsRestored': len(mappings),
        'detail': data,
    }


def _restore_device(
    device_id: int, algorithm_type: str, payload: Dict[str, Any]
) -> Dict[str, Any]:
    current = param_history_repository.snapshot(
        SCOPE_DEVICE, int(device_id), algorithm_type)
    target_params = {
        _param_key(row): row for row in payload.get('params') or []
    }
    current_params = {
        _param_key(row): row for row in current.get('params') or []
    }
    target_mappings = {
        _mapping_key(row): row for row in payload.get('mappings') or []
    }
    current_mappings = {
        _mapping_key(row): row for row in current.get('mappings') or []
    }

    counts = {'paramsCreated': 0, 'paramsUpdated': 0, 'paramsDeleted': 0,
              'mappingsCreated': 0, 'mappingsUpdated': 0, 'mappingsDeleted': 0}

    for key, row in target_params.items():
        body = _device_param_body(row, device_id, algorithm_type)
        existing = current_params.get(key)
        if existing is None:
            result = _algorithm_acl.create_param(body)
            if not _ok(result):
                return {'error': _error(result, '回滚设备参数失败')}
            counts['paramsCreated'] += 1
        else:
            result = _algorithm_acl.update_param(existing['id'], body)
            if not _ok(result):
                return {'error': _error(result, '回滚设备参数失败')}
            counts['paramsUpdated'] += 1
    for key, row in current_params.items():
        if key in target_params:
            continue
        result = _algorithm_acl.delete_param(row['id'])
        if not _ok(result):
            return {'error': _error(result, '回滚设备参数失败')}
        counts['paramsDeleted'] += 1

    for key, row in target_mappings.items():
        body = _device_mapping_body(row, device_id, algorithm_type)
        existing = current_mappings.get(key)
        if existing is None:
            result = _algorithm_acl.create_mapping(body)
            if not _ok(result):
                return {'error': _error(result, '回滚设备映射失败')}
            counts['mappingsCreated'] += 1
        else:
            result = _algorithm_acl.update_mapping(existing['id'], body)
            if not _ok(result):
                return {'error': _error(result, '回滚设备映射失败')}
            counts['mappingsUpdated'] += 1
    for key, row in current_mappings.items():
        if key in target_mappings:
            continue
        result = _algorithm_acl.delete_mapping(row['id'])
        if not _ok(result):
            return {'error': _error(result, '回滚设备映射失败')}
        counts['mappingsDeleted'] += 1

    return counts


def _device_param_body(
    row: Dict[str, Any], device_id: int, algorithm_type: str
) -> Dict[str, Any]:
    body = _strip_id(row)
    body.update({
        'algorithm_type': algorithm_type,
        'device_id': int(device_id),
        # 写侧按该键选表（缺省会落到 device 表，但显式声明避免歧义）
        'param_type_source': 'device',
    })
    return body


def _device_mapping_body(
    row: Dict[str, Any], device_id: int, algorithm_type: str
) -> Dict[str, Any]:
    body = _strip_id(row)
    body.update({
        'algorithm_type': algorithm_type,
        'device_id': int(device_id),
        # 写侧兼容 source_type / source 两种键
        'source_type': row.get('source'),
    })
    return body
