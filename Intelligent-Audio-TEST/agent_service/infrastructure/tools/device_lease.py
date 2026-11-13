# -*- coding: utf-8 -*-
"""设备租用适配器（INT-2492）：复用平台既有物理设备互斥锁。

平台已有的事实源是任务派发用的 ``RedisKeyPrefix.TASK_PHYSICAL_LOCK``
（``task_service/core/execution_engine/mixins/task_dispatch.py``）：按设备 SN
归一、TTL 兜底、持有者崩溃自动自愈。探索会话直接复用同一把锁——
**探索中的设备**与**跑任务的设备**天然互斥，不新建租约系统。

锁定键的 SN 解析走网关的 ``device_get``（与任务派发同口径：取不到 SN 时
退化为 device_id 并留日志，不静默换口径）。
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from agent_service.domain.ports.tool_registry import (
    RunCredentialPort, ToolTransportPort,
)
from agent_service.domain.ports.ui_device import DeviceLeasePort

logger = logging.getLogger(__name__)

LEASE_LOCK_PREFIX_KEY = 'TASK_PHYSICAL_LOCK'
DEVICE_DETAIL_TOOL = 'device_get'


class _Lease:
    """一个已持久的设备互斥锁句柄（release 幂等）。"""

    def __init__(self, lock: Any, device_id: int, lock_key: str):
        self._lock = lock
        self.device_id = device_id
        self.lock_key = lock_key

    def release(self) -> None:
        lock, self._lock = self._lock, None
        if lock is not None:
            lock.release()


class PhysicalDeviceLeaseAdapter(DeviceLeasePort):
    """按物理设备 SN 抢占互斥锁（与任务派发共用同一 Redis 键空间）。"""

    def __init__(self, *, rest: ToolTransportPort,
                 credentials: RunCredentialPort,
                 ttl_seconds: float, lock_factory=None):
        self._rest = rest
        self._credentials = credentials
        self._ttl = max(1, int(ttl_seconds))
        self._lock_factory = lock_factory

    def _lock(self, key: str, ttl: int):
        if self._lock_factory is not None:
            return self._lock_factory(key, ttl=ttl)
        from shared.models.common_enums import RedisKeyPrefix
        from shared.utils.distributed_coordinator import DistributedLock
        prefix = RedisKeyPrefix[LEASE_LOCK_PREFIX_KEY].value
        return DistributedLock(f'{prefix}:{key}', ttl=ttl,
                               retry_timeout=0)

    def _resolve_lock_key(self, device_id: int,
                          holder: str) -> str:
        try:
            from shared.agent_tools.mcp_registry import get_tool
            tool = get_tool(DEVICE_DETAIL_TOOL)
            authorization = self._credentials.get(holder) if holder else None
            result = self._rest.call(
                tool, {'device_id': device_id}, authorization=authorization,
                permissions=('device:read',))
            payload = result.payload if isinstance(result.payload, dict) else {}
            data = payload.get('data') if isinstance(payload, dict) else None
            serial = (data or {}).get('serial_number') if isinstance(
                data, dict) else None
        except Exception as exc:  # noqa: BLE001 - 解析失败不能拿错键放行
            logger.warning('设备 %s 的 SN 解析失败，租约退化为按 device_id 加锁: %s',
                           device_id, exc)
            serial = None
        if serial:
            return str(serial)
        return str(device_id)

    def acquire(self, device_id: int, *, holder: str) -> Optional[Any]:
        key = self._resolve_lock_key(device_id, holder)
        lock = self._lock(key, self._ttl)
        try:
            acquired = lock.acquire(blocking=False)
        except Exception as exc:  # noqa: BLE001 - 获取失败按「未租到」处理
            logger.warning('设备租约获取失败 device=%s: %s', device_id, exc)
            return None
        if not acquired:
            return None
        return _Lease(lock, device_id, key)

    def release(self, lease: Any) -> None:
        if lease is None:
            return
        release = getattr(lease, 'release', None)
        if callable(release):
            release()


__all__ = ['DEVICE_DETAIL_TOOL', 'LEASE_LOCK_PREFIX_KEY',
           'PhysicalDeviceLeaseAdapter']
