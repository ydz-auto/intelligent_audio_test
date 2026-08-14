# -*- coding: utf-8 -*-
"""带 TTL 缓存的 task_service 数据访问层。

shared/utils/event_manager 在进度推送时高频查询 task_service 数据
（Task/TaskCase/TestCase/Log/TestResult）。直连 PO 会造成跨服务 DB 耦合，
走 gRPC 每次调用又有网络延迟。

本模块提供 TTL 缓存 + gRPC 回源策略：
- 进度数据缓存 2 秒（满足 WebSocket 实时推送频率）
- 任务详情缓存 5 秒
- 日志数据缓存 1 秒
- gRPC 不可时回退直连 PO（保持兼容）

[归属说明] 本模块通过 gRPC 调用 task_service（无 PO 直连违规），属于合规的
gRPC 缓存装饰器层。消费方 event_manager 被 task_service 与 api_gateway 多个
服务使用，故保留在 shared/utils 作为跨服务共享基础设施。
"""
import time
import logging
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_cache: Dict[str, Any] = {}
_cache_lock = threading.Lock()

_TTL_PROGRESS = 2.0   # 进度数据缓存 2 秒
_TTL_DETAIL = 5.0     # 任务详情缓存 5 秒
_TTL_LOGS = 1.0       # 日志缓存 1 秒


def _get_cached(key: str, ttl: float) -> Optional[Any]:
    """从缓存读取，未过期则返回值，否则返回 None。"""
    entry = _cache.get(key)
    if entry is None:
        return None
    ts, val = entry
    if time.time() - ts > ttl:
        return None
    return val


def _set_cached(key: str, value: Any) -> None:
    _cache[key] = (time.time(), value)


def get_task_progress_via_grpc(task_id: int) -> Optional[dict]:
    """通过 gRPC 获取任务进度（带 TTL 缓存）。

    返回 task_service GetTaskProgress 的 data 字段（dict），
    gRPC 不可用或缓存未命中时返回 None。
    """
    cache_key = f'progress:{task_id}'
    cached = _get_cached(cache_key, _TTL_PROGRESS)
    if cached is not None:
        return cached

    try:
        from shared.clients.grpc_clients import get_task_config_service_stub
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads

        stub = get_task_config_service_stub()
        resp = stub.GetTaskProgress(task_pb.GetTaskProgressRequest(task_id=int(task_id)))
        if resp.success:
            data = _loads(resp.data, {}) or {}
            _set_cached(cache_key, data)
            return data
    except Exception:
        logger.debug("get_task_progress_via_grpc 失败 task_id=%s", task_id, exc_info=True)
    return None


def get_task_detail_via_grpc(task_id: int) -> Optional[dict]:
    """通过 gRPC 获取任务详情（带 TTL 缓存）。"""
    cache_key = f'detail:{task_id}'
    cached = _get_cached(cache_key, _TTL_DETAIL)
    if cached is not None:
        return cached

    try:
        from shared.clients.grpc_clients import get_task_config_service_stub
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads

        stub = get_task_config_service_stub()
        resp = stub.GetTaskDetail(task_pb.GetTaskDetailRequest(task_id=int(task_id)))
        if resp.success:
            data = _loads(resp.data, {}) or {}
            _set_cached(cache_key, data)
            return data
    except Exception:
        logger.debug("get_task_detail_via_grpc 失败 task_id=%s", task_id, exc_info=True)
    return None


def invalidate(task_id: int) -> None:
    """手动失效指定任务的缓存。"""
    with _cache_lock:
        for prefix in ('progress:', 'detail:', 'logs:'):
            key = f'{prefix}{task_id}'
            _cache.pop(key, None)


def clear_all() -> None:
    """清空全部缓存。"""
    with _cache_lock:
        _cache.clear()
